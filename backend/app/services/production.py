"""BOM planning, production completion, variance and costing.

Production completion is ONE database transaction:
  validate -> post raw/packaging issues -> post finished-goods output -> write run, usage, cost rows -> commit.
Any failure (e.g. insufficient stock) raises, and nothing is persisted.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import units
from app.core.config import get_settings
from app.core.errors import Conflict, DomainError, NotFound
from app.models import BOM, BOMItem, Product, ProductionCost, ProductionMaterialUsage, ProductionRun, User
from app.services import stock
from app.services.common import audit, dec, get_setting, next_number, q2, q4

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def get_tolerance(db: Session) -> Decimal:
    return Decimal(get_setting(db, "variance_tolerance_pct", str(get_settings().default_variance_tolerance_pct)))


def pct_variance(actual: Decimal, standard: Decimal) -> Decimal:
    """((actual - standard) / standard) x 100. Zero when standard is zero."""
    if standard == 0:
        return ZERO
    return (actual - standard) / standard * HUNDRED


def create_bom(db: Session, user: User, *, product_id: int, expected_output: Decimal, batch_size: Decimal,
               effective_date: date, items: list[dict], notes: str = "") -> BOM:
    product = db.get(Product, product_id)
    if not product:
        raise NotFound("Product not found")
    if not items:
        raise DomainError("BOM needs at least one item")
    if Decimal(expected_output) <= 0:
        raise DomainError("Expected output must be positive")
    last = db.scalar(select(BOM.version).where(BOM.product_id == product_id).order_by(BOM.version.desc()))
    bom = BOM(product_id=product_id, version=(last or 0) + 1, batch_size=batch_size, expected_output=expected_output,
              effective_date=effective_date, notes=notes)
    seen = set()
    for it in items:
        item = stock.get_item(db, it["item_id"])
        if item.item_type == "FINISHED":
            raise DomainError("A BOM can only contain raw or packaging items")
        if item.id in seen:
            raise DomainError(f"{item.name} appears twice in the BOM")
        seen.add(item.id)
        unit = units.normalize_unit(it.get("unit") or item.unit)
        units.convert(Decimal(1), unit, item.unit)
        if Decimal(it["quantity"]) <= 0:
            raise DomainError("BOM quantities must be positive")
        bom.items.append(BOMItem(item_id=item.id, quantity=Decimal(it["quantity"]), unit=unit, is_primary_pack=bool(it.get("is_primary_pack"))))
    db.add(bom)
    db.flush()
    audit(db, user, "CREATE", "BOM", bom.id, new={"product_id": product_id, "version": bom.version})
    db.commit()
    return bom


def _resolve_bom(db: Session, product_id: int, bom_id: int | None) -> BOM:
    if bom_id:
        bom = db.get(BOM, bom_id)
    else:
        bom = db.scalar(select(BOM).where(BOM.product_id == product_id, BOM.is_active.is_(True)).order_by(BOM.version.desc()))
    if not bom or bom.product_id != product_id:
        raise NotFound("BOM not found for this product")
    if not bom.is_active:
        raise DomainError("This BOM version is inactive")
    return bom


def standard_qty(bom_item: BOMItem, batches: Decimal) -> Decimal:
    """Standard consumption for N batches, expressed in the item's stock unit."""
    return units.convert(bom_item.quantity, bom_item.unit, bom_item.item.unit) * batches


def plan_run(db: Session, *, product_id: int, bom_id: int | None, batches: Decimal) -> dict:
    batches = Decimal(batches)
    if batches <= 0:
        raise DomainError("Number of batches must be positive")
    bom = _resolve_bom(db, product_id, bom_id)
    lines = []
    for bi in bom.items:
        std = standard_qty(bi, batches)
        avail = stock.balance(db, bi.item_id)
        lines.append({"item_id": bi.item_id, "item": bi.item.name, "item_type": bi.item.item_type, "unit": bi.item.unit,
                      "standard_qty": std, "available": avail, "sufficient": avail >= std,
                      "shortage": max(ZERO, std - avail), "is_primary_pack": bi.is_primary_pack,
                      "avg_cost": bi.item.avg_cost, "planned_cost": q2(std * bi.item.avg_cost)})
    return {"product_id": product_id, "product": bom.product.name, "bom_id": bom.id, "bom_version": bom.version,
            "batches": batches, "expected_output": bom.expected_output * batches, "lines": lines,
            "can_produce": all(l["sufficient"] for l in lines), "tolerance_pct": get_tolerance(db)}


def complete_run(db: Session, user: User, *, product_id: int, bom_id: int | None, batches: Decimal, run_date: date,
                 good_output: Decimal, actual_usage: list[dict], damaged_packets: Decimal = ZERO,
                 damaged_pouches: Decimal = ZERO, scrap_qty: Decimal = ZERO, material_wastage: Decimal = ZERO,
                 remarks: str = "", idempotency_key: str | None = None) -> ProductionRun:
    if idempotency_key:
        existing = db.scalar(select(ProductionRun).where(ProductionRun.idempotency_key == idempotency_key))
        if existing:
            return existing
    batches, good_output = Decimal(batches), Decimal(good_output)
    damaged_packets, damaged_pouches = Decimal(damaged_packets), Decimal(damaged_pouches)
    if batches <= 0:
        raise DomainError("Number of batches must be positive")
    if min(good_output, damaged_packets, damaged_pouches, Decimal(scrap_qty), Decimal(material_wastage)) < 0:
        raise DomainError("Output and wastage quantities cannot be negative")
    bom = _resolve_bom(db, product_id, bom_id)
    product = bom.product
    if not product.inventory_item_id:
        raise DomainError("Product has no finished-goods inventory item")
    tolerance = get_tolerance(db)
    bom_item_ids = {bi.item_id for bi in bom.items}
    provided = {}
    for u in actual_usage:
        iid = int(u["item_id"])
        if iid not in bom_item_ids:
            raise DomainError(f"Item {iid} is not part of BOM v{bom.version}")
        item = stock.get_item(db, iid)
        provided[iid] = units.convert(dec(u["actual_quantity"]), u.get("unit") or item.unit, item.unit)

    expected_output = bom.expected_output * batches
    run = ProductionRun(run_number=next_number(db, "RUN", run_date), product_id=product_id, bom_id=bom.id, run_date=run_date,
                        batches=batches, expected_output=expected_output, good_output=good_output,
                        damaged_packets=damaged_packets, damaged_pouches=damaged_pouches, scrap_qty=Decimal(scrap_qty),
                        material_wastage=Decimal(material_wastage), tolerance_pct=tolerance, remarks=remarks,
                        idempotency_key=idempotency_key, created_by=user.id)
    yv = pct_variance(good_output, expected_output)
    run.yield_variance_pct = q4(yv)
    run.yield_alert = abs(yv) > tolerance
    db.add(run)
    db.flush()

    material_cost = ZERO
    for bi in bom.items:
        item = bi.item
        std = standard_qty(bi, batches)
        if bi.is_primary_pack:
            # one pouch per packet: good + damaged packets + damaged (unfilled/spoiled) pouches
            actual = good_output + damaged_packets + damaged_pouches
        else:
            actual = provided.get(bi.item_id, std)  # default to standard if not supplied
        if actual < 0:
            raise DomainError("Actual consumption cannot be negative")
        unit_cost = item.avg_cost
        if actual > 0:
            mtype = "PACKAGING_CONSUMPTION" if item.item_type == "PACKAGING" else "PRODUCTION_ISSUE"
            stock.post_movement(db, item=item, quantity=actual, unit=item.unit, direction="OUT", movement_type=mtype,
                                txn_date=run_date, source_type="ProductionRun", source_id=run.id, user=user,
                                remarks=f"{run.run_number} actual consumption")
        cost = q2(actual * unit_cost)
        material_cost += cost
        var = pct_variance(actual, std)
        run.usages.append(ProductionMaterialUsage(item_id=item.id, standard_qty=std, actual_qty=actual, unit=item.unit,
                                                   unit_cost=q4(unit_cost), cost=cost, difference=actual - std,
                                                   variance_pct=q4(var), alert=abs(var) > tolerance))

    fg = product.inventory_item
    if good_output > 0:
        stock.post_movement(db, item=fg, quantity=good_output, unit=fg.unit, direction="IN", movement_type="PRODUCTION_OUTPUT",
                            txn_date=run_date, source_type="ProductionRun", source_id=run.id, user=user,
                            remarks=f"{run.run_number} good output", rate=q4(material_cost / good_output))

    cost_row = ProductionCost(run_id=run.id)
    db.add(cost_row)
    run.cost = cost_row
    _recalc_cost(cost_row, run, product, material_cost, ZERO, ZERO, ZERO)
    audit(db, user, "COMPLETE", "ProductionRun", run.id,
          new={"run": run.run_number, "good_output": good_output, "yield_variance_pct": run.yield_variance_pct})
    db.commit()
    return run


def _recalc_cost(c: ProductionCost, run: ProductionRun, product: Product, material: Decimal, labour: Decimal,
                 gas: Decimal, other: Decimal) -> None:
    overhead = labour + gas + other
    total = material + overhead
    c.material_cost, c.labour, c.gas_power, c.other_overhead = material, labour, gas, other
    c.overhead_total, c.total_cost = overhead, total
    cpp = total / run.good_output if run.good_output > 0 else ZERO
    c.cost_per_packet = q4(cpp)
    c.selling_price = product.selling_price
    c.gross_profit_per_packet = q4(product.selling_price - cpp)
    c.gross_margin_pct = q4((product.selling_price - cpp) / product.selling_price * HUNDRED) if product.selling_price else ZERO


def record_overheads(db: Session, user: User, run_id: int, *, labour: Decimal, gas_power: Decimal, other: Decimal = ZERO) -> ProductionRun:
    run = db.get(ProductionRun, run_id)
    if not run:
        raise NotFound("Production run not found")
    if min(Decimal(labour), Decimal(gas_power), Decimal(other)) < 0:
        raise DomainError("Overheads cannot be negative")
    c = run.cost
    old = {"labour": c.labour, "gas_power": c.gas_power, "other": c.other_overhead, "cost_per_packet": c.cost_per_packet}
    _recalc_cost(c, run, run.product, c.material_cost, Decimal(labour), Decimal(gas_power), Decimal(other))
    audit(db, user, "UPDATE_COST", "ProductionRun", run.id, old=old,
          new={"labour": c.labour, "gas_power": c.gas_power, "other": c.other_overhead, "cost_per_packet": c.cost_per_packet})
    db.commit()
    return run
