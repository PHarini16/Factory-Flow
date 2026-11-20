"""Products, customers, suppliers, inventory items, stock ledger, purchases, BOM."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Conflict, NotFound
from app.deps import ALL, FIN_READ, OPS_READ, get_current_user, require_roles
from app.models import BOM, Customer, InventoryItem, Product, StockMovement, Supplier, User
from app.schemas import (AdjustmentIn, BomIn, BomOut, CustomerIn, CustomerOut, ItemIn, ItemOut, ProductIn, ProductOut, ProductPatch,
                         PurchaseIn, PurchaseOut, SupplierIn, SupplierOut)
from app.services import production as prod_svc, purchase as pur_svc, reports, stock
from app.services.common import audit, jsonable

products = APIRouter(prefix="/products", tags=["products"])
customers = APIRouter(prefix="/customers", tags=["customers"])
suppliers = APIRouter(prefix="/suppliers", tags=["suppliers"])
inventory = APIRouter(prefix="/inventory", tags=["inventory"])
ledger = APIRouter(prefix="/stock-ledger", tags=["stock-ledger"])
purchases = APIRouter(prefix="/purchases", tags=["purchases"])
bom = APIRouter(prefix="/bom", tags=["bom"])

ADMIN = require_roles("ADMIN")


def _search(stmt, model, q, *cols):
    if q:
        stmt = stmt.where(or_(*[c.ilike(f"%{q}%") for c in cols]))
    return stmt


# ------------------------------------------------ products
@products.get("", response_model=list[ProductOut])
def list_products(q: str | None = None, active: bool | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = _search(select(Product).order_by(Product.name), Product, q, Product.name, Product.sku)
    if active is not None:
        stmt = stmt.where(Product.is_active == active)
    return list(db.scalars(stmt))


@products.post("", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    if db.scalar(select(Product).where(Product.sku == body.sku)):
        raise Conflict("SKU already exists")
    fg = InventoryItem(sku=body.sku, name=f"{body.name} {body.pack_size}".strip(), item_type="FINISHED", category=body.category,
                       unit="packet", reorder_level=body.reorder_level)
    db.add(fg)
    db.flush()
    p = Product(**body.model_dump(), inventory_item_id=fg.id)
    db.add(p)
    db.flush()
    audit(db, user, "CREATE", "Product", p.id, new=body.model_dump())
    db.commit()
    return p


@products.patch("/{pid}", response_model=ProductOut)
def update_product(pid: int, body: ProductPatch, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    p = db.get(Product, pid)
    if not p:
        raise NotFound("Product not found")
    data = body.model_dump(exclude_unset=True)
    audit(db, user, "UPDATE", "Product", p.id, old={k: getattr(p, k) for k in data}, new=data)
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    return p


# ------------------------------------------------ customers
@customers.get("", response_model=list[CustomerOut])
def list_customers(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_roles(*ALL))):
    stmt = _search(select(Customer).order_by(Customer.name), Customer, q, Customer.name, Customer.city)
    if user.role == "SALESMAN":
        stmt = stmt.where(Customer.salesman_id == user.id, Customer.is_active.is_(True))
    elif user.role == "PRODUCTION":
        return []
    return list(db.scalars(stmt))


@customers.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    c = Customer(**body.model_dump())
    db.add(c)
    db.flush()
    audit(db, user, "CREATE", "Customer", c.id, new=body.model_dump())
    db.commit()
    return c


@customers.put("/{cid}", response_model=CustomerOut)
def update_customer(cid: int, body: CustomerIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    c = db.get(Customer, cid)
    if not c:
        raise NotFound("Customer not found")
    old = {k: getattr(c, k) for k in body.model_dump()}
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, user, "UPDATE", "Customer", c.id, old=old, new=body.model_dump())
    db.commit()
    return c


# ------------------------------------------------ suppliers
@suppliers.get("", response_model=list[SupplierOut])
def list_suppliers(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    return list(db.scalars(_search(select(Supplier).order_by(Supplier.name), Supplier, q, Supplier.name)))


@suppliers.post("", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    if db.scalar(select(Supplier).where(Supplier.name == body.name)):
        raise Conflict("Supplier already exists")
    s = Supplier(**body.model_dump())
    db.add(s)
    db.flush()
    audit(db, user, "CREATE", "Supplier", s.id, new=body.model_dump())
    db.commit()
    return s


@suppliers.put("/{sid}", response_model=SupplierOut)
def update_supplier(sid: int, body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    s = db.get(Supplier, sid)
    if not s:
        raise NotFound("Supplier not found")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    audit(db, user, "UPDATE", "Supplier", s.id, new=body.model_dump())
    db.commit()
    return s


# ------------------------------------------------ inventory
@inventory.get("/items", response_model=list[ItemOut])
def list_items(item_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    stmt = select(InventoryItem).order_by(InventoryItem.item_type, InventoryItem.name)
    if item_type:
        stmt = stmt.where(InventoryItem.item_type == item_type)
    return list(db.scalars(stmt))


@inventory.post("/items", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PRODUCTION"))):
    if db.scalar(select(InventoryItem).where(InventoryItem.sku == body.sku)):
        raise Conflict("SKU already exists")
    it = InventoryItem(**body.model_dump())
    db.add(it)
    db.flush()
    audit(db, user, "CREATE", "InventoryItem", it.id, new=body.model_dump())
    db.commit()
    return it


@inventory.get("/summary")
def inventory_summary(item_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    rows = stock.stock_summary(db, item_type)
    return jsonable({"items": rows, "total_value": sum((r["value"] for r in rows), 0),
                     "low_stock": [r for r in rows if r["low_stock"]]})


@inventory.post("/adjustments", status_code=201)
def stock_adjustment(body: AdjustmentIn, db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    """The only way to correct stock: an explicit, reasoned STOCK_ADJUSTMENT ledger entry (never an overwrite)."""
    item = stock.get_item(db, body.item_id)
    mv = stock.post_movement(db, item=item, quantity=body.quantity, unit=body.unit, direction=body.direction,
                             movement_type="STOCK_ADJUSTMENT", txn_date=body.txn_date or date.today(), source_type="Adjustment",
                             source_id=None, user=user, remarks=body.reason)
    audit(db, user, "ADJUST", "InventoryItem", item.id, new={"direction": body.direction, "quantity": body.quantity, "reason": body.reason})
    db.commit()
    return jsonable({"movement_id": mv.id, "balance": stock.balance(db, item.id)})


# ------------------------------------------------ stock ledger
@ledger.get("")
def get_ledger(item_id: int | None = None, movement_type: str | None = None, date_from: date | None = None, date_to: date | None = None,
               db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    return jsonable(reports.stock_ledger(db, date_from, date_to, item_id=item_id, movement_type=movement_type))


@ledger.get("/summary/{item_id}")
def item_summary(item_id: int, date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db),
                 _: User = Depends(require_roles(*OPS_READ))):
    return jsonable(stock.item_ledger_summary(db, item_id, date_from, date_to))


# ------------------------------------------------ purchases
@purchases.get("", response_model=list[PurchaseOut])
def list_purchases(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(*OPS_READ))):
    from app.models import Purchase
    stmt = select(Purchase).order_by(Purchase.id.desc())
    if date_from:
        stmt = stmt.where(Purchase.purchase_date >= date_from)
    if date_to:
        stmt = stmt.where(Purchase.purchase_date <= date_to)
    return list(db.scalars(stmt))


@purchases.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(body: PurchaseIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PRODUCTION"))):
    return pur_svc.create_purchase(db, user, supplier_id=body.supplier_id, supplier_invoice_no=body.supplier_invoice_no,
                                   purchase_date=body.purchase_date, items=[i.model_dump() for i in body.items], receive=body.receive,
                                   idempotency_key=body.idempotency_key)


@purchases.post("/{pid}/receive", response_model=PurchaseOut)
def receive_purchase(pid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PRODUCTION"))):
    return pur_svc.receive_purchase(db, user, pid)


# ------------------------------------------------ BOM
@bom.get("", response_model=list[BomOut])
def list_boms(product_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    stmt = select(BOM).order_by(BOM.product_id, BOM.version.desc())
    if product_id:
        stmt = stmt.where(BOM.product_id == product_id)
    return list(db.scalars(stmt))


@bom.get("/{bid}", response_model=BomOut)
def get_bom(bid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*OPS_READ))):
    b = db.get(BOM, bid)
    if not b:
        raise NotFound("BOM not found")
    return b


@bom.post("", response_model=BomOut, status_code=201)
def create_bom(body: BomIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "PRODUCTION"))):
    return prod_svc.create_bom(db, user, product_id=body.product_id, expected_output=body.expected_output, batch_size=body.batch_size,
                               effective_date=body.effective_date, items=[i.model_dump() for i in body.items], notes=body.notes)
