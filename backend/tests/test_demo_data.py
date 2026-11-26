from decimal import Decimal
from sqlalchemy import func, select

from app import demo_data, seed
from app.models import (Customer, Dispatch, InventoryItem, Invoice, Payment, ProductionRun, Product, Purchase, SalesOrder, StockMovement, Supplier)
from app.services import sales, stock


def test_demo_data_is_rich_and_consistent(db):
    res = demo_data.seed_demo_data(db)
    assert res["status"] == "loaded"
    count = lambda m: db.scalar(select(func.count()).select_from(m))
    for model in (Customer, Supplier, Product, Purchase, ProductionRun, SalesOrder, Invoice, Dispatch, Payment):
        assert count(model) >= 10, model.__name__
    # the ledger never goes negative and balances reconstruct from it
    assert all(b >= 0 for b in stock.balances_for_all(db).values())
    # receivables exist and every invoice's outstanding is non-negative
    outs = [sales.outstanding(db, i)["outstanding"] for i in db.scalars(select(Invoice))]
    assert all(o >= 0 for o in outs) and sum(outs) > 0
    # statuses for every workflow stage are represented
    statuses = {o.status for o in db.scalars(select(SalesOrder))}
    assert {"SUBMITTED", "APPROVED", "REJECTED", "INVOICED", "DISPATCHED", "PARTIALLY_DISPATCHED", "CANCELLED"} <= statuses
    # idempotent
    assert demo_data.seed_demo_data(db)["status"] == "already loaded"


def test_benchmark_still_exact_on_top_of_demo_data(db):
    demo_data.seed_demo_data(db)
    r = seed.run_benchmark(db)
    D = Decimal
    assert (r["flour_closing"], r["oil_closing"], r["spice_closing"], r["pouches_closing"], r["cartons_closing"]) == (D("120"), D("19.5"), D("3.8"), D("306"), D("21"))
    assert (r["finished_after_production"], r["finished_after_dispatch"], r["distributor_b_shortage"]) == (D("238"), D("88"), D("32"))
    assert r["invoice_total"] == D("7875") and r["retailer_a_outstanding"] == D("3875") and round(r["cost_per_packet"], 2) == D("31.14")
