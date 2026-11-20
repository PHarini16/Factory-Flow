"""Owner dashboard - every figure is computed from database records."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Customer, Invoice, Payment, ProductionMaterialUsage, ProductionRun, SalesOrder, StockMovement)
from app.services import stock
from app.services.sales import outstanding

ZERO = Decimal("0")


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def summary(db: Session, date_from: date | None = None, date_to: date | None = None) -> dict:
    today = date.today()
    d1 = date_from or today.replace(day=1)
    d2 = date_to or today
    invoices = list(db.scalars(select(Invoice).where(Invoice.status == "POSTED")))
    in_range = [i for i in invoices if d1 <= i.invoice_date <= d2]
    runs = list(db.scalars(select(ProductionRun).where(ProductionRun.run_date >= d1, ProductionRun.run_date <= d2)))
    summ = stock.stock_summary(db)
    open_rows = []
    total_out = ZERO
    for i in invoices:
        o = outstanding(db, i)["outstanding"]
        if o > 0:
            total_out += o
            open_rows.append((i, o))
    by_cust: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for i, o in open_rows:
        by_cust[i.buyer_name] += o
    exp = sum((r.expected_output for r in runs), ZERO)
    good = sum((r.good_output for r in runs), ZERO)

    alerts = []
    for r in runs:
        if r.yield_alert:
            alerts.append({"run": r.run_number, "item": "Yield", "variance_pct": r.yield_variance_pct, "kind": "YIELD"})
        for u in r.usages:
            if u.alert:
                alerts.append({"run": r.run_number, "item": u.item.name, "variance_pct": u.variance_pct, "kind": "CONSUMPTION"})

    # trends (last 6 months, independent of the filter)
    months = []
    y, m = today.year, today.month
    for _ in range(6):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    sales_m = defaultdict(lambda: ZERO)
    coll_m = defaultdict(lambda: ZERO)
    prod_m = defaultdict(lambda: ZERO)
    disp_m = defaultdict(lambda: ZERO)
    for i in invoices:
        sales_m[_month_key(i.invoice_date)] += i.total
    for p in db.scalars(select(Payment)):
        coll_m[_month_key(p.payment_date)] += p.amount
    for r in db.scalars(select(ProductionRun)):
        prod_m[_month_key(r.run_date)] += r.good_output
    for mv in db.scalars(select(StockMovement).where(StockMovement.movement_type == "SALES_DISPATCH")):
        disp_m[_month_key(mv.txn_date)] += mv.quantity
    prod_sales = defaultdict(lambda: ZERO)
    for i in in_range:
        for it in i.items:
            prod_sales[it.description] += it.taxable_amount
    dist = defaultdict(lambda: ZERO)
    for s in summ:
        dist[s["item_type"]] += s["value"]
    low = [s for s in summ if s["low_stock"]]
    fg = sum((s["quantity"] for s in summ if s["item_type"] == "FINISHED"), ZERO)

    recent_orders = db.scalars(select(SalesOrder).order_by(SalesOrder.id.desc()).limit(6))
    recent_runs = db.scalars(select(ProductionRun).order_by(ProductionRun.id.desc()).limit(5))
    pending = db.scalars(select(SalesOrder).where(SalesOrder.status == "SUBMITTED").order_by(SalesOrder.id))
    return {
        "range": {"from": d1, "to": d2},
        "kpis": {
            "todays_orders": len(list(db.scalars(select(SalesOrder).where(SalesOrder.order_date == today)))),
            "todays_sales": sum((i.total for i in invoices if i.invoice_date == today), ZERO),
            "monthly_revenue": sum((i.total for i in in_range), ZERO),
            "total_outstanding": total_out,
            "raw_material_stock_value": sum((s["value"] for s in summ if s["item_type"] in ("RAW", "PACKAGING")), ZERO),
            "finished_goods_stock": fg,
            "production_batches": sum((r.batches for r in runs), ZERO),
            "production_yield_pct": (good / exp * 100) if exp else ZERO,
            "low_stock_count": len(low),
            "variance_alert_count": len(alerts),
        },
        "charts": {
            "sales_trend": [{"month": k, "sales": sales_m[k]} for k in months],
            "product_sales": [{"product": k, "sales": v} for k, v in prod_sales.items()],
            "production_vs_sales": [{"month": k, "produced": prod_m[k], "dispatched": disp_m[k]} for k in months],
            "inventory_distribution": [{"type": k, "value": v} for k, v in dist.items()],
            "collection_trend": [{"month": k, "collected": coll_m[k]} for k in months],
            "wastage": [{"run": r.run_number, "damaged_packets": r.damaged_packets, "damaged_pouches": r.damaged_pouches, "scrap": r.scrap_qty} for r in runs],
        },
        "low_stock": low,
        "alerts": alerts,
        "recent_orders": [{"id": o.id, "order_no": o.order_no, "customer": o.customer.name, "status": o.status, "total": o.total_estimate, "date": o.order_date} for o in recent_orders],
        "recent_runs": [{"id": r.id, "run_number": r.run_number, "product": r.product.name, "good_output": r.good_output, "yield_variance_pct": r.yield_variance_pct} for r in recent_runs],
        "pending_approvals": [{"id": o.id, "order_no": o.order_no, "customer": o.customer.name, "total": o.total_estimate} for o in pending],
        "outstanding_customers": sorted([{"customer": k, "outstanding": v} for k, v in by_cust.items()], key=lambda x: -x["outstanding"]),
    }
