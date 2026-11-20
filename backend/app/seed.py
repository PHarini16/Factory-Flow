"""Seed data (dummy only) and the mandatory benchmark scenario runner."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.core.errors import Conflict
from app.core.security import hash_password
from app.models import (BOM, BOMItem, Customer, InventoryItem, Product, Role, Supplier, SystemSetting, User)
from app.services import production, purchase, sales, stock
from app.services.common import audit

D = Decimal
DEMO_PASSWORD = "Demo@1234"

ROLES = {"OWNER": "Business owner - full read access, user management",
         "ADMIN": "Factory administrator - master data, orders, invoicing, dispatch, payments",
         "SALESMAN": "Field salesman - mobile ordering for assigned customers",
         "PRODUCTION": "Production supervisor - BOM, production runs, wastage",
         "ACCOUNTANT": "Accountant / auditor - read-only financial access"}

USERS = [("owner", "Meena Raghavan (Owner)", "OWNER"), ("admin", "Karthik Subramanian (Admin)", "ADMIN"),
         ("salesman_a", "Salesman A - Arun Kumar", "SALESMAN"), ("salesman_b", "Salesman B - Bala Murugan", "SALESMAN"),
         ("production", "Prakash Iyer (Production)", "PRODUCTION"), ("accountant", "Anitha Devi (Accountant)", "ACCOUNTANT")]


def seed_master(db: Session) -> None:
    """Idempotent master-data seed: roles, users, items, products, customers, suppliers, opening stock, BOM."""
    if db.scalar(select(Role).limit(1)):
        return
    roles = {n: Role(name=n, description=d) for n, d in ROLES.items()}
    db.add_all(roles.values())
    db.flush()
    users = {}
    for uname, full, role in USERS:
        users[uname] = User(username=uname, full_name=full, email=f"{uname}@example.com", password_hash=hash_password(DEMO_PASSWORD), role_id=roles[role].id)
        db.add(users[uname])
    db.add_all([SystemSetting(key="variance_tolerance_pct", value="3", description="Variance alert tolerance (%)"),
                SystemSetting(key="allow_partial_dispatch", value="true", description="Allow documented partial dispatch")])
    db.flush()
    admin = users["admin"]

    items = {}
    for sku, name, typ, cat, unit, reorder in [
        ("RM-FLOUR", "Flour", "RAW", "Raw material", "kg", "50"), ("RM-OIL", "Cooking oil", "RAW", "Raw material", "litre", "20"),
        ("RM-SPICE", "Salt and spice mix", "RAW", "Raw material", "kg", "2"),
        ("PK-POUCH200", "200 g pouch", "PACKAGING", "Packaging", "piece", "100"), ("PK-CARTON", "Carton", "PACKAGING", "Packaging", "piece", "10")]:
        items[sku] = InventoryItem(sku=sku, name=name, item_type=typ, category=cat, unit=unit, reorder_level=D(reorder))
        db.add(items[sku])

    prods = {}
    for sku, name, cat, pack, price, reorder in [("FG-MURUKKU200", "Murukku", "Murukku", "200 g", "50", "40"), ("FG-MIXTURE200", "Mixture", "Mixture", "200 g", "55", "0"),
                                                 ("FG-CHIPS150", "Chips", "Chips", "150 g", "45", "0"), ("FG-SWEET250", "Sweets", "Sweets", "250 g", "90", "0")]:
        fg = InventoryItem(sku=sku, name=f"{name} {pack}", item_type="FINISHED", category=cat, unit="packet", reorder_level=D(reorder))
        db.add(fg)
        db.flush()
        prods[sku] = Product(name=f"{name} {pack}", category=cat, sku=sku, pack_size=pack, unit="packet", hsn_code="1905" if cat != "Sweets" else "1704",
                             gst_rate=D("5"), selling_price=D(price), reorder_level=D(reorder), inventory_item_id=fg.id)
        db.add(prods[sku])
    db.flush()

    db.add_all([Customer(name="Retailer A - Sri Lakshmi Stores", customer_type="RETAILER", gstin="33BBBBB1111B1Z6", billing_address="45 Gandhi Road, Coimbatore",
                         shipping_address="45 Gandhi Road, Coimbatore", city="Coimbatore", state="Tamil Nadu", state_code="33", phone="9000000001",
                         email="retailera@example.com", salesman_id=users["salesman_a"].id, credit_limit=D("50000"), payment_terms_days=30),
                Customer(name="Retailer C - Annapurna Provision", customer_type="RETAILER", billing_address="7 Market St, Tiruchirappalli", city="Tiruchirappalli",
                         state="Tamil Nadu", state_code="33", phone="9000000003", salesman_id=users["salesman_a"].id, credit_limit=D("25000")),
                Customer(name="Distributor B - Namma Foods", customer_type="DISTRIBUTOR", gstin="29CCCCC2222C1Z7", billing_address="88 MG Road, Bengaluru",
                         shipping_address="Warehouse 4, Peenya, Bengaluru", city="Bengaluru", state="Karnataka", state_code="29", phone="9000000002",
                         email="distributorb@example.com", salesman_id=users["salesman_b"].id, credit_limit=D("200000"), payment_terms_days=45)])
    db.add_all([Supplier(name="Coimbatore Flour Mills", contact="9111100001", gstin="33DDDDD3333D1Z8", address="Coimbatore", state="Tamil Nadu"),
                Supplier(name="Sri Oil Traders", contact="9111100002", gstin="33EEEEE4444E1Z9", address="Madurai", state="Tamil Nadu"),
                Supplier(name="PackWise Packaging", contact="9111100003", gstin="33FFFFF5555F1Z1", address="Chennai", state="Tamil Nadu")])
    db.flush()

    opening_date = date.today().replace(day=1)
    for sku, qty, rate in [("RM-FLOUR", "100", "42"), ("RM-OIL", "30", "140"), ("RM-SPICE", "5", "200"), ("PK-POUCH200", "500", "2.50"), ("PK-CARTON", "30", "15")]:
        stock.post_movement(db, item=items[sku], quantity=D(qty), unit=None, direction="IN", movement_type="OPENING", txn_date=opening_date,
                            source_type="Opening", source_id=None, user=admin, remarks="Opening balance", rate=D(rate))
    murukku = prods["FG-MURUKKU200"]
    stock.post_movement(db, item=murukku.inventory_item, quantity=D("50"), unit=None, direction="IN", movement_type="OPENING", txn_date=opening_date,
                        source_type="Opening", source_id=None, user=admin, remarks="Existing opening stock", rate=D("30"))

    bom = BOM(product_id=murukku.id, version=1, batch_size=D("1"), expected_output=D("200"), effective_date=opening_date, notes="Standard Murukku 200 g recipe")
    for sku, q, u, prim in [("RM-FLOUR", "40", "kg", False), ("RM-OIL", "10", "litre", False), ("RM-SPICE", "1.2", "kg", False),
                            ("PK-POUCH200", "200", "piece", True), ("PK-CARTON", "10", "piece", False)]:
        bom.items.append(BOMItem(item_id=items[sku].id, quantity=D(q), unit=u, is_primary_pack=prim))
    db.add(bom)
    audit(db, admin, "SEED", "System", None, new={"note": "demo master data seeded"})
    db.commit()


def reset_database(engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def run_benchmark(db: Session) -> dict:
    """Executes mandatory steps 1-14 through the real services (no shortcuts) and returns the observed results."""
    if db.scalar(select(Supplier).limit(1)) is None:
        seed_master(db)
    u = {x.username: x for x in db.scalars(select(User))}
    from app.models import Purchase
    if db.scalar(select(Purchase).where(Purchase.supplier_invoice_no == "BENCH-001")):
        raise Conflict("Benchmark already executed on this database. Reset the demo database first.")
    items = {i.sku: i for i in db.scalars(select(InventoryItem))}
    murukku = db.scalar(select(Product).where(Product.sku == "FG-MURUKKU200"))
    cust = {c.name.split(" - ")[0]: c for c in db.scalars(select(Customer))}
    supplier = db.scalar(select(Supplier).where(Supplier.name == "Coimbatore Flour Mills"))
    today = date.today()

    # 1. purchase 60 kg flour @ 45
    purchase.create_purchase(db, u["admin"], supplier_id=supplier.id, supplier_invoice_no="BENCH-001", purchase_date=today,
                             items=[{"item_id": items["RM-FLOUR"].id, "quantity": D("60"), "rate": D("45"), "unit": "kg"}])
    # 2-5. production run
    run = production.complete_run(db, u["production"], product_id=murukku.id, bom_id=None, batches=D("1"), run_date=today, good_output=D("188"),
                                  damaged_pouches=D("6"), actual_usage=[{"item_id": items["RM-FLOUR"].id, "actual_quantity": D("40")},
                                                                       {"item_id": items["RM-OIL"].id, "actual_quantity": D("10.5")},
                                                                       {"item_id": items["RM-SPICE"].id, "actual_quantity": D("1.2")},
                                                                       {"item_id": items["PK-CARTON"].id, "actual_quantity": D("9")}],
                                  remarks="Benchmark run", idempotency_key="bench-run-1")
    fg_after_prod = stock.balance(db, murukku.inventory_item_id)
    # 6-9 order, approve, invoice, dispatch
    oa = sales.create_order(db, u["salesman_a"], customer_id=cust["Retailer A"].id, items=[{"product_id": murukku.id, "quantity": D("150")}],
                            remarks="Benchmark order A", idempotency_key="bench-order-a")
    sales.decide_order(db, u["admin"], oa.id, True)
    inv = sales.create_invoice(db, u["admin"], oa.id)
    sales.create_dispatch(db, u["admin"], invoice_id=inv.id, lines=None, idempotency_key="bench-dispatch-a")
    fg_after_dispatch = stock.balance(db, murukku.inventory_item_id)
    # 10-11 order B + stock warning
    ob = sales.create_order(db, u["salesman_b"], customer_id=cust["Distributor B"].id, items=[{"product_id": murukku.id, "quantity": D("120")}],
                            remarks="Benchmark order B", idempotency_key="bench-order-b")
    warning = sales.stock_check(db, ob)
    # 12 payment
    pay = sales.record_payment(db, u["admin"], customer_id=cust["Retailer A"].id, amount=D("4000"), mode="UPI", reference="BENCH-UPI-001",
                               invoice_id=inv.id, idempotency_key="bench-pay-1")
    # 13 overheads
    production.record_overheads(db, u["production"], run.id, labour=D("1200"), gas_power=D("600"))
    db.refresh(run)
    c = run.cost
    usage = {x.item.sku: x for x in run.usages}
    return {
        "flour_closing": stock.balance(db, items["RM-FLOUR"].id), "oil_closing": stock.balance(db, items["RM-OIL"].id),
        "spice_closing": stock.balance(db, items["RM-SPICE"].id), "pouches_closing": stock.balance(db, items["PK-POUCH200"].id),
        "cartons_closing": stock.balance(db, items["PK-CARTON"].id),
        "finished_after_production": fg_after_prod, "finished_after_dispatch": fg_after_dispatch,
        "expected_output": run.expected_output, "good_output": run.good_output,
        "yield_variance_pct": run.yield_variance_pct, "oil_variance_pct": usage["RM-OIL"].variance_pct,
        "flour_wavg_rate": items["RM-FLOUR"].avg_cost,
        "flour_cost": usage["RM-FLOUR"].cost, "oil_cost": usage["RM-OIL"].cost, "spice_cost": usage["RM-SPICE"].cost,
        "pouch_cost": usage["PK-POUCH200"].cost, "carton_cost": usage["PK-CARTON"].cost,
        "material_cost": c.material_cost, "overhead": c.overhead_total, "total_cost": c.total_cost, "cost_per_packet": c.cost_per_packet,
        "gross_profit_per_packet": c.gross_profit_per_packet, "gross_margin_pct": c.gross_margin_pct,
        "invoice_no": inv.invoice_no, "taxable": inv.taxable_amount, "cgst": inv.cgst, "sgst": inv.sgst, "igst": inv.igst, "invoice_total": inv.total,
        "retailer_a_outstanding": sales.outstanding(db, inv)["outstanding"],
        "distributor_b_shortage": warning[0]["shortage"], "distributor_b_available": warning[0]["available"], "distributor_b_requested": warning[0]["requested"],
        "order_b_id": ob.id, "invoice_id": inv.id, "run_id": run.id, "receipt_no": pay.receipt_no,
    }
