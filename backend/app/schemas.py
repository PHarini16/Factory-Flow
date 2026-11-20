"""Pydantic v2 request/response schemas. Decimals serialise as strings in JSON (lossless)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["OWNER", "ADMIN", "SALESMAN", "PRODUCTION", "ACCOUNTANT"]
Pos = Field(gt=0)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


# ---- auth/users
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str | None = None
    role: str
    is_active: bool


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str
    email: str | None = None
    password: str = Field(min_length=8)
    role: Role


class UserPatch(BaseModel):
    full_name: str | None = None
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: Role | None = None
    is_active: bool | None = None


# ---- master data
class ProductIn(BaseModel):
    name: str
    category: str = ""
    sku: str
    pack_size: str = ""
    unit: str = "packet"
    hsn_code: str = "1905"
    gst_rate: Decimal = Field(default=Decimal("5"), ge=0, le=28)
    selling_price: Decimal = Field(ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True


class ProductPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    pack_size: str | None = None
    hsn_code: str | None = None
    gst_rate: Decimal | None = Field(default=None, ge=0, le=28)
    selling_price: Decimal | None = Field(default=None, ge=0)
    reorder_level: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(ORM):
    id: int
    name: str
    category: str
    sku: str
    pack_size: str
    unit: str
    hsn_code: str
    gst_rate: Decimal
    selling_price: Decimal
    reorder_level: Decimal
    is_active: bool
    inventory_item_id: int | None = None


class CustomerIn(BaseModel):
    name: str
    customer_type: Literal["RETAILER", "DISTRIBUTOR"] = "RETAILER"
    gstin: str | None = Field(default=None, max_length=15)
    billing_address: str = ""
    shipping_address: str = ""
    city: str = ""
    state: str = "Tamil Nadu"
    state_code: str = Field(default="33", min_length=2, max_length=2)
    phone: str | None = None
    email: str | None = None
    salesman_id: int | None = None
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    is_active: bool = True


class CustomerOut(CustomerIn, ORM):
    id: int


class SupplierIn(BaseModel):
    name: str
    contact: str | None = None
    gstin: str | None = Field(default=None, max_length=15)
    address: str = ""
    state: str = "Tamil Nadu"
    payment_terms: str = "30 days"
    is_active: bool = True


class SupplierOut(SupplierIn, ORM):
    id: int


class ItemIn(BaseModel):
    sku: str
    name: str
    item_type: Literal["RAW", "PACKAGING"]
    category: str = ""
    unit: Literal["kg", "g", "litre", "ml", "piece", "packet", "carton"]
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)


class ItemOut(ORM):
    id: int
    sku: str
    name: str
    item_type: str
    category: str
    unit: str
    reorder_level: Decimal
    avg_cost: Decimal
    valuation_method: str
    is_active: bool


class AdjustmentIn(BaseModel):
    item_id: int
    direction: Literal["IN", "OUT"]
    quantity: Decimal = Pos
    unit: str | None = None
    reason: str = Field(min_length=3)
    txn_date: date | None = None


# ---- purchases
class PurchaseLineIn(BaseModel):
    item_id: int
    quantity: Decimal = Pos
    unit: str | None = None
    rate: Decimal = Field(ge=0)


class PurchaseIn(BaseModel):
    supplier_id: int
    supplier_invoice_no: str = Field(min_length=1)
    purchase_date: date
    items: list[PurchaseLineIn] = Field(min_length=1)
    receive: bool = True
    idempotency_key: str | None = None


class PurchaseLineOut(ORM):
    item_id: int
    item: ItemOut
    quantity: Decimal
    unit: str
    rate: Decimal
    amount: Decimal


class PurchaseOut(ORM):
    id: int
    po_number: str
    supplier_id: int
    supplier: SupplierOut
    supplier_invoice_no: str
    purchase_date: date
    status: str
    total: Decimal
    items: list[PurchaseLineOut]


# ---- BOM / production
class BomLineIn(BaseModel):
    item_id: int
    quantity: Decimal = Pos
    unit: str | None = None
    is_primary_pack: bool = False


class BomIn(BaseModel):
    product_id: int
    batch_size: Decimal = Field(default=Decimal("1"), gt=0)
    expected_output: Decimal = Pos
    effective_date: date
    notes: str = ""
    items: list[BomLineIn] = Field(min_length=1)


class BomLineOut(ORM):
    item_id: int
    item: ItemOut
    quantity: Decimal
    unit: str
    is_primary_pack: bool


class BomOut(ORM):
    id: int
    product_id: int
    product: ProductOut
    version: int
    batch_size: Decimal
    expected_output: Decimal
    effective_date: date
    is_active: bool
    notes: str
    items: list[BomLineOut]


class PlanIn(BaseModel):
    product_id: int
    bom_id: int | None = None
    batches: Decimal = Pos


class UsageIn(BaseModel):
    item_id: int
    actual_quantity: Decimal = Field(ge=0)
    unit: str | None = None


class RunIn(BaseModel):
    product_id: int
    bom_id: int | None = None
    batches: Decimal = Pos
    run_date: date
    good_output: Decimal = Field(ge=0)
    damaged_packets: Decimal = Field(default=Decimal("0"), ge=0)
    damaged_pouches: Decimal = Field(default=Decimal("0"), ge=0)
    scrap_qty: Decimal = Field(default=Decimal("0"), ge=0)
    material_wastage: Decimal = Field(default=Decimal("0"), ge=0)
    actual_usage: list[UsageIn] = []
    remarks: str = ""
    idempotency_key: str | None = None


class OverheadIn(BaseModel):
    labour: Decimal = Field(default=Decimal("0"), ge=0)
    gas_power: Decimal = Field(default=Decimal("0"), ge=0)
    other: Decimal = Field(default=Decimal("0"), ge=0)


class UsageOut(ORM):
    item_id: int
    item: ItemOut
    standard_qty: Decimal
    actual_qty: Decimal
    unit: str
    unit_cost: Decimal
    cost: Decimal
    difference: Decimal
    variance_pct: Decimal
    alert: bool


class CostOut(ORM):
    material_cost: Decimal
    labour: Decimal
    gas_power: Decimal
    other_overhead: Decimal
    overhead_total: Decimal
    total_cost: Decimal
    cost_per_packet: Decimal
    selling_price: Decimal
    gross_profit_per_packet: Decimal
    gross_margin_pct: Decimal


class RunOut(ORM):
    id: int
    run_number: str
    product_id: int
    product: ProductOut
    bom_id: int
    run_date: date
    batches: Decimal
    status: str
    expected_output: Decimal
    good_output: Decimal
    damaged_packets: Decimal
    damaged_pouches: Decimal
    scrap_qty: Decimal
    material_wastage: Decimal
    yield_variance_pct: Decimal
    tolerance_pct: Decimal
    yield_alert: bool
    remarks: str
    usages: list[UsageOut]
    cost: CostOut | None = None


# ---- sales
class OrderLineIn(BaseModel):
    product_id: int
    quantity: Decimal = Pos
    unit_price: Decimal | None = Field(default=None, ge=0)  # honoured only for admin edits


class OrderIn(BaseModel):
    customer_id: int
    items: list[OrderLineIn] = Field(min_length=1)
    remarks: str = ""
    draft: bool = False
    idempotency_key: str | None = None


class OrderEditIn(BaseModel):
    items: list[OrderLineIn] = Field(min_length=1)
    reason: str = Field(min_length=3)


class ReasonIn(BaseModel):
    reason: str = ""


class OrderLineOut(ORM):
    id: int
    product_id: int
    product: ProductOut
    quantity: Decimal
    unit_price: Decimal


class OrderOut(ORM):
    id: int
    order_no: str
    customer_id: int
    customer: CustomerOut
    salesman_id: int
    status: str
    order_date: date
    remarks: str
    change_reason: str
    rejection_reason: str
    subtotal: Decimal
    tax_estimate: Decimal
    total_estimate: Decimal
    items: list[OrderLineOut]
    created_at: datetime


class InvoiceLineOut(ORM):
    id: int
    product_id: int
    description: str
    hsn_code: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    taxable_amount: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    dispatched_qty: Decimal
    returned_qty: Decimal


class InvoiceOut(ORM):
    id: int
    invoice_no: str
    financial_year: str
    invoice_date: date
    due_date: date
    order_id: int | None
    customer_id: int
    seller_name: str
    seller_gstin: str
    buyer_name: str
    buyer_gstin: str | None
    buyer_address: str
    place_of_supply: str
    place_of_supply_code: str
    is_interstate: bool
    taxable_amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    status: str
    dispatch_status: str
    cancel_reason: str
    items: list[InvoiceLineOut]
    paid: Decimal | None = None
    credited: Decimal | None = None
    outstanding: Decimal | None = None


class CreditLineIn(BaseModel):
    invoice_item_id: int
    quantity: Decimal = Pos


class CreditNoteIn(BaseModel):
    lines: list[CreditLineIn] = Field(min_length=1)
    reason: str = Field(min_length=3)
    restock: bool = False


class CreditNoteOut(ORM):
    id: int
    credit_note_no: str
    invoice_id: int
    note_date: date
    reason: str
    taxable_amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    restocked: bool


class DispatchLineIn(BaseModel):
    invoice_item_id: int
    quantity: Decimal = Pos


class DispatchIn(BaseModel):
    invoice_id: int
    lines: list[DispatchLineIn] | None = None  # omitted = dispatch all remaining
    remarks: str = ""
    vehicle_no: str = ""
    dispatch_date: date | None = None
    idempotency_key: str | None = None


class DispatchItemOut(ORM):
    invoice_item_id: int
    product_id: int
    quantity: Decimal


class DispatchOut(ORM):
    id: int
    dispatch_no: str
    invoice_id: int
    dispatch_date: date
    vehicle_no: str
    remarks: str
    items: list[DispatchItemOut]


class PaymentIn(BaseModel):
    customer_id: int
    invoice_id: int | None = None
    amount: Decimal = Pos
    mode: Literal["CASH", "UPI", "BANK", "CHEQUE"]
    payment_date: date | None = None
    reference: str = ""
    remarks: str = ""
    idempotency_key: str | None = None


class AllocationOut(ORM):
    invoice_id: int
    amount: Decimal


class PaymentOut(ORM):
    id: int
    receipt_no: str
    customer_id: int
    payment_date: date
    amount: Decimal
    mode: str
    reference: str
    remarks: str
    allocations: list[AllocationOut]
    customer: CustomerOut


class AuditOut(ORM):
    id: int
    username: str
    action: str
    entity_type: str
    entity_id: int | None
    old_values: dict | None
    new_values: dict | None
    created_at: datetime
