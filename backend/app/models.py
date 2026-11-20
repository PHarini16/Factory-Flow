"""SQLAlchemy 2.x models for FactoryFlow.

Money and quantities use DecimalString (exact decimal text) - never floats.
The stock ledger (StockMovement) is append-only: updates/deletes are blocked by
ORM event listeners at the bottom of this file.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.types import DecimalString

ZERO = Decimal("0")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------- auth
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_obj: Mapped[Role] = relationship(lazy="joined")

    @property
    def role(self) -> str:
        return self.role_obj.name


# --------------------------------------------------------------------------- master data
class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    customer_type: Mapped[str] = mapped_column(String(20), default="RETAILER")  # RETAILER | DISTRIBUTOR
    gstin: Mapped[str | None] = mapped_column(String(15))
    billing_address: Mapped[str] = mapped_column(String(250), default="")
    shipping_address: Mapped[str] = mapped_column(String(250), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(60), default="Tamil Nadu")
    state_code: Mapped[str] = mapped_column(String(2), default="33")
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    salesman_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    credit_limit: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    contact: Mapped[str | None] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15))
    address: Mapped[str] = mapped_column(String(250), default="")
    state: Mapped[str] = mapped_column(String(60), default="Tamil Nadu")
    payment_terms: Mapped[str] = mapped_column(String(80), default="30 days")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryItem(Base, TimestampMixin):
    """Anything that has stock: RAW, PACKAGING or FINISHED. Stock lives in the ledger."""
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    item_type: Mapped[str] = mapped_column(String(12), index=True)  # RAW | PACKAGING | FINISHED
    category: Mapped[str] = mapped_column(String(60), default="")
    unit: Mapped[str] = mapped_column(String(10))  # stock-keeping unit
    reorder_level: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    valuation_method: Mapped[str] = mapped_column(String(20), default="WEIGHTED_AVG")
    avg_cost: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)  # running weighted-average rate
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="")
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    pack_size: Mapped[str] = mapped_column(String(30), default="")
    unit: Mapped[str] = mapped_column(String(10), default="packet")
    hsn_code: Mapped[str] = mapped_column(String(10), default="1905")
    gst_rate: Mapped[Decimal] = mapped_column(DecimalString, default=Decimal("5"))
    selling_price: Mapped[Decimal] = mapped_column(DecimalString)
    reorder_level: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    inventory_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"))
    inventory_item: Mapped[InventoryItem | None] = relationship(lazy="joined")


# --------------------------------------------------------------------------- stock ledger
class StockMovement(Base):
    """Immutable stock ledger. quantity is always positive, in the item's own unit."""
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(DecimalString)
    unit: Mapped[str] = mapped_column(String(10))
    direction: Mapped[str] = mapped_column(String(3))  # IN | OUT
    movement_type: Mapped[str] = mapped_column(String(25), index=True)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    remarks: Mapped[str] = mapped_column(String(250), default="")
    unit_cost: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)  # rate applied to this movement
    value: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)  # quantity * unit_cost
    item: Mapped[InventoryItem] = relationship(lazy="joined")
    __table_args__ = (Index("ix_sm_source", "source_type", "source_id"),)


# --------------------------------------------------------------------------- purchasing
class Purchase(Base, TimestampMixin):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    supplier_invoice_no: Mapped[str] = mapped_column(String(50))
    purchase_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="ORDERED")  # ORDERED | RECEIVED | CANCELLED
    total: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    supplier: Mapped[Supplier] = relationship(lazy="joined")
    items: Mapped[list["PurchaseItem"]] = relationship(back_populates="purchase", cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (UniqueConstraint("supplier_id", "supplier_invoice_no", name="uq_supplier_invoice"),)


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    quantity: Mapped[Decimal] = mapped_column(DecimalString)
    unit: Mapped[str] = mapped_column(String(10))
    rate: Mapped[Decimal] = mapped_column(DecimalString)  # per entered unit
    amount: Mapped[Decimal] = mapped_column(DecimalString)
    purchase: Mapped[Purchase] = relationship(back_populates="items")
    item: Mapped[InventoryItem] = relationship(lazy="joined")


# --------------------------------------------------------------------------- BOM + production
class BOM(Base, TimestampMixin):
    __tablename__ = "boms"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    batch_size: Mapped[Decimal] = mapped_column(DecimalString, default=Decimal("1"))
    expected_output: Mapped[Decimal] = mapped_column(DecimalString)  # finished units per batch
    effective_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(250), default="")
    product: Mapped[Product] = relationship(lazy="joined")
    items: Mapped[list["BOMItem"]] = relationship(back_populates="bom", cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (UniqueConstraint("product_id", "version", name="uq_bom_version"),)


class BOMItem(Base):
    __tablename__ = "bom_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    quantity: Mapped[Decimal] = mapped_column(DecimalString)  # standard qty per batch
    unit: Mapped[str] = mapped_column(String(10))
    is_primary_pack: Mapped[bool] = mapped_column(Boolean, default=False)  # the pouch: 1 per packet produced
    bom: Mapped[BOM] = relationship(back_populates="items")
    item: Mapped[InventoryItem] = relationship(lazy="joined")


class ProductionRun(Base, TimestampMixin):
    __tablename__ = "production_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_number: Mapped[str] = mapped_column(String(30), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id"))
    run_date: Mapped[date] = mapped_column(Date)
    batches: Mapped[Decimal] = mapped_column(DecimalString)
    status: Mapped[str] = mapped_column(String(12), default="COMPLETED")
    expected_output: Mapped[Decimal] = mapped_column(DecimalString)
    good_output: Mapped[Decimal] = mapped_column(DecimalString)
    damaged_packets: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    damaged_pouches: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    scrap_qty: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    material_wastage: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    yield_variance_pct: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    tolerance_pct: Mapped[Decimal] = mapped_column(DecimalString, default=Decimal("3"))
    yield_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    remarks: Mapped[str] = mapped_column(String(250), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    product: Mapped[Product] = relationship(lazy="joined")
    bom: Mapped[BOM] = relationship(lazy="joined")
    usages: Mapped[list["ProductionMaterialUsage"]] = relationship(back_populates="run", cascade="all, delete-orphan", lazy="selectin")
    cost: Mapped["ProductionCost | None"] = relationship(back_populates="run", uselist=False, lazy="joined")


class ProductionMaterialUsage(Base):
    __tablename__ = "production_material_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("production_runs.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    standard_qty: Mapped[Decimal] = mapped_column(DecimalString)
    actual_qty: Mapped[Decimal] = mapped_column(DecimalString)
    unit: Mapped[str] = mapped_column(String(10))  # item stock unit
    unit_cost: Mapped[Decimal] = mapped_column(DecimalString)  # weighted-average rate at consumption
    cost: Mapped[Decimal] = mapped_column(DecimalString)
    difference: Mapped[Decimal] = mapped_column(DecimalString)
    variance_pct: Mapped[Decimal] = mapped_column(DecimalString)
    alert: Mapped[bool] = mapped_column(Boolean, default=False)
    run: Mapped[ProductionRun] = relationship(back_populates="usages")
    item: Mapped[InventoryItem] = relationship(lazy="joined")


class ProductionCost(Base, TimestampMixin):
    __tablename__ = "production_costs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("production_runs.id"), unique=True)
    material_cost: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)  # raw + packaging
    labour: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    gas_power: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    other_overhead: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    overhead_total: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    total_cost: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    cost_per_packet: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    selling_price: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    gross_profit_per_packet: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    gross_margin_pct: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    run: Mapped[ProductionRun] = relationship(back_populates="cost")


# --------------------------------------------------------------------------- sales
class SalesOrder(Base, TimestampMixin):
    __tablename__ = "sales_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    salesman_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(25), default="SUBMITTED", index=True)
    order_date: Mapped[date] = mapped_column(Date)
    remarks: Mapped[str] = mapped_column(String(250), default="")
    change_reason: Mapped[str] = mapped_column(String(250), default="")
    rejection_reason: Mapped[str] = mapped_column(String(250), default="")
    subtotal: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    tax_estimate: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    total_estimate: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    customer: Mapped[Customer] = relationship(lazy="joined")
    salesman: Mapped[User] = relationship(foreign_keys=[salesman_id], lazy="joined")
    items: Mapped[list["SalesOrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(DecimalString)
    unit_price: Mapped[Decimal] = mapped_column(DecimalString)
    order: Mapped[SalesOrder] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


class InvoiceSequence(Base):
    __tablename__ = "invoice_sequences"
    id: Mapped[int] = mapped_column(primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10))  # INV | CN | DSP | RCPT | PO | RUN | ORD
    financial_year: Mapped[str] = mapped_column(String(10), default="")
    last_number: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("prefix", "financial_year", name="uq_seq"),)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_no: Mapped[str] = mapped_column(String(30), unique=True)
    financial_year: Mapped[str] = mapped_column(String(10))
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    salesman_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # immutable snapshots of seller/buyer at posting time
    seller_name: Mapped[str] = mapped_column(String(120))
    seller_gstin: Mapped[str] = mapped_column(String(15))
    seller_address: Mapped[str] = mapped_column(String(250))
    buyer_name: Mapped[str] = mapped_column(String(120))
    buyer_gstin: Mapped[str | None] = mapped_column(String(15))
    buyer_address: Mapped[str] = mapped_column(String(250))
    place_of_supply: Mapped[str] = mapped_column(String(60))
    place_of_supply_code: Mapped[str] = mapped_column(String(2))
    is_interstate: Mapped[bool] = mapped_column(Boolean, default=False)
    taxable_amount: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    cgst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    sgst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    igst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    total: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    status: Mapped[str] = mapped_column(String(12), default="POSTED")  # POSTED | CANCELLED
    dispatch_status: Mapped[str] = mapped_column(String(15), default="NOT_DISPATCHED")  # NOT_DISPATCHED | PARTIAL | DISPATCHED
    cancel_reason: Mapped[str] = mapped_column(String(250), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    customer: Mapped[Customer] = relationship(lazy="joined")
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (Index("ix_invoice_order", "order_id"),)


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    description: Mapped[str] = mapped_column(String(200))
    hsn_code: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(DecimalString)
    unit: Mapped[str] = mapped_column(String(10), default="packet")
    unit_price: Mapped[Decimal] = mapped_column(DecimalString)
    taxable_amount: Mapped[Decimal] = mapped_column(DecimalString)
    gst_rate: Mapped[Decimal] = mapped_column(DecimalString)
    cgst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    sgst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    igst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    total: Mapped[Decimal] = mapped_column(DecimalString)
    dispatched_qty: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    returned_qty: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)  # quantity covered by credit notes
    restocked_qty: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)  # quantity returned to stock
    invoice: Mapped[Invoice] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


class CreditNote(Base, TimestampMixin):
    __tablename__ = "credit_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    credit_note_no: Mapped[str] = mapped_column(String(30), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    note_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(250))
    taxable_amount: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    cgst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    sgst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    igst: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    total: Mapped[Decimal] = mapped_column(DecimalString, default=ZERO)
    restocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    invoice: Mapped[Invoice] = relationship(lazy="joined")


class Dispatch(Base, TimestampMixin):
    __tablename__ = "dispatches"
    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_no: Mapped[str] = mapped_column(String(30), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    dispatch_date: Mapped[date] = mapped_column(Date)
    vehicle_no: Mapped[str] = mapped_column(String(30), default="")
    remarks: Mapped[str] = mapped_column(String(250), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    invoice: Mapped[Invoice] = relationship(lazy="joined")
    items: Mapped[list["DispatchItem"]] = relationship(back_populates="dispatch", cascade="all, delete-orphan", lazy="selectin")


class DispatchItem(Base):
    __tablename__ = "dispatch_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id"))
    invoice_item_id: Mapped[int] = mapped_column(ForeignKey("invoice_items.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(DecimalString)
    dispatch: Mapped[Dispatch] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(DecimalString)
    mode: Mapped[str] = mapped_column(String(15))  # CASH | UPI | BANK | CHEQUE
    reference: Mapped[str] = mapped_column(String(60), default="")
    remarks: Mapped[str] = mapped_column(String(250), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    customer: Mapped[Customer] = relationship(lazy="joined")
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="payment", cascade="all, delete-orphan", lazy="selectin")


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(DecimalString)
    payment: Mapped[Payment] = relationship(back_populates="allocations")


# --------------------------------------------------------------------------- audit & settings
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(50), default="system")
    action: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    old_values: Mapped[dict | None] = mapped_column(JSON)
    new_values: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(String(250), default="")


# --------------------------------------------------------------------------- ledger immutability
@event.listens_for(StockMovement, "before_update")
def _block_update(mapper, connection, target):  # pragma: no cover - trivial
    raise RuntimeError("StockMovement ledger rows are immutable")


@event.listens_for(StockMovement, "before_delete")
def _block_delete(mapper, connection, target):  # pragma: no cover - trivial
    raise RuntimeError("StockMovement ledger rows cannot be deleted")
