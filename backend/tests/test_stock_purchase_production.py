from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import Conflict, DomainError, InsufficientStock
from app.models import StockMovement
from app.services import production, purchase, stock

D = Decimal
TODAY = date.today()


def _purchase(db, users, items, inv="S-1", key=None):
    from sqlalchemy import select
    from app.models import Supplier
    sup = db.scalar(select(Supplier))
    return purchase.create_purchase(db, users["admin"], supplier_id=sup.id, supplier_invoice_no=inv, purchase_date=TODAY,
                                    items=[{"item_id": items["RM-FLOUR"].id, "quantity": D("60"), "rate": D("45"), "unit": "kg"}], idempotency_key=key)


def test_purchase_updates_stock_and_writes_ledger(db, users, items):
    p = _purchase(db, users, items)
    assert p.status == "RECEIVED" and p.total == D("2700.00")
    assert stock.balance(db, items["RM-FLOUR"].id) == D("160")
    mv = db.query(StockMovement).filter_by(source_type="Purchase", source_id=p.id).one()
    assert mv.movement_type == "PURCHASE_RECEIPT" and mv.direction == "IN" and mv.user_id == users["admin"].id


def test_duplicate_supplier_invoice_blocked(db, users, items):
    _purchase(db, users, items, "DUP-1")
    with pytest.raises(Conflict):
        _purchase(db, users, items, "DUP-1")
    assert stock.balance(db, items["RM-FLOUR"].id) == D("160")


def test_idempotent_purchase_returns_same_record(db, users, items):
    a = _purchase(db, users, items, "K-1", key="abc")
    b = _purchase(db, users, items, "K-2", key="abc")
    assert a.id == b.id and stock.balance(db, items["RM-FLOUR"].id) == D("160")


def test_double_receipt_prevented(db, users, items):
    p = _purchase(db, users, items)
    with pytest.raises(Conflict):
        purchase.receive_purchase(db, users["admin"], p.id)
    assert stock.balance(db, items["RM-FLOUR"].id) == D("160")


def test_no_negative_stock(db, users, items):
    with pytest.raises(InsufficientStock) as e:
        stock.post_movement(db, item=items["RM-FLOUR"], quantity=D("101"), unit="kg", direction="OUT", movement_type="PRODUCTION_ISSUE",
                            txn_date=TODAY, source_type="T", source_id=1, user=users["admin"])
    assert e.value.detail["shortage"] == "1"


def test_ledger_is_immutable(db, users, items):
    mv = db.query(StockMovement).first()
    mv.remarks = "tamper"
    with pytest.raises(RuntimeError):
        db.commit()
    db.rollback()


def test_ledger_reconstructs_balance(db, users, items):
    _purchase(db, users, items)
    s = stock.item_ledger_summary(db, items["RM-FLOUR"].id, None, None)
    assert s["opening"] == D("100") and s["receipts"] == D("60") and s["closing"] == D("160")
    assert s["closing"] == stock.balance(db, items["RM-FLOUR"].id)


def test_bom_expected_consumption(db, murukku):
    plan = production.plan_run(db, product_id=murukku.id, bom_id=None, batches=D("2"))
    by = {l["item"]: l for l in plan["lines"]}
    assert plan["expected_output"] == D("400")
    assert by["Flour"]["standard_qty"] == D("80") and by["Cooking oil"]["standard_qty"] == D("20")
    assert by["Flour"]["available"] == D("100")
    assert plan["can_produce"] is True


def test_plan_flags_shortage(db, murukku):
    plan = production.plan_run(db, product_id=murukku.id, bom_id=None, batches=D("3"))  # flour 120 > 100
    flour = next(l for l in plan["lines"] if l["item"] == "Flour")
    assert plan["can_produce"] is False and flour["shortage"] == D("20")


def _run(db, users, items, murukku, **kw):
    args = dict(product_id=murukku.id, bom_id=None, batches=D("1"), run_date=TODAY, good_output=D("188"), damaged_pouches=D("6"),
                actual_usage=[{"item_id": items["RM-FLOUR"].id, "actual_quantity": D("40")}, {"item_id": items["RM-OIL"].id, "actual_quantity": D("10.5")},
                              {"item_id": items["RM-SPICE"].id, "actual_quantity": D("1.2")}, {"item_id": items["PK-CARTON"].id, "actual_quantity": D("9")}])
    args.update(kw)
    return production.complete_run(db, users["production"], **args)


def test_production_deductions_and_fg_addition(db, users, items, murukku):
    run = _run(db, users, items, murukku)
    b = lambda sku: stock.balance(db, items[sku].id)
    assert (b("RM-FLOUR"), b("RM-OIL"), b("RM-SPICE"), b("PK-POUCH200"), b("PK-CARTON")) == (D("60"), D("19.5"), D("3.8"), D("306"), D("21"))
    assert stock.balance(db, murukku.inventory_item_id) == D("238")
    assert run.expected_output == D("200") and run.yield_variance_pct == D("-6") and run.yield_alert is True


def test_variances_and_alerts(db, users, items, murukku):
    run = _run(db, users, items, murukku)
    u = {x.item.sku: x for x in run.usages}
    assert u["RM-OIL"].variance_pct == D("5") and u["RM-OIL"].alert is True and u["RM-OIL"].difference == D("0.5")
    assert u["RM-FLOUR"].alert is False and u["RM-SPICE"].alert is False
    assert u["PK-POUCH200"].actual_qty == D("194") and u["PK-POUCH200"].variance_pct == D("-3") and u["PK-POUCH200"].alert is False
    assert u["PK-CARTON"].variance_pct == D("-10") and u["PK-CARTON"].alert is True


def test_production_rolls_back_on_insufficient_stock(db, users, items, murukku):
    bad = [{"item_id": items["RM-FLOUR"].id, "actual_quantity": D("40")}, {"item_id": items["RM-OIL"].id, "actual_quantity": D("31")}]
    before = db.query(StockMovement).count()
    with pytest.raises(InsufficientStock):
        _run(db, users, items, murukku, actual_usage=bad)
    db.rollback()
    assert db.query(StockMovement).count() == before
    assert stock.balance(db, items["RM-FLOUR"].id) == D("100")  # flour issue (posted first) was rolled back
    assert stock.balance(db, murukku.inventory_item_id) == D("50")


def test_production_idempotent(db, users, items, murukku):
    a = _run(db, users, items, murukku, idempotency_key="r1")
    b = _run(db, users, items, murukku, idempotency_key="r1")
    assert a.id == b.id and stock.balance(db, items["RM-FLOUR"].id) == D("60")


def test_unit_conversion_in_actuals(db, users, items, murukku):
    _run(db, users, items, murukku, actual_usage=[{"item_id": items["RM-FLOUR"].id, "actual_quantity": D("40000"), "unit": "g"}])
    assert stock.balance(db, items["RM-FLOUR"].id) == D("60")


def test_bom_versioning_keeps_history(db, users, items, murukku):
    run = _run(db, users, items, murukku)
    v2 = production.create_bom(db, users["production"], product_id=murukku.id, expected_output=D("210"), batch_size=D("1"), effective_date=TODAY,
                               items=[{"item_id": items["RM-FLOUR"].id, "quantity": D("42"), "unit": "kg"}, {"item_id": items["PK-POUCH200"].id, "quantity": D("210"), "unit": "piece", "is_primary_pack": True}])
    assert v2.version == 2 and run.bom.version == 1


def test_costing_benchmark(db, users, items, murukku):
    _purchase(db, users, items)
    run = _run(db, users, items, murukku)
    c = run.cost
    assert c.material_cost == D("4055") and c.total_cost == D("4055")
    production.record_overheads(db, users["production"], run.id, labour=D("1200"), gas_power=D("600"))
    assert c.overhead_total == D("1800") and c.total_cost == D("5855")
    assert round(c.cost_per_packet, 2) == D("31.14")
    assert c.gross_profit_per_packet == D("50") - D("5855") / D("188") or abs(c.gross_profit_per_packet - (D("50") - D("5855") / D("188"))) < D("0.0001")
