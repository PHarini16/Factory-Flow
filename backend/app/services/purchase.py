"""Purchase orders and goods receipt. Receipt = ledger entries + weighted-average update, atomically."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import units
from app.core.errors import Conflict, DomainError, NotFound
from app.models import Purchase, PurchaseItem, Supplier, User
from app.services import stock
from app.services.common import audit, next_number, q2


def create_purchase(db: Session, user: User, *, supplier_id: int, supplier_invoice_no: str, purchase_date: date,
                    items: list[dict], receive: bool = True, idempotency_key: str | None = None) -> Purchase:
    if idempotency_key:
        existing = db.scalar(select(Purchase).where(Purchase.idempotency_key == idempotency_key))
        if existing:
            return existing
    supplier = db.get(Supplier, supplier_id)
    if not supplier or not supplier.is_active:
        raise NotFound("Supplier not found or inactive")
    if db.scalar(select(Purchase).where(Purchase.supplier_id == supplier_id, Purchase.supplier_invoice_no == supplier_invoice_no)):
        raise Conflict(f"Supplier invoice {supplier_invoice_no} is already recorded for {supplier.name}")
    if not items:
        raise DomainError("A purchase needs at least one item")

    p = Purchase(po_number=next_number(db, "PO", purchase_date), supplier_id=supplier_id, supplier_invoice_no=supplier_invoice_no,
                 purchase_date=purchase_date, status="ORDERED", idempotency_key=idempotency_key, created_by=user.id)
    total = Decimal("0")
    for it in items:
        item = stock.get_item(db, it["item_id"])
        if item.item_type == "FINISHED":
            raise DomainError("Finished goods cannot be purchased; produce them")
        if not item.is_active:
            raise DomainError(f"{item.name} is inactive")
        qty, rate = Decimal(it["quantity"]), Decimal(it["rate"])
        if qty <= 0 or rate < 0:
            raise DomainError("Quantity must be > 0 and rate must be >= 0")
        unit = units.normalize_unit(it.get("unit") or item.unit)
        units.convert(Decimal(1), unit, item.unit)  # validate dimension compatibility
        amount = q2(qty * rate)
        total += amount
        p.items.append(PurchaseItem(item_id=item.id, quantity=qty, unit=unit, rate=rate, amount=amount))
    p.total = total
    db.add(p)
    db.flush()
    audit(db, user, "CREATE", "Purchase", p.id, new={"po": p.po_number, "total": total})
    if receive:
        _receive(db, user, p)
    db.commit()
    return p


def _receive(db: Session, user: User, p: Purchase) -> None:
    if p.status != "ORDERED":
        raise Conflict(f"Purchase {p.po_number} is already {p.status}; duplicate receipt prevented")
    for pi in p.items:
        stock.post_movement(db, item=pi.item, quantity=pi.quantity, unit=pi.unit, direction="IN",
                            movement_type="PURCHASE_RECEIPT", txn_date=p.purchase_date, source_type="Purchase",
                            source_id=p.id, user=user, remarks=f"{p.po_number} / {p.supplier_invoice_no}", rate=pi.rate)
    p.status = "RECEIVED"
    p.received_at = datetime.now(timezone.utc).replace(tzinfo=None)
    audit(db, user, "RECEIVE", "Purchase", p.id, new={"status": "RECEIVED"})


def receive_purchase(db: Session, user: User, purchase_id: int) -> Purchase:
    p = db.get(Purchase, purchase_id)
    if not p:
        raise NotFound("Purchase not found")
    _receive(db, user, p)
    db.commit()
    return p
