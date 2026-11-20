from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, DomainError, Forbidden, InsufficientStock
from app.models import Customer, Invoice
from app.services import sales, stock

D = Decimal


@pytest.fixture()
def custs(db):
    return {c.name.split(" - ")[0]: c for c in db.scalars(select(Customer))}


def _approved_invoice(db, users, custs, murukku, qty="30", cust="Retailer A", salesman="salesman_a"):
    o = sales.create_order(db, users[salesman], customer_id=custs[cust].id, items=[{"product_id": murukku.id, "quantity": D(qty)}])
    sales.decide_order(db, users["admin"], o.id, True)
    return o, sales.create_invoice(db, users["admin"], o.id)


def test_order_submission_does_not_touch_stock(db, users, custs, murukku):
    o = sales.create_order(db, users["salesman_a"], customer_id=custs["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("40")}])
    assert o.status == "SUBMITTED" and o.subtotal == D("2000.00") and o.tax_estimate == D("100.00")
    sales.decide_order(db, users["admin"], o.id, True)
    assert stock.balance(db, murukku.inventory_item_id) == D("50")


def test_salesman_cannot_order_for_unassigned_customer(db, users, custs, murukku):
    with pytest.raises(Forbidden):
        sales.create_order(db, users["salesman_a"], customer_id=custs["Distributor B"].id, items=[{"product_id": murukku.id, "quantity": D("1")}])


def test_salesman_price_override_ignored(db, users, custs, murukku):
    o = sales.create_order(db, users["salesman_a"], customer_id=custs["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("2"), "unit_price": D("1")}])
    assert o.items[0].unit_price == D("50")


def test_order_idempotency(db, users, custs, murukku):
    a = sales.create_order(db, users["salesman_a"], customer_id=custs["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("2")}], idempotency_key="k1")
    b = sales.create_order(db, users["salesman_a"], customer_id=custs["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("2")}], idempotency_key="k1")
    assert a.id == b.id


def test_edit_requires_reason_and_is_audited(db, users, custs, murukku):
    o = sales.create_order(db, users["salesman_a"], customer_id=custs["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("10")}])
    with pytest.raises(DomainError):
        sales.edit_order(db, users["admin"], o.id, [{"product_id": murukku.id, "quantity": D("5")}], " ")
    sales.edit_order(db, users["admin"], o.id, [{"product_id": murukku.id, "quantity": D("5"), "unit_price": D("48")}], "Price agreed on phone")
    assert o.subtotal == D("240.00") and o.change_reason == "Price agreed on phone"


def test_reject_needs_reason_and_blocks_invoice(db, users, custs, murukku):
    o = sales.create_order(db, users["salesman_a"], customer_id=custs["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("10")}])
    with pytest.raises(DomainError):
        sales.decide_order(db, users["admin"], o.id, False, "")
    sales.decide_order(db, users["admin"], o.id, False, "Credit limit")
    with pytest.raises(Conflict):
        sales.create_invoice(db, users["admin"], o.id)


def test_invoice_intra_state_and_numbering(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "150" if False else "30")
    assert inv.invoice_no.startswith("FF/") and inv.invoice_no.endswith("/0001")
    assert inv.is_interstate is False and inv.cgst == inv.sgst == D("37.50") and inv.igst == 0 and inv.total == D("1575.00")


def test_invoice_interstate_igst(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "10", "Distributor B", "salesman_b")
    assert inv.is_interstate and inv.igst == D("25.00") and inv.cgst == 0 and inv.total == D("525.00") and inv.place_of_supply == "Karnataka"


def test_second_invoice_for_same_order_blocked(db, users, custs, murukku):
    o, _ = _approved_invoice(db, users, custs, murukku)
    with pytest.raises(Conflict):
        sales.create_invoice(db, users["admin"], o.id)


def test_dispatch_deducts_stock_and_updates_status(db, users, custs, murukku):
    o, inv = _approved_invoice(db, users, custs, murukku, "30")
    sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None)
    assert stock.balance(db, murukku.inventory_item_id) == D("20")
    assert inv.dispatch_status == "DISPATCHED" and o.status == "DISPATCHED"


def test_insufficient_stock_blocks_dispatch(db, users, custs, murukku):
    o, inv = _approved_invoice(db, users, custs, murukku, "120", "Distributor B", "salesman_b")
    with pytest.raises(InsufficientStock) as e:
        sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None)
    db.rollback()
    sh = e.value.detail["shortages"][0]
    assert (sh["requested"], sh["available"], sh["shortage"]) == ("120", "50", "70")
    assert stock.balance(db, murukku.inventory_item_id) == D("50")  # no silent negative stock


def test_partial_dispatch_requires_remarks_then_completes(db, users, custs, murukku):
    o, inv = _approved_invoice(db, users, custs, murukku, "40")
    line = inv.items[0].id
    with pytest.raises(DomainError):
        sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=[{"invoice_item_id": line, "quantity": D("10")}])
    db.rollback()
    sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=[{"invoice_item_id": line, "quantity": D("10")}], remarks="Rest pending production")
    assert inv.dispatch_status == "PARTIAL" and o.status == "PARTIALLY_DISPATCHED"
    with pytest.raises(DomainError):
        sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=[{"invoice_item_id": line, "quantity": D("31")}])
    db.rollback()
    sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None)
    assert inv.dispatch_status == "DISPATCHED" and stock.balance(db, murukku.inventory_item_id) == D("10")


def test_dispatch_idempotent(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "30")
    a = sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None, idempotency_key="d1")
    b = sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None, idempotency_key="d1")
    assert a.id == b.id and stock.balance(db, murukku.inventory_item_id) == D("20")


def test_partial_payments_and_outstanding(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "30")  # total 1575
    sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("500"), mode="CASH")
    sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("100"), mode="UPI", reference="U1")
    assert sales.outstanding(db, inv)["outstanding"] == D("975.00")


def test_overpayment_rejected(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "30")
    with pytest.raises(DomainError):
        sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("1575.01"), mode="CASH")


def test_duplicate_payment_reference_and_key_blocked(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "30")
    sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("100"), mode="UPI", reference="TX9", idempotency_key="p1")
    with pytest.raises(Conflict):
        sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("100"), mode="UPI", reference="TX9")
    again = sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("100"), mode="UPI", reference="TX10", idempotency_key="p1")
    assert again.reference == "TX9"
    assert sales.outstanding(db, inv)["paid"] == D("100")


def test_fifo_allocation_without_invoice(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "10")
    p = sales.record_payment(db, users["admin"], customer_id=inv.customer_id, amount=D("100"), mode="CASH")
    assert p.allocations[0].invoice_id == inv.id


def test_partial_credit_note_with_restock(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "30")
    sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None)
    cn = sales.issue_credit_note(db, users["admin"], inv.id, [{"invoice_item_id": inv.items[0].id, "quantity": D("10")}], "Damaged in transit", True)
    assert cn.total == D("525.00") and stock.balance(db, murukku.inventory_item_id) == D("30")
    assert sales.outstanding(db, inv)["outstanding"] == D("1050.00")
    with pytest.raises(DomainError):
        sales.issue_credit_note(db, users["admin"], inv.id, [{"invoice_item_id": inv.items[0].id, "quantity": D("21")}], "too many", False)


def test_invoice_cancellation_returns_stock_and_issues_credit_note(db, users, custs, murukku):
    o, inv = _approved_invoice(db, users, custs, murukku, "30")
    sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None)
    sales.cancel_invoice(db, users["admin"], inv.id, "Wrong customer")
    assert inv.status == "CANCELLED" and stock.balance(db, murukku.inventory_item_id) == D("50")
    assert sales.outstanding(db, inv)["outstanding"] == 0 and o.status == "CANCELLED"
    with pytest.raises(Conflict):
        sales.create_dispatch(db, users["admin"], invoice_id=inv.id, lines=None)


def test_cancel_blocked_when_payments_exist(db, users, custs, murukku):
    _, inv = _approved_invoice(db, users, custs, murukku, "30")
    sales.record_payment(db, users["admin"], customer_id=inv.customer_id, invoice_id=inv.id, amount=D("10"), mode="CASH")
    with pytest.raises(Conflict):
        sales.cancel_invoice(db, users["admin"], inv.id, "oops")


def test_posted_invoices_have_no_edit_or_delete_api(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p, ops in paths.items():
        if p.startswith("/api/v1/invoices"):
            assert not ({"put", "patch", "delete"} & set(ops)), p
