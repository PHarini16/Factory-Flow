"""Report builders. Every report queries the database; nothing is precomputed or hardcoded.

Each builder returns {"title", "columns": [{key,label,numeric}], "rows": [dict], "note": str}.
"""
import csv
import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (CreditNote, Customer, Invoice, InvoiceItem, Payment, PaymentAllocation, ProductionMaterialUsage,
                        ProductionRun, Purchase, PurchaseItem, SalesOrder, StockMovement, User)
from app.services import stock
from app.services.common import q2

ZERO = Decimal("0")


def col(key, label, numeric=False):
    return {"key": key, "label": label, "numeric": numeric}


def _in_range(stmt, column, d1, d2):
    if d1:
        stmt = stmt.where(column >= d1)
    if d2:
        stmt = stmt.where(column <= d2)
    return stmt


def sales_register(db, d1, d2, **_):
    rows = []
    for i in db.scalars(_in_range(select(Invoice).order_by(Invoice.invoice_date, Invoice.id), Invoice.invoice_date, d1, d2)):
        rows.append({"invoice_no": i.invoice_no, "date": i.invoice_date, "customer": i.buyer_name, "gstin": i.buyer_gstin or "",
                     "place_of_supply": i.place_of_supply, "taxable": i.taxable_amount, "cgst": i.cgst, "sgst": i.sgst,
                     "igst": i.igst, "total": i.total, "status": i.status})
    return {"title": "Sales Register", "columns": [col("invoice_no", "Invoice"), col("date", "Date"), col("customer", "Customer"),
            col("gstin", "GSTIN"), col("place_of_supply", "Place of supply"), col("taxable", "Taxable", True), col("cgst", "CGST", True),
            col("sgst", "SGST", True), col("igst", "IGST", True), col("total", "Total", True), col("status", "Status")], "rows": rows, "note": ""}


def _posted_invoices(db, d1, d2):
    return list(db.scalars(_in_range(select(Invoice).where(Invoice.status == "POSTED").order_by(Invoice.invoice_date), Invoice.invoice_date, d1, d2)))


def customer_sales(db, d1, d2, **_):
    agg: dict[int, dict] = {}
    for i in _posted_invoices(db, d1, d2):
        r = agg.setdefault(i.customer_id, {"customer": i.buyer_name, "invoices": 0, "taxable": ZERO, "total": ZERO, "received": ZERO})
        r["invoices"] += 1
        r["taxable"] += i.taxable_amount
        r["total"] += i.total
        for a in db.scalars(select(PaymentAllocation).where(PaymentAllocation.invoice_id == i.id)):
            r["received"] += a.amount
    rows = [dict(r, outstanding=r["total"] - r["received"]) for r in agg.values()]
    return {"title": "Customer-wise Sales", "columns": [col("customer", "Customer"), col("invoices", "Invoices", True), col("taxable", "Taxable", True),
            col("total", "Invoice value", True), col("received", "Received", True), col("outstanding", "Outstanding (before credit notes)", True)],
            "rows": rows, "note": ""}


def salesman_sales(db, d1, d2, **_):
    agg: dict[int, dict] = {}
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    for i in _posted_invoices(db, d1, d2):
        r = agg.setdefault(i.salesman_id, {"salesman": names.get(i.salesman_id, "-"), "invoices": 0, "taxable": ZERO, "total": ZERO})
        r["invoices"] += 1
        r["taxable"] += i.taxable_amount
        r["total"] += i.total
    return {"title": "Salesman-wise Sales", "columns": [col("salesman", "Salesman"), col("invoices", "Invoices", True),
            col("taxable", "Taxable", True), col("total", "Invoice value", True)], "rows": list(agg.values()), "note": ""}


def product_sales(db, d1, d2, **_):
    agg: dict[int, dict] = {}
    for i in _posted_invoices(db, d1, d2):
        for it in i.items:
            r = agg.setdefault(it.product_id, {"product": it.description, "quantity": ZERO, "taxable": ZERO, "tax": ZERO, "total": ZERO})
            r["quantity"] += it.quantity
            r["taxable"] += it.taxable_amount
            r["tax"] += it.cgst + it.sgst + it.igst
            r["total"] += it.total
    return {"title": "Product-wise Sales", "columns": [col("product", "Product"), col("quantity", "Quantity", True), col("taxable", "Taxable", True),
            col("tax", "GST", True), col("total", "Total", True)], "rows": list(agg.values()), "note": ""}


def gst_summary(db, d1, d2, **_):
    agg: dict[tuple, dict] = {}
    for i in _posted_invoices(db, d1, d2):
        for it in i.items:
            key = ("Inter-state (IGST)" if i.is_interstate else "Intra-state (CGST+SGST)", "B2B" if i.buyer_gstin else "B2C", it.hsn_code, it.gst_rate)
            r = agg.setdefault(key, {"supply_type": key[0], "category": key[1], "hsn": key[2], "rate": key[3], "taxable": ZERO,
                                     "cgst": ZERO, "sgst": ZERO, "igst": ZERO, "total_tax": ZERO})
            r["taxable"] += it.taxable_amount
            r["cgst"] += it.cgst
            r["sgst"] += it.sgst
            r["igst"] += it.igst
            r["total_tax"] += it.cgst + it.sgst + it.igst
    cn_total = sum((c.total for c in db.scalars(_in_range(select(CreditNote), CreditNote.note_date, d1, d2))), ZERO)
    return {"title": "GST Outward Supply Summary", "columns": [col("supply_type", "Supply type"), col("category", "B2B/B2C"), col("hsn", "HSN"),
            col("rate", "Rate %", True), col("taxable", "Taxable", True), col("cgst", "CGST", True), col("sgst", "SGST", True),
            col("igst", "IGST", True), col("total_tax", "Total tax", True)], "rows": list(agg.values()),
            "note": f"Simplified outward-supply summary mappable to GSTR-1 / GSTR-3B categories. NOT an official filing. Credit notes in period: {cn_total}."}


def purchase_register(db, d1, d2, **_):
    rows = []
    for p in db.scalars(_in_range(select(Purchase).order_by(Purchase.purchase_date, Purchase.id), Purchase.purchase_date, d1, d2)):
        for it in p.items:
            rows.append({"po": p.po_number, "date": p.purchase_date, "supplier": p.supplier.name, "supplier_invoice": p.supplier_invoice_no,
                         "item": it.item.name, "quantity": it.quantity, "unit": it.unit, "rate": it.rate, "amount": it.amount, "status": p.status})
    return {"title": "Purchase Register", "columns": [col("po", "PO"), col("date", "Date"), col("supplier", "Supplier"), col("supplier_invoice", "Supplier invoice"),
            col("item", "Item"), col("quantity", "Qty", True), col("unit", "Unit"), col("rate", "Rate", True), col("amount", "Amount", True), col("status", "Status")],
            "rows": rows, "note": ""}


def stock_summary(db, d1, d2, **_):
    rows = stock.stock_summary(db)
    return {"title": "Stock Summary", "columns": [col("sku", "SKU"), col("name", "Item"), col("item_type", "Type"), col("quantity", "Quantity", True),
            col("unit", "Unit"), col("avg_cost", "Avg rate", True), col("value", "Value", True), col("reorder_level", "Reorder level", True),
            col("low_stock", "Low stock")], "rows": rows, "note": "Valuation: weighted average."}


def stock_ledger(db, d1, d2, item_id=None, movement_type=None, **_):
    stmt = select(StockMovement).order_by(StockMovement.txn_date, StockMovement.id)
    stmt = _in_range(stmt, StockMovement.txn_date, d1, d2)
    if item_id:
        stmt = stmt.where(StockMovement.item_id == item_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    names = {u.id: u.username for u in db.scalars(select(User))}
    rows = [{"id": m.id, "date": m.txn_date, "item": m.item.name, "type": m.movement_type, "direction": m.direction, "quantity": m.quantity,
             "unit": m.unit, "unit_cost": m.unit_cost, "value": m.value, "source": f"{m.source_type} #{m.source_id or '-'}",
             "user": names.get(m.user_id, "system"), "remarks": m.remarks} for m in db.scalars(stmt)]
    return {"title": "Stock Ledger", "columns": [col("id", "#"), col("date", "Date"), col("item", "Item"), col("type", "Movement"), col("direction", "Dir"),
            col("quantity", "Qty", True), col("unit", "Unit"), col("unit_cost", "Rate", True), col("value", "Value", True), col("source", "Source"),
            col("user", "User"), col("remarks", "Remarks")], "rows": rows, "note": "Append-only ledger."}


def _runs(db, d1, d2):
    return list(db.scalars(_in_range(select(ProductionRun).order_by(ProductionRun.run_date, ProductionRun.id), ProductionRun.run_date, d1, d2)))


def production_report(db, d1, d2, **_):
    rows = [{"run": r.run_number, "date": r.run_date, "product": r.product.name, "bom_version": r.bom.version, "batches": r.batches,
             "expected": r.expected_output, "good": r.good_output, "yield_variance_pct": r.yield_variance_pct,
             "alert": "ALERT" if r.yield_alert else "OK"} for r in _runs(db, d1, d2)]
    return {"title": "Production Report", "columns": [col("run", "Run"), col("date", "Date"), col("product", "Product"), col("bom_version", "BOM v", True),
            col("batches", "Batches", True), col("expected", "Expected", True), col("good", "Good output", True),
            col("yield_variance_pct", "Yield var %", True), col("alert", "Status")], "rows": rows, "note": ""}


def consumption_report(db, d1, d2, **_):
    rows = []
    for r in _runs(db, d1, d2):
        for u in r.usages:
            rows.append({"run": r.run_number, "date": r.run_date, "item": u.item.name, "unit": u.unit, "standard": u.standard_qty,
                         "actual": u.actual_qty, "difference": u.difference, "variance_pct": u.variance_pct, "alert": "ALERT" if u.alert else "OK"})
    return {"title": "Planned vs Actual Consumption", "columns": [col("run", "Run"), col("date", "Date"), col("item", "Item"), col("unit", "Unit"),
            col("standard", "Standard", True), col("actual", "Actual", True), col("difference", "Difference", True),
            col("variance_pct", "Variance %", True), col("alert", "Status")], "rows": rows,
            "note": "Positive variance = excess consumption. Alert when |variance| exceeds tolerance."}


def yield_wastage(db, d1, d2, **_):
    rows = [{"run": r.run_number, "date": r.run_date, "expected": r.expected_output, "good": r.good_output, "damaged_packets": r.damaged_packets,
             "damaged_pouches": r.damaged_pouches, "scrap": r.scrap_qty, "material_wastage": r.material_wastage,
             "yield_variance_pct": r.yield_variance_pct} for r in _runs(db, d1, d2)]
    return {"title": "Yield & Wastage", "columns": [col("run", "Run"), col("date", "Date"), col("expected", "Expected", True), col("good", "Good", True),
            col("damaged_packets", "Damaged packets", True), col("damaged_pouches", "Damaged pouches", True), col("scrap", "Scrap", True),
            col("material_wastage", "Material wastage", True), col("yield_variance_pct", "Yield var %", True)], "rows": rows, "note": ""}


def costing_report(db, d1, d2, **_):
    rows = []
    for r in _runs(db, d1, d2):
        c = r.cost
        rows.append({"run": r.run_number, "date": r.run_date, "product": r.product.name, "good": r.good_output, "material": c.material_cost,
                     "labour": c.labour, "gas_power": c.gas_power, "other": c.other_overhead, "total": c.total_cost,
                     "cost_per_packet": c.cost_per_packet, "selling_price": c.selling_price, "gp_per_packet": c.gross_profit_per_packet,
                     "margin_pct": c.gross_margin_pct})
    return {"title": "Production Costing", "columns": [col("run", "Run"), col("date", "Date"), col("product", "Product"), col("good", "Good pkts", True),
            col("material", "Material+pack", True), col("labour", "Labour", True), col("gas_power", "Gas & power", True), col("other", "Other", True),
            col("total", "Total cost", True), col("cost_per_packet", "Cost/packet", True), col("selling_price", "Selling price", True),
            col("gp_per_packet", "GP/packet", True), col("margin_pct", "Margin %", True)], "rows": rows,
            "note": "Weighted-average material cost + allocated overhead, divided by good packets."}


def payments_report(db, d1, d2, **_):
    rows = []
    for p in db.scalars(_in_range(select(Payment).order_by(Payment.payment_date, Payment.id), Payment.payment_date, d1, d2)):
        invs = ", ".join(db.get(Invoice, a.invoice_id).invoice_no for a in p.allocations)
        rows.append({"receipt": p.receipt_no, "date": p.payment_date, "customer": p.customer.name, "invoices": invs, "mode": p.mode,
                     "reference": p.reference, "amount": p.amount})
    return {"title": "Payments & Collections", "columns": [col("receipt", "Receipt"), col("date", "Date"), col("customer", "Customer"), col("invoices", "Invoices"),
            col("mode", "Mode"), col("reference", "Reference"), col("amount", "Amount", True)], "rows": rows, "note": ""}


def _open_invoices(db, as_of: date):
    from app.services.sales import outstanding
    for inv in db.scalars(select(Invoice).where(Invoice.status == "POSTED").order_by(Invoice.invoice_date, Invoice.id)):
        o = outstanding(db, inv)
        yield inv, o


def outstanding_report(db, d1, d2, **_):
    today = date.today()
    rows = []
    for inv, o in _open_invoices(db, today):
        if o["outstanding"] <= 0:
            continue
        rows.append({"customer": inv.buyer_name, "invoice": inv.invoice_no, "invoice_date": inv.invoice_date, "due_date": inv.due_date,
                     "amount": inv.total, "received": o["paid"], "credited": o["credited"], "outstanding": o["outstanding"],
                     "days_overdue": max(0, (today - inv.due_date).days)})
    return {"title": "Customer Outstanding", "columns": [col("customer", "Customer"), col("invoice", "Invoice"), col("invoice_date", "Invoice date"),
            col("due_date", "Due date"), col("amount", "Invoice amount", True), col("received", "Received", True), col("credited", "Credit notes", True),
            col("outstanding", "Outstanding", True), col("days_overdue", "Days overdue", True)], "rows": rows,
            "note": "Outstanding = invoice total - payments allocated - credit notes."}


def ageing_report(db, d1, d2, **_):
    today = date.today()
    agg: dict[str, dict] = {}
    for inv, o in _open_invoices(db, today):
        if o["outstanding"] <= 0:
            continue
        age = (today - inv.invoice_date).days
        b = "b0_30" if age <= 30 else "b31_60" if age <= 60 else "b61_90" if age <= 90 else "b90_plus"
        r = agg.setdefault(inv.buyer_name, {"customer": inv.buyer_name, "b0_30": ZERO, "b31_60": ZERO, "b61_90": ZERO, "b90_plus": ZERO, "total": ZERO})
        r[b] += o["outstanding"]
        r["total"] += o["outstanding"]
    return {"title": "Receivables Ageing", "columns": [col("customer", "Customer"), col("b0_30", "0-30 days", True), col("b31_60", "31-60 days", True),
            col("b61_90", "61-90 days", True), col("b90_plus", "Above 90 days", True), col("total", "Total", True)], "rows": list(agg.values()),
            "note": "Buckets are based on days since invoice date."}


REPORTS = {
    "sales-register": sales_register, "customer-sales": customer_sales, "salesman-sales": salesman_sales, "product-sales": product_sales,
    "gst-summary": gst_summary, "purchase-register": purchase_register, "stock-summary": stock_summary, "stock-ledger": stock_ledger,
    "production": production_report, "consumption": consumption_report, "yield-wastage": yield_wastage, "costing": costing_report,
    "payments": payments_report, "outstanding": outstanding_report, "ageing": ageing_report,
}


def _plain(v):
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return v if v is not None else ""


def to_csv(rep: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c["label"] for c in rep["columns"]])
    for r in rep["rows"]:
        w.writerow([_plain(r.get(c["key"])) for c in rep["columns"]])
    return buf.getvalue()


def to_xlsx(rep: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = rep["title"][:30]
    ws.append([rep["title"]])
    ws["A1"].font = Font(bold=True, size=14)
    if rep.get("note"):
        ws.append([rep["note"]])
    ws.append([])
    ws.append([c["label"] for c in rep["columns"]])
    hr = ws.max_row
    for c in ws[hr]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E293B")
        c.alignment = Alignment(horizontal="center")
    for r in rep["rows"]:
        row = []
        for c in rep["columns"]:
            v = r.get(c["key"])
            row.append(float(v) if isinstance(v, Decimal) else ("Yes" if v is True else "No" if v is False else v))  # export-only conversion
        ws.append(row)
    for i, c in enumerate(rep["columns"], 1):
        ws.column_dimensions[ws.cell(row=hr, column=i).column_letter].width = max(12, len(c["label"]) + 4)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
