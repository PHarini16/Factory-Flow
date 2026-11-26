"""Production, orders, invoices, dispatches, payments, costing, reports, audit, dashboard, demo."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import engine, get_db
from app.core.errors import Forbidden, NotFound
from app.deps import ALL, FIN_READ, OPS_READ, get_current_user, require_roles
from app.models import (AuditLog, CreditNote, Customer, Dispatch, Invoice, Payment, ProductionRun, SalesOrder, User)
from app.schemas import (AuditOut, CreditNoteIn, CreditNoteOut, DispatchIn, DispatchOut, InvoiceOut, OrderEditIn, OrderIn, OrderOut,
                         OverheadIn, PaymentIn, PaymentOut, PlanIn, ReasonIn, RunIn, RunOut)
from app.services.common import jsonable
from app.services import dashboard as dash_svc, pdf, production as prod_svc, reports, sales, stock

production = APIRouter(prefix="/production", tags=["production"])
orders = APIRouter(prefix="/orders", tags=["orders"])
invoices = APIRouter(prefix="/invoices", tags=["invoices"])
dispatches = APIRouter(prefix="/dispatches", tags=["dispatches"])
payments = APIRouter(prefix="/payments", tags=["payments"])
costing = APIRouter(prefix="/costing", tags=["costing"])
report_router = APIRouter(prefix="/reports", tags=["reports"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])
dashboard = APIRouter(prefix="/dashboard", tags=["dashboard"])
demo = APIRouter(prefix="/demo", tags=["demo"])

PROD_WRITE = require_roles("PRODUCTION", "ADMIN")
ADMIN = require_roles("ADMIN")


# ------------------------------------------------ production
@production.post("/plan")
def plan(body: PlanIn, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    return jsonable(prod_svc.plan_run(db, product_id=body.product_id, bom_id=body.bom_id, batches=body.batches))


@production.post("/runs", response_model=RunOut, status_code=201)
def complete_run(body: RunIn, db: Session = Depends(get_db), user: User = Depends(PROD_WRITE)):
    return prod_svc.complete_run(db, user, product_id=body.product_id, bom_id=body.bom_id, batches=body.batches, run_date=body.run_date,
                                 good_output=body.good_output, actual_usage=[u.model_dump() for u in body.actual_usage],
                                 damaged_packets=body.damaged_packets, damaged_pouches=body.damaged_pouches, scrap_qty=body.scrap_qty,
                                 material_wastage=body.material_wastage, remarks=body.remarks, idempotency_key=body.idempotency_key)


@production.get("/runs", response_model=list[RunOut])
def list_runs(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    stmt = select(ProductionRun).order_by(ProductionRun.id.desc())
    if date_from:
        stmt = stmt.where(ProductionRun.run_date >= date_from)
    if date_to:
        stmt = stmt.where(ProductionRun.run_date <= date_to)
    return list(db.scalars(stmt))


@production.get("/runs/{rid}", response_model=RunOut)
def get_run(rid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    r = db.get(ProductionRun, rid)
    if not r:
        raise NotFound("Run not found")
    return r


@production.post("/runs/{rid}/costs", response_model=RunOut)
def set_costs(rid: int, body: OverheadIn, db: Session = Depends(get_db), user: User = Depends(PROD_WRITE)):
    return prod_svc.record_overheads(db, user, rid, labour=body.labour, gas_power=body.gas_power, other=body.other)


# ------------------------------------------------ orders
def _own(user: User, o: SalesOrder):
    if user.role == "SALESMAN" and o.salesman_id != user.id:
        raise Forbidden("This order belongs to another salesman")


@orders.get("", response_model=list[OrderOut])
def list_orders(status: str | None = None, customer_id: int | None = None, db: Session = Depends(get_db),
                user: User = Depends(require_roles("SALESMAN", "ADMIN", "OWNER", "ACCOUNTANT"))):
    stmt = select(SalesOrder).order_by(SalesOrder.id.desc())
    if user.role == "SALESMAN":
        stmt = stmt.where(SalesOrder.salesman_id == user.id)
    if status:
        stmt = stmt.where(SalesOrder.status == status)
    if customer_id:
        stmt = stmt.where(SalesOrder.customer_id == customer_id)
    return list(db.scalars(stmt))


@orders.post("", response_model=OrderOut, status_code=201)
def create_order(body: OrderIn, db: Session = Depends(get_db), user: User = Depends(require_roles("SALESMAN", "ADMIN"))):
    return sales.create_order(db, user, customer_id=body.customer_id, items=[i.model_dump() for i in body.items], remarks=body.remarks,
                              idempotency_key=body.idempotency_key, draft=body.draft)


@orders.get("/my-customer-sales")
def my_customer_sales(db: Session = Depends(get_db), user: User = Depends(require_roles("SALESMAN"))):
    out: dict[int, dict] = {}
    for o in db.scalars(select(SalesOrder).where(SalesOrder.salesman_id == user.id, SalesOrder.status.notin_(["REJECTED", "CANCELLED", "DRAFT"]))):
        r = out.setdefault(o.customer_id, {"customer": o.customer.name, "orders": 0, "value": 0})
        r["orders"] += 1
        r["value"] += o.subtotal
    return jsonable(list(out.values()))


@orders.get("/{oid}", response_model=OrderOut)
def get_order(oid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("SALESMAN", "ADMIN", "OWNER", "ACCOUNTANT"))):
    o = sales.get_order(db, oid)
    _own(user, o)
    return o


@orders.get("/{oid}/stock-check")
def order_stock_check(oid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OWNER")) ):
    o = sales.get_order(db, oid)
    lines = sales.stock_check(db, o)
    return jsonable({"order_no": o.order_no, "all_sufficient": all(l["sufficient"] for l in lines), "lines": lines})


@orders.put("/{oid}", response_model=OrderOut)
def edit_order(oid: int, body: OrderEditIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return sales.edit_order(db, user, oid, [i.model_dump() for i in body.items], body.reason)


@orders.post("/{oid}/submit", response_model=OrderOut)
def submit(oid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("SALESMAN", "ADMIN"))):
    return sales.submit_order(db, user, oid)


@orders.post("/{oid}/approve")
def approve(oid: int, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    o = sales.decide_order(db, user, oid, True)
    lines = sales.stock_check(db, o)
    return {"order": OrderOut.model_validate(o), "stock_warning": not all(l["sufficient"] for l in lines), "stock_check": jsonable(lines)}


@orders.post("/{oid}/reject", response_model=OrderOut)
def reject(oid: int, body: ReasonIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return sales.decide_order(db, user, oid, False, body.reason)


@orders.post("/{oid}/cancel", response_model=OrderOut)
def cancel(oid: int, body: ReasonIn, db: Session = Depends(get_db), user: User = Depends(require_roles("SALESMAN", "ADMIN"))):
    return sales.cancel_order(db, user, oid, body.reason)


# ------------------------------------------------ invoices
def _inv_out(db, inv):
    o = sales.outstanding(db, inv)
    out = InvoiceOut.model_validate(inv)
    out.paid, out.credited, out.outstanding = o["paid"], o["credited"], o["outstanding"]
    return out


@invoices.get("", response_model=list[InvoiceOut])
def list_invoices(customer_id: int | None = None, status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                  db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT", "SALESMAN"))):
    stmt = select(Invoice).order_by(Invoice.id.desc())
    if user.role == "SALESMAN":
        stmt = stmt.where(Invoice.salesman_id == user.id)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= date_to)
    return [_inv_out(db, i) for i in db.scalars(stmt)]


@invoices.post("/from-order/{oid}", response_model=InvoiceOut, status_code=201)
def create_invoice(oid: int, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return _inv_out(db, sales.create_invoice(db, user, oid))


@invoices.get("/{iid}", response_model=InvoiceOut)
def get_invoice(iid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT", "SALESMAN"))):
    inv = sales.get_invoice(db, iid)
    if user.role == "SALESMAN" and inv.salesman_id != user.id:
        raise Forbidden("Not your invoice")
    return _inv_out(db, inv)


@invoices.get("/{iid}/pdf")
def invoice_pdf(iid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT", "SALESMAN"))):
    inv = sales.get_invoice(db, iid)
    if user.role == "SALESMAN" and inv.salesman_id != user.id:
        raise Forbidden("Not your invoice")
    name = inv.invoice_no.replace("/", "-")
    return Response(pdf.invoice_pdf(inv), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


@invoices.post("/{iid}/cancel", response_model=InvoiceOut)
def cancel_invoice(iid: int, body: ReasonIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return _inv_out(db, sales.cancel_invoice(db, user, iid, body.reason))


@invoices.post("/{iid}/credit-notes", response_model=CreditNoteOut, status_code=201)
def credit_note(iid: int, body: CreditNoteIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return sales.issue_credit_note(db, user, iid, [l.model_dump() for l in body.lines], body.reason, body.restock)


@invoices.get("/{iid}/credit-notes", response_model=list[CreditNoteOut])
def list_credit_notes(iid: int, db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT"))):
    return list(db.scalars(select(CreditNote).where(CreditNote.invoice_id == iid)))


# ------------------------------------------------ dispatches
@dispatches.get("", response_model=list[DispatchOut])
def list_dispatches(db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT"))):
    return list(db.scalars(select(Dispatch).order_by(Dispatch.id.desc())))


@dispatches.post("", response_model=DispatchOut, status_code=201)
def create_dispatch(body: DispatchIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return sales.create_dispatch(db, user, invoice_id=body.invoice_id, lines=[l.model_dump() for l in body.lines] if body.lines else None,
                                 remarks=body.remarks, vehicle_no=body.vehicle_no, dispatch_date=body.dispatch_date,
                                 idempotency_key=body.idempotency_key)


# ------------------------------------------------ payments
@payments.get("", response_model=list[PaymentOut])
def list_payments(customer_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT"))):
    stmt = select(Payment).order_by(Payment.id.desc())
    if customer_id:
        stmt = stmt.where(Payment.customer_id == customer_id)
    return list(db.scalars(stmt))


@payments.post("", response_model=PaymentOut, status_code=201)
def record_payment(body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    return sales.record_payment(db, user, customer_id=body.customer_id, amount=body.amount, mode=body.mode, payment_date=body.payment_date,
                                reference=body.reference, remarks=body.remarks, invoice_id=body.invoice_id, idempotency_key=body.idempotency_key)


@payments.get("/{pid}/receipt")
def receipt(pid: int, db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN", "OWNER", "ACCOUNTANT"))):
    p = db.get(Payment, pid)
    if not p:
        raise NotFound("Payment not found")
    nos = [db.get(Invoice, a.invoice_id).invoice_no for a in p.allocations]
    name = p.receipt_no.replace("/", "-")
    return Response(pdf.receipt_pdf(p, nos), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


# ------------------------------------------------ costing
@costing.get("/runs")
def costing_runs(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    return jsonable(reports.costing_report(db, date_from, date_to))


@costing.get("/weighted-average")
def weighted_avg(db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    return jsonable([{"item": r["name"], "unit": r["unit"], "quantity": r["quantity"], "avg_cost": r["avg_cost"], "value": r["value"]}
                     for r in stock.stock_summary(db) if r["item_type"] != "FINISHED"])


# ------------------------------------------------ reports
PROD_REPORTS = {"production", "consumption", "yield-wastage", "costing", "stock-summary", "stock-ledger"}


@report_router.get("")
def list_reports(user: User = Depends(require_roles("OWNER", "ADMIN", "ACCOUNTANT", "PRODUCTION"))):
    return [k for k in reports.REPORTS if user.role != "PRODUCTION" or k in PROD_REPORTS]


@report_router.get("/{name}")
def get_report(name: str, date_from: date | None = None, date_to: date | None = None, format: str = Query("json", pattern="^(json|csv|xlsx)$"),
               item_id: int | None = None, movement_type: str | None = None, db: Session = Depends(get_db),
               user: User = Depends(require_roles("OWNER", "ADMIN", "ACCOUNTANT", "PRODUCTION"))):
    if name not in reports.REPORTS:
        raise NotFound("Unknown report")
    if user.role == "PRODUCTION" and name not in PROD_REPORTS:
        raise Forbidden("Your role cannot access this report")
    rep = reports.REPORTS[name](db, date_from, date_to, item_id=item_id, movement_type=movement_type)
    if format == "csv":
        return Response(reports.to_csv(rep), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    if format == "xlsx":
        return Response(reports.to_xlsx(rep), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    return jsonable(rep)


# ------------------------------------------------ audit + dashboard
@audit_router.get("", response_model=list[AuditOut])
def get_audit(entity_type: str | None = None, action: str | None = None, username: str | None = None, limit: int = Query(200, le=1000),
              db: Session = Depends(get_db), _: User = Depends(require_roles("OWNER", "ADMIN", "ACCOUNTANT"))):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    return list(db.scalars(stmt))


@dashboard.get("")
def get_dashboard(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db),
                  _: User = Depends(require_roles("OWNER", "ADMIN", "ACCOUNTANT"))):
    return jsonable(dash_svc.summary(db, date_from, date_to))


# ------------------------------------------------ demo (disabled unless DEMO_MODE=true)
def _demo_guard():
    if not get_settings().demo_mode:
        raise HTTPException(404, "Demo endpoints are disabled")


@demo.post("/reset")
def demo_reset(user: User = Depends(require_roles("OWNER")), db: Session = Depends(get_db)):
    """Drops and re-creates all tables, then re-seeds master data (clean state before the benchmark)."""
    _demo_guard()
    from app import seed
    db.close()
    seed.reset_database(engine)
    from app.core.db import SessionLocal
    with SessionLocal() as s:
        seed.seed_all(s, get_settings().seed_demo_data)
    return {"status": "reset", "message": "Database reset to seed data. Log in again if your session was invalidated."}


@demo.post("/run-benchmark")
def demo_run_benchmark(db: Session = Depends(get_db), user: User = Depends(require_roles("OWNER"))):
    _demo_guard()
    from app import seed
    from app.services.common import jsonable
    return jsonable(seed.run_benchmark(db))
