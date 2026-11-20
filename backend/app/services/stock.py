"""Transaction-safe stock service - the ONLY place that writes StockMovement rows.

Rules enforced here:
 * quantities are converted to the item's own stock unit via core.units
 * OUT movements never take stock below zero (InsufficientStock is raised)
 * IN movements with a cost update the item's weighted-average rate
 * every movement carries source document type/id, user and timestamp
Callers own the transaction boundary: they call db.commit() after all steps
succeed, and the request-scoped session rolls everything back on any exception.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import units
from app.core.errors import DomainError, InsufficientStock, NotFound
from app.models import InventoryItem, StockMovement, User
from app.services.common import q4

ZERO = Decimal("0")
IN_TYPES = {"OPENING", "PURCHASE_RECEIPT", "PRODUCTION_OUTPUT", "SALES_RETURN"}
OUT_TYPES = {"PRODUCTION_ISSUE", "PACKAGING_CONSUMPTION", "SALES_DISPATCH", "PURCHASE_RETURN"}
ALL_TYPES = IN_TYPES | OUT_TYPES | {"STOCK_ADJUSTMENT"}


def get_item(db: Session, item_id: int) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if not item:
        raise NotFound(f"Inventory item {item_id} not found")
    return item


def balance(db: Session, item_id: int, before: date | None = None, upto: date | None = None) -> Decimal:
    """Stock balance reconstructed from the ledger (never stored)."""
    stmt = select(StockMovement.direction, StockMovement.quantity).where(StockMovement.item_id == item_id)
    if before:
        stmt = stmt.where(StockMovement.txn_date < before)
    if upto:
        stmt = stmt.where(StockMovement.txn_date <= upto)
    total = ZERO
    for direction, qty in db.execute(stmt):
        total += qty if direction == "IN" else -qty
    return total


def balances_for_all(db: Session) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for item_id, direction, qty in db.execute(select(StockMovement.item_id, StockMovement.direction, StockMovement.quantity)):
        out[item_id] = out.get(item_id, ZERO) + (qty if direction == "IN" else -qty)
    return out


def post_movement(db: Session, *, item: InventoryItem, quantity: Decimal, unit: str | None, direction: str,
                  movement_type: str, txn_date: date, source_type: str, source_id: int | None,
                  user: User | None, remarks: str = "", rate: Decimal | None = None) -> StockMovement:
    if direction not in ("IN", "OUT"):
        raise DomainError("direction must be IN or OUT")
    if movement_type not in ALL_TYPES:
        raise DomainError(f"Unknown movement type {movement_type}")
    if movement_type in IN_TYPES and direction != "IN" or movement_type in OUT_TYPES and direction != "OUT":
        raise DomainError(f"Movement type {movement_type} is inconsistent with direction {direction}")
    entered = Decimal(quantity)
    if entered <= 0:
        raise DomainError("Quantity must be greater than zero")
    q = units.convert(entered, unit or item.unit, item.unit)  # raises UnitError for incompatible units
    bal = balance(db, item.id)

    if direction == "OUT":
        if bal < q:
            raise InsufficientStock(
                f"Insufficient stock for {item.name}: available {bal} {item.unit}, requested {q} {item.unit}",
                {"item_id": item.id, "item": item.name, "available": str(bal), "requested": str(q),
                 "shortage": str(q - bal), "unit": item.unit})
        unit_cost = item.avg_cost
    else:
        if rate is not None:
            value_in = Decimal(rate) * entered  # rate is per *entered* unit
            unit_cost = value_in / q
            new_qty = bal + q
            item.avg_cost = (bal * item.avg_cost + value_in) / new_qty  # weighted average
        else:
            unit_cost = item.avg_cost

    mv = StockMovement(item_id=item.id, quantity=q, unit=item.unit, direction=direction, movement_type=movement_type,
                       txn_date=txn_date, source_type=source_type, source_id=source_id, user_id=user.id if user else None,
                       remarks=remarks, unit_cost=q4(unit_cost), value=q4(q * unit_cost))
    db.add(mv)
    db.flush()
    return mv


def item_ledger_summary(db: Session, item_id: int, date_from: date | None, date_to: date | None) -> dict:
    """Opening / receipts / issues / adjustments / closing for a period."""
    item = get_item(db, item_id)
    stmt = select(StockMovement).where(StockMovement.item_id == item_id).order_by(StockMovement.txn_date, StockMovement.id)
    opening = balance(db, item_id, before=date_from) if date_from else ZERO
    receipts = issues = adjustments = ZERO
    for m in db.scalars(stmt):
        if date_from and m.txn_date < date_from:
            continue
        if date_to and m.txn_date > date_to:
            continue
        signed = m.quantity if m.direction == "IN" else -m.quantity
        if m.movement_type == "OPENING":
            opening += m.quantity
        elif m.movement_type == "STOCK_ADJUSTMENT":
            adjustments += signed
        elif m.direction == "IN":
            receipts += m.quantity
        else:
            issues += m.quantity
    closing = opening + receipts - issues + adjustments
    return {"item_id": item_id, "item": item.name, "unit": item.unit, "opening": opening, "receipts": receipts,
            "issues": issues, "adjustments": adjustments, "closing": closing}


def stock_summary(db: Session, item_type: str | None = None) -> list[dict]:
    stmt = select(InventoryItem).where(InventoryItem.is_active.is_(True)).order_by(InventoryItem.item_type, InventoryItem.name)
    if item_type:
        stmt = stmt.where(InventoryItem.item_type == item_type)
    bal = balances_for_all(db)
    rows = []
    for it in db.scalars(stmt):
        b = bal.get(it.id, ZERO)
        rows.append({"item_id": it.id, "sku": it.sku, "name": it.name, "item_type": it.item_type, "category": it.category,
                     "unit": it.unit, "quantity": b, "avg_cost": it.avg_cost, "value": q4(b * it.avg_cost),
                     "reorder_level": it.reorder_level, "low_stock": b <= it.reorder_level and it.reorder_level > 0,
                     "valuation_method": it.valuation_method})
    return rows
