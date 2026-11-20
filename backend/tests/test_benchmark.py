"""Mandatory benchmark scenario - exact expected values from the project brief."""
from decimal import Decimal

import pytest

from app import seed
from app.core.errors import Conflict

D = Decimal


@pytest.fixture()
def result(db):
    return seed.run_benchmark(db)


def test_inventory_closings(result):
    assert result["flour_closing"] == D("120")
    assert result["oil_closing"] == D("19.5")
    assert result["spice_closing"] == D("3.8")
    assert result["pouches_closing"] == D("306")
    assert result["cartons_closing"] == D("21")


def test_finished_goods_and_shortage(result):
    assert result["finished_after_production"] == D("238")
    assert result["finished_after_dispatch"] == D("88")
    assert result["distributor_b_shortage"] == D("32")


def test_variances(result):
    assert result["expected_output"] == D("200") and result["good_output"] == D("188")
    assert result["yield_variance_pct"] == D("-6")
    assert result["oil_variance_pct"] == D("5")


def test_gst_invoice_and_outstanding(result):
    assert result["taxable"] == D("7500") and result["cgst"] == D("187.50") and result["sgst"] == D("187.50") and result["igst"] == 0
    assert result["invoice_total"] == D("7875")
    assert result["retailer_a_outstanding"] == D("3875")


def test_costing(result):
    assert result["flour_wavg_rate"] == D("43.125")
    assert (result["flour_cost"], result["oil_cost"], result["spice_cost"], result["pouch_cost"], result["carton_cost"]) == \
           (D("1725"), D("1470"), D("240"), D("485"), D("135"))
    assert result["material_cost"] == D("4055") and result["overhead"] == D("1800") and result["total_cost"] == D("5855")
    assert round(result["cost_per_packet"], 2) == D("31.14")


def test_benchmark_not_repeatable_without_reset(db, result):
    with pytest.raises(Conflict):
        seed.run_benchmark(db)


def test_benchmark_reports_and_dashboard_are_database_driven(client, auth, result):
    h = auth("owner")
    dash = client.get("/api/v1/dashboard", headers=h).json()
    assert D(dash["kpis"]["total_outstanding"]) == D("3875.00")
    assert D(dash["kpis"]["finished_goods_stock"]) == D("88")
    assert any(a["item"] == "Cooking oil" for a in dash["alerts"])
    assert any(l["name"] == "Cooking oil" for l in dash["low_stock"])  # 19.5 <= reorder 20
    assert dash["pending_approvals"][0]["customer"].startswith("Distributor B")
    out = client.get("/api/v1/reports/outstanding", headers=h).json()
    assert D(out["rows"][0]["outstanding"]) == D("3875.00")
    gst = client.get("/api/v1/reports/gst-summary", headers=h).json()
    assert D(gst["rows"][0]["cgst"]) == D("187.50")
    costing = client.get("/api/v1/reports/costing", headers=h).json()
    assert D(costing["rows"][0]["total"]) == D("5855.00")


def test_exports_and_pdf(client, auth, result):
    h = auth("accountant")
    csv = client.get("/api/v1/reports/sales-register?format=csv", headers=h)
    assert csv.status_code == 200 and "FF/" in csv.text and "7875" in csv.text
    x = client.get("/api/v1/reports/stock-summary?format=xlsx", headers=h)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    pdf = client.get(f"/api/v1/invoices/{result['invoice_id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    rc = client.get("/api/v1/payments/1/receipt", headers=h)
    assert rc.content.startswith(b"%PDF")


def test_audit_log_traceability(client, auth, result):
    rows = client.get("/api/v1/audit?entity_type=Invoice", headers=auth("accountant")).json()
    assert rows and rows[0]["action"] in ("POST", "DISPATCH", "CANCEL")


def test_ledger_source_documents(client, auth, result):
    led = client.get("/api/v1/stock-ledger", headers=auth("owner")).json()
    types = {r["type"] for r in led["rows"]}
    assert {"OPENING", "PURCHASE_RECEIPT", "PRODUCTION_ISSUE", "PACKAGING_CONSUMPTION", "PRODUCTION_OUTPUT", "SALES_DISPATCH"} <= types
    assert all(r["source"] and r["user"] for r in led["rows"])


def test_end_to_end_via_http_api(client, auth):
    """Drive the sales half of the benchmark purely through HTTP, as the real UI does."""
    a, s, p = auth("admin"), auth("salesman_a"), auth("production")
    cust = client.get("/api/v1/customers", headers=s).json()[0]
    prod = next(x for x in client.get("/api/v1/products", headers=s).json() if x["sku"] == "FG-MURUKKU200")
    items = {i["sku"]: i["id"] for i in client.get("/api/v1/inventory/items", headers=p).json()}
    r = client.post("/api/v1/production/runs", headers=p, json={
        "product_id": prod["id"], "batches": "1", "run_date": str(__import__("datetime").date.today()), "good_output": "188", "damaged_pouches": "6",
        "actual_usage": [{"item_id": items["RM-OIL"], "actual_quantity": "10.5"}, {"item_id": items["PK-CARTON"], "actual_quantity": "9"}]})
    assert r.status_code == 201, r.text
    o = client.post("/api/v1/orders", headers=s, json={"customer_id": cust["id"], "items": [{"product_id": prod["id"], "quantity": "150"}], "idempotency_key": "ui-1"})
    assert o.status_code == 201
    assert client.post(f"/api/v1/orders/{o.json()['id']}/approve", headers=a).status_code == 200
    inv = client.post(f"/api/v1/invoices/from-order/{o.json()['id']}", headers=a).json()
    assert inv["total"] == "7875.00"
    d = client.post("/api/v1/dispatches", headers=a, json={"invoice_id": inv["id"]})
    assert d.status_code == 201
    over = client.post("/api/v1/payments", headers=a, json={"customer_id": cust["id"], "invoice_id": inv["id"], "amount": "9000", "mode": "CASH"})
    assert over.status_code == 400
    ok = client.post("/api/v1/payments", headers=a, json={"customer_id": cust["id"], "invoice_id": inv["id"], "amount": "4000", "mode": "UPI", "reference": "X1"})
    assert ok.status_code == 201
    assert client.get(f"/api/v1/invoices/{inv['id']}", headers=a).json()["outstanding"] == "3875.00"
