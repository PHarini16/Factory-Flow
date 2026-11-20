"""Sales orders, GST invoices, credit notes, dispatch and payments."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, DomainError, Forbidden, InsufficientStock, NotFound
from app.models import (CreditNote, Customer, Dispatch, DispatchItem, Invoice, InvoiceItem, Payment, PaymentAllocation,
                        Product, SalesOrder, SalesOrderItem, User)
from app.services import stock
from app.services.common import audit, financial_year, get_setting, next_number, q2
from app.services.gst import compute_line, is_interstate

ZERO = Decimal("0")


# ------------------------------------------------------------------ orders
def _build_items(db: Session, order: SalesOrder, items: list[dict], allow_price_override: bool) -> None:
    if not items:
        raise DomainError("An order needs at least one product")
    seen = set()
    order.items.clear()
    sub = tax = ZERO
    for it in items:
        p = db.get(Product, it["product_id"])
        if not p or not p.is_active:
            raise DomainError(f"Product {it['product_id']} not found or inactive")
        if p.id in seen:
            raise DomainError(f"{p.name} is listed twice")
        seen.add(p.id)
        qty = Decimal(str(it["quantity"]))
        if qty <= 0:
            raise DomainError("Quantities must be positive")
        price = Decimal(str(it["unit_price"])) if allow_price_override and it.get("unit_price") is not None else p.selling_price
        order.items.append(SalesOrderItem(product_id=p.id, quantity=qty, unit_price=price))
        taxable = q2(qty * price)
        sub += taxable
        tax += q2(taxable * p.gst_rate / 100)
    order.subtotal, order.tax_estimate, order.total_estimate = sub, tax, sub + tax


def create_order(db: Session, user: User, *, customer_id: int, items: list[dict], remarks: str = "",
                 idempotency_key: str | None = None, draft: bool = False, order_date: date | None = None) -> SalesOrder:
    if idempotency_key:
        ex = db.scalar(select(SalesOrder).where(SalesOrder.idempotency_key == idempotency_key))
        if ex:
            return ex
    cust = db.get(Customer, customer_id)
    if not cust or not cust.is_active:
        raise NotFound("Customer not found")
    if user.role == "SALESMAN" and cust.salesman_id != user.id:
        raise Forbidden("This customer is not assigned to you")
    d = order_date or date.today()
    o = SalesOrder(order_no=next_number(db, "ORD", d), customer_id=customer_id, salesman_id=cust.salesman_id or user.id if user.role != "SALESMAN" else user.id,
                   status="DRAFT" if draft else "SUBMITTED", order_date=d, remarks=remarks, idempotency_key=idempotency_key)
    _build_items(db, o, items, allow_price_override=False)
    db.add(o)
    db.flush()
    audit(db, user, "CREATE", "SalesOrder", o.id, new={"order_no": o.order_no, "total": o.total_estimate})
    db.commit()
    return o


def get_order(db: Session, order_id: int) -> SalesOrder:
    o = db.get(SalesOrder, order_id)
    if not o:
        raise NotFound("Order not found")
    return o


def stock_check(db: Session, order: SalesOrder) -> list[dict]:
    out = []
    for it in order.items:
        avail = stock.balance(db, it.product.inventory_item_id) if it.product.inventory_item_id else ZERO
        out.append({"product_id": it.product_id, "product": it.product.name, "requested": it.quantity, "available": avail,
                    "shortage": max(ZERO, it.quantity - avail), "sufficient": avail >= it.quantity})
    return out


def edit_order(db: Session, user: User, order_id: int, items: list[dict], reason: str) -> SalesOrder:
    o = get_order(db, order_id)
    if o.status not in ("SUBMITTED", "DRAFT"):
        raise Conflict(f"Order is {o.status}; only SUBMITTED orders can be edited")
    if not reason.strip():
        raise DomainError("A reason for the change is required")
    old = {"total": o.total_estimate, "items": [(i.product_id, i.quantity, i.unit_price) for i in o.items]}
    _build_items(db, o, items, allow_price_override=True)
    o.change_reason = reason
    audit(db, user, "EDIT", "SalesOrder", o.id, old=old,
          new={"total": o.total_estimate, "items": [(i.product_id, i.quantity, i.unit_price) for i in o.items], "reason": reason})
    db.commit()
    return o


def submit_order(db: Session, user: User, order_id: int) -> SalesOrder:
    o = get_order(db, order_id)
    if o.status != "DRAFT":
        raise Conflict("Only DRAFT orders can be submitted")
    if user.role == "SALESMAN" and o.salesman_id != user.id:
        raise Forbidden("Not your order")
    o.status = "SUBMITTED"
    audit(db, user, "SUBMIT", "SalesOrder", o.id)
    db.commit()
    return o


def decide_order(db: Session, user: User, order_id: int, approve: bool, reason: str = "") -> SalesOrder:
    o = get_order(db, order_id)
    if o.status != "SUBMITTED":
        raise Conflict(f"Order is {o.status}; only SUBMITTED orders can be approved or rejected")
    if not approve and not reason.strip():
        raise DomainError("A rejection reason is required")
    o.status = "APPROVED" if approve else "REJECTED"
    o.approved_by = user.id
    o.rejection_reason = "" if approve else reason
    audit(db, user, "APPROVE" if approve else "REJECT", "SalesOrder", o.id, new={"status": o.status, "reason": reason})
    db.commit()  # NOTE: no stock movement here - stock only changes on dispatch
    return o


def cancel_order(db: Session, user: User, order_id: int, reason: str) -> SalesOrder:
    o = get_order(db, order_id)
    if o.status not in ("DRAFT", "SUBMITTED", "APPROVED"):
        raise Conflict(f"Order is {o.status}; cancel the invoice instead")
    if user.role == "SALESMAN" and (o.salesman_id != user.id or o.status == "APPROVED"):
        raise Forbidden("You can only cancel your own un-approved orders")
    o.status = "CANCELLED"
    o.rejection_reason = reason
    audit(db, user, "CANCEL", "SalesOrder", o.id, new={"reason": reason})
    db.commit()
    return o


# ------------------------------------------------------------------ invoices
def outstanding(db: Session, inv: Invoice) -> dict:
    paid = sum((a.amount for a in db.scalars(select(PaymentAllocation).where(PaymentAllocation.invoice_id == inv.id))), ZERO)
    credits = sum((c.total for c in db.scalars(select(CreditNote).where(CreditNote.invoice_id == inv.id))), ZERO)
    out = inv.total - paid - credits
    return {"paid": paid, "credited": credits, "outstanding": out if inv.status != "CANCELLED" else ZERO}


def create_invoice(db: Session, user: User, order_id: int, invoice_date: date | None = None) -> Invoice:
    s = get_settings()
    o = get_order(db, order_id)
    if o.status != "APPROVED":
        raise Conflict(f"Order is {o.status}; only APPROVED orders can be invoiced")
    if db.scalar(select(Invoice).where(Invoice.order_id == o.id, Invoice.status == "POSTED")):
        raise Conflict("An invoice already exists for this order")
    c = o.customer
    d = invoice_date or date.today()
    inter = is_interstate(s.factory_state_code, c.state_code)
    inv = Invoice(invoice_no=next_number(db, "INV", d), financial_year=financial_year(d), invoice_date=d,
                  due_date=d + timedelta(days=c.payment_terms_days), order_id=o.id, customer_id=c.id, salesman_id=o.salesman_id,
                  seller_name=s.factory_name, seller_gstin=s.factory_gstin, seller_address=s.factory_address,
                  buyer_name=c.name, buyer_gstin=c.gstin, buyer_address=c.billing_address or c.city,
                  place_of_supply=c.state, place_of_supply_code=c.state_code, is_interstate=inter, created_by=user.id)
    tx = cg = sg = ig = ZERO
    for it in o.items:
        g = compute_line(it.quantity, it.unit_price, it.product.gst_rate, inter)
        inv.items.append(InvoiceItem(product_id=it.product_id, description=f"{it.product.name} {it.product.pack_size}".strip(),
                                     hsn_code=it.product.hsn_code, quantity=it.quantity, unit=it.product.unit,
                                     unit_price=it.unit_price, taxable_amount=g.taxable, gst_rate=it.product.gst_rate,
                                     cgst=g.cgst, sgst=g.sgst, igst=g.igst, total=g.total))
        tx, cg, sg, ig = tx + g.taxable, cg + g.cgst, sg + g.sgst, ig + g.igst
    inv.taxable_amount, inv.cgst, inv.sgst, inv.igst, inv.total = tx, cg, sg, ig, tx + cg + sg + ig
    db.add(inv)
    o.status = "INVOICED"
    db.flush()
    audit(db, user, "POST", "Invoice", inv.id, new={"invoice_no": inv.invoice_no, "total": inv.total})
    db.commit()
    return inv


def get_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise NotFound("Invoice not found")
    return inv


def _credit_note(db: Session, user: User, inv: Invoice, lines: list[tuple[InvoiceItem, Decimal]], reason: str, restock: bool) -> CreditNote:
    today = date.today()
    cn = CreditNote(credit_note_no=next_number(db, "CN", today), invoice_id=inv.id, note_date=today, reason=reason,
                    restocked=restock, created_by=user.id)
    tx = cg = sg = ig = ZERO
    for ii, qty in lines:
        g = compute_line(qty, ii.unit_price, ii.gst_rate, inv.is_interstate)
        tx, cg, sg, ig = tx + g.taxable, cg + g.cgst, sg + g.sgst, ig + g.igst
        ii.returned_qty += qty
        if restock:
            can = ii.dispatched_qty - ii.restocked_qty
            back = min(qty, can)
            if back > 0:
                stock.post_movement(db, item=ii.product.inventory_item, quantity=back, unit=None, direction="IN",
                                    movement_type="SALES_RETURN", txn_date=today, source_type="CreditNote", source_id=None,
                                    user=user, remarks=f"{cn.credit_note_no} return of {inv.invoice_no}")
                ii.restocked_qty += back
    cn.taxable_amount, cn.cgst, cn.sgst, cn.igst, cn.total = tx, cg, sg, ig, tx + cg + sg + ig
    db.add(cn)
    db.flush()
    return cn


def issue_credit_note(db: Session, user: User, invoice_id: int, lines: list[dict], reason: str, restock: bool) -> CreditNote:
    inv = get_invoice(db, invoice_id)
    if inv.status != "POSTED":
        raise Conflict("Credit notes can only be raised against POSTED invoices")
    if not reason.strip():
        raise DomainError("A reason is required")
    by_id = {i.id: i for i in inv.items}
    resolved = []
    for ln in lines:
        ii = by_id.get(ln["invoice_item_id"])
        qty = Decimal(str(ln["quantity"]))
        if not ii:
            raise DomainError("Invoice item not on this invoice")
        if qty <= 0 or qty > ii.quantity - ii.returned_qty:
            raise DomainError(f"Credit quantity for {ii.description} exceeds the creditable {ii.quantity - ii.returned_qty}")
        resolved.append((ii, qty))
    if not resolved:
        raise DomainError("No lines supplied")
    cn = _credit_note(db, user, inv, resolved, reason, restock)
    if outstanding(db, inv)["outstanding"] < 0:
        raise Conflict("Credit exceeds outstanding balance; refunds/advances are not supported in this prototype")
    audit(db, user, "CREDIT_NOTE", "Invoice", inv.id, new={"credit_note": cn.credit_note_no, "total": cn.total, "reason": reason})
    db.commit()
    return cn


def cancel_invoice(db: Session, user: User, invoice_id: int, reason: str) -> Invoice:
    inv = get_invoice(db, invoice_id)
    if inv.status != "POSTED":
        raise Conflict("Invoice is already cancelled")
    if not reason.strip():
        raise DomainError("A cancellation reason is required")
    if db.scalar(select(func.count(PaymentAllocation.id)).where(PaymentAllocation.invoice_id == inv.id)):
        raise Conflict("Payments are allocated to this invoice; reverse them before cancelling")
    lines = [(i, i.quantity - i.returned_qty) for i in inv.items if i.quantity - i.returned_qty > 0]
    if lines:
        cn = _credit_note(db, user, inv, lines, f"Invoice cancelled: {reason}", restock=True)
    inv.status = "CANCELLED"
    inv.cancel_reason = reason
    if inv.order_id:
        db.get(SalesOrder, inv.order_id).status = "CANCELLED"
    audit(db, user, "CANCEL", "Invoice", inv.id, new={"reason": reason})
    db.commit()
    return inv


# ------------------------------------------------------------------ dispatch
def create_dispatch(db: Session, user: User, *, invoice_id: int, lines: list[dict] | None, remarks: str = "",
                    vehicle_no: str = "", dispatch_date: date | None = None, idempotency_key: str | None = None) -> Dispatch:
    if idempotency_key:
        ex = db.scalar(select(Dispatch).where(Dispatch.idempotency_key == idempotency_key))
        if ex:
            return ex
    inv = get_invoice(db, invoice_id)
    if inv.status != "POSTED":
        raise Conflict("Only POSTED invoices can be dispatched")
    d = dispatch_date or date.today()
    remaining = {i.id: i.quantity - i.returned_qty - i.dispatched_qty for i in inv.items}
    by_id = {i.id: i for i in inv.items}
    if not lines:
        lines = [{"invoice_item_id": k, "quantity": v} for k, v in remaining.items() if v > 0]
    want: dict[int, Decimal] = {}
    for ln in lines:
        qty = Decimal(str(ln["quantity"]))
        iid = ln["invoice_item_id"]
        if iid not in by_id:
            raise DomainError("Invoice item not on this invoice")
        if qty <= 0:
            raise DomainError("Dispatch quantity must be positive")
        want[iid] = want.get(iid, ZERO) + qty
        if want[iid] > remaining[iid]:
            raise DomainError(f"Cannot dispatch {want[iid]} of {by_id[iid].description}; only {remaining[iid]} remain on the invoice")
    if not want:
        raise Conflict("Nothing left to dispatch on this invoice")
    # stock validation - collect ALL shortages before failing
    shortages = []
    for iid, qty in want.items():
        pr = by_id[iid].product
        avail = stock.balance(db, pr.inventory_item_id)
        if avail < qty:
            shortages.append({"product": pr.name, "requested": str(qty), "available": str(avail), "shortage": str(qty - avail)})
    if shortages:
        raise InsufficientStock("Insufficient finished-goods stock for dispatch: " + "; ".join(
            f"{s['product']} requested {s['requested']}, available {s['available']}, short {s['shortage']}" for s in shortages),
            {"shortages": shortages})
    partial = any(want.get(i, ZERO) < r for i, r in remaining.items() if r > 0)
    if partial:
        if get_setting(db, "allow_partial_dispatch", "true") != "true":
            raise Conflict("Partial dispatch is disabled; dispatch the full remaining quantity")
        if not remarks.strip():
            raise DomainError("Partial dispatch must be documented: please enter remarks")
    dsp = Dispatch(dispatch_no=next_number(db, "DSP", d), invoice_id=inv.id, dispatch_date=d, vehicle_no=vehicle_no,
                   remarks=remarks, idempotency_key=idempotency_key, created_by=user.id)
    db.add(dsp)
    db.flush()
    for iid, qty in want.items():
        ii = by_id[iid]
        stock.post_movement(db, item=ii.product.inventory_item, quantity=qty, unit=None, direction="OUT",
                            movement_type="SALES_DISPATCH", txn_date=d, source_type="Dispatch", source_id=dsp.id, user=user,
                            remarks=f"{dsp.dispatch_no} / {inv.invoice_no}")
        ii.dispatched_qty += qty
        dsp.items.append(DispatchItem(invoice_item_id=iid, product_id=ii.product_id, quantity=qty))
    done = all(i.quantity - i.returned_qty - i.dispatched_qty <= 0 for i in inv.items)
    inv.dispatch_status = "DISPATCHED" if done else "PARTIAL"
    if inv.order_id:
        db.get(SalesOrder, inv.order_id).status = "DISPATCHED" if done else "PARTIALLY_DISPATCHED"
    audit(db, user, "DISPATCH", "Dispatch", dsp.id, new={"dispatch_no": dsp.dispatch_no, "invoice": inv.invoice_no,
                                                         "quantities": {str(k): v for k, v in want.items()}})
    db.commit()
    return dsp


# ------------------------------------------------------------------ payments
def record_payment(db: Session, user: User, *, customer_id: int, amount: Decimal, mode: str, payment_date: date | None = None,
                   reference: str = "", remarks: str = "", invoice_id: int | None = None,
                   idempotency_key: str | None = None) -> Payment:
    if idempotency_key:
        ex = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if ex:
            return ex
    amount = q2(Decimal(str(amount)))
    if amount <= 0:
        raise DomainError("Payment amount must be positive")
    if mode not in ("CASH", "UPI", "BANK", "CHEQUE"):
        raise DomainError("Payment mode must be CASH, UPI, BANK or CHEQUE")
    cust = db.get(Customer, customer_id)
    if not cust:
        raise NotFound("Customer not found")
    if reference and db.scalar(select(Payment).where(Payment.customer_id == customer_id, Payment.mode == mode, Payment.reference == reference)):
        raise Conflict(f"A {mode} payment with reference {reference} is already recorded (duplicate prevented)")
    d = payment_date or date.today()
    if invoice_id:
        targets = [get_invoice(db, invoice_id)]
    else:  # oldest-first allocation
        targets = list(db.scalars(select(Invoice).where(Invoice.customer_id == customer_id, Invoice.status == "POSTED").order_by(Invoice.invoice_date, Invoice.id)))
    pay = Payment(receipt_no=next_number(db, "RCPT", d), customer_id=customer_id, payment_date=d, amount=amount, mode=mode,
                  reference=reference, remarks=remarks, idempotency_key=idempotency_key, created_by=user.id)
    left = amount
    for inv in targets:
        if inv.customer_id != customer_id:
            raise DomainError("Invoice belongs to a different customer")
        if inv.status != "POSTED":
            raise Conflict("Invoice is not POSTED")
        due = outstanding(db, inv)["outstanding"]
        if due <= 0:
            continue
        take = min(left, due)
        if invoice_id and amount > due:
            raise DomainError(f"Payment {amount} exceeds outstanding {due} on {inv.invoice_no}; advance payments are not supported")
        pay.allocations.append(PaymentAllocation(invoice_id=inv.id, amount=take))
        left -= take
        if left <= 0:
            break
    if left > 0:
        raise DomainError(f"Payment exceeds total outstanding by {left}; advance payments are not supported")
    db.add(pay)
    db.flush()
    audit(db, user, "RECORD", "Payment", pay.id, new={"receipt": pay.receipt_no, "amount": amount})
    db.commit()
    return pay
