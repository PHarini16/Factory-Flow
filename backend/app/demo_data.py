"""Rich dummy history so a fresh install is not empty.

Everything is created through the REAL services (purchases, production runs, orders, invoices, dispatches, payments),
so the stock ledger, costing, receivables and audit log are genuinely consistent - nothing is inserted "by hand".

The benchmark items (Flour, Cooking oil, Salt & spice mix, 200 g pouch, Carton, Murukku 200 g) and the customers
"Retailer A" / "Distributor B" are deliberately NOT touched, so the mandatory benchmark still reproduces its exact numbers.
All names, GSTINs and phone numbers are fictitious.
"""
import math
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BOM, BOMItem, Customer, InventoryItem, Product, Supplier, SystemSetting, User
from app.services import production, purchase, sales, stock
from app.services.common import q2

D = lambda x: Decimal(str(x))  # noqa: E731
MARKER = "demo_data_loaded"

# sku, name, type, unit, reorder level, base purchase rate, supplier name
ITEMS = [
    ("RM-BESAN", "Gram flour (besan)", "RAW", "kg", "30", "70", "Madurai Gram Mills"),
    ("RM-RICE", "Rice flour", "RAW", "kg", "30", "55", "Erode Rice Mill"),
    ("RM-POTATO", "Potato", "RAW", "kg", "60", "28", "Tiruppur Potato Mandi"),
    ("RM-BANANA", "Raw banana", "RAW", "kg", "50", "38", "Tiruppur Potato Mandi"),
    ("RM-SUGAR", "Sugar", "RAW", "kg", "30", "45", "Sri Ghee Dairy"),
    ("RM-GHEE", "Ghee", "RAW", "kg", "25", "520", "Sri Ghee Dairy"),
    ("RM-PEANUT", "Peanuts", "RAW", "kg", "20", "110", "Madurai Gram Mills"),
    ("RM-OIL2", "Refined sunflower oil", "RAW", "litre", "40", "135", "Sri Oil Traders"),
    ("RM-MASALA", "Snack masala blend", "RAW", "kg", "5", "190", "Madurai Gram Mills"),
    ("PK-POUCH200M", "200 g snack pouch", "PACKAGING", "piece", "200", "2.2", "Chennai Packaging Works"),
    ("PK-POUCH150", "150 g snack pouch", "PACKAGING", "piece", "200", "2.0", "Chennai Packaging Works"),
    ("PK-BOX250", "250 g sweet box", "PACKAGING", "piece", "100", "6", "Chennai Packaging Works"),
    ("PK-CARTON2", "Shipping carton (large)", "PACKAGING", "piece", "40", "14", "Chennai Packaging Works"),
]

NEW_SUPPLIERS = [("Madurai Gram Mills", "Madurai"), ("Erode Rice Mill", "Erode"), ("Tiruppur Potato Mandi", "Tiruppur"),
                 ("Chennai Packaging Works", "Chennai"), ("Sri Ghee Dairy", "Coimbatore"),
                 ("Coimbatore Spice House", "Coimbatore"), ("Salem Sugar Traders", "Salem"), ("Trichy Packaging Supplies", "Tiruchirappalli")]

# sku, name, category, pack, price, hsn
NEW_PRODUCTS = [("FG-THATTAI200", "Thattai", "Murukku", "200 g", "48", "1905"), ("FG-RIBBON200", "Ribbon Pakoda", "Mixture", "200 g", "52", "1905"),
                ("FG-BANANA150", "Banana Chips", "Chips", "150 g", "60", "1905"), ("FG-CHIKKI150", "Peanut Chikki", "Sweets", "150 g", "40", "1704"),
                ("FG-KARASEV200", "Karasev", "Mixture", "200 g", "50", "1905"), ("FG-BURFI250", "Ghee Burfi", "Sweets", "250 g", "130", "1704")]

# product sku -> (expected output / batch, [(item sku, qty, unit, is_primary_pack)])
BOMS = {
    "FG-MIXTURE200": (150, [("RM-BESAN", "20", "kg", 0), ("RM-RICE", "10", "kg", 0), ("RM-PEANUT", "6", "kg", 0), ("RM-OIL2", "12", "litre", 0), ("RM-MASALA", "1.5", "kg", 0), ("PK-POUCH200M", "150", "piece", 1), ("PK-CARTON2", "8", "piece", 0)]),
    "FG-CHIPS150": (200, [("RM-POTATO", "45", "kg", 0), ("RM-OIL2", "14", "litre", 0), ("RM-MASALA", "1", "kg", 0), ("PK-POUCH150", "200", "piece", 1), ("PK-CARTON2", "10", "piece", 0)]),
    "FG-SWEET250": (120, [("RM-BESAN", "8", "kg", 0), ("RM-SUGAR", "18", "kg", 0), ("RM-GHEE", "9", "kg", 0), ("PK-BOX250", "120", "piece", 1), ("PK-CARTON2", "6", "piece", 0)]),
    "FG-THATTAI200": (160, [("RM-RICE", "22", "kg", 0), ("RM-OIL2", "10", "litre", 0), ("RM-MASALA", "0.8", "kg", 0), ("PK-POUCH200M", "160", "piece", 1), ("PK-CARTON2", "8", "piece", 0)]),
    "FG-RIBBON200": (150, [("RM-BESAN", "16", "kg", 0), ("RM-RICE", "12", "kg", 0), ("RM-OIL2", "11", "litre", 0), ("RM-MASALA", "1.2", "kg", 0), ("PK-POUCH200M", "150", "piece", 1), ("PK-CARTON2", "8", "piece", 0)]),
    "FG-BANANA150": (180, [("RM-BANANA", "40", "kg", 0), ("RM-OIL2", "12", "litre", 0), ("RM-MASALA", "0.9", "kg", 0), ("PK-POUCH150", "180", "piece", 1), ("PK-CARTON2", "9", "piece", 0)]),
    "FG-KARASEV200": (160, [("RM-BESAN", "18", "kg", 0), ("RM-RICE", "6", "kg", 0), ("RM-OIL2", "10", "litre", 0), ("RM-MASALA", "1", "kg", 0), ("PK-POUCH200M", "160", "piece", 1), ("PK-CARTON2", "8", "piece", 0)]),
    "FG-BURFI250": (120, [("RM-SUGAR", "16", "kg", 0), ("RM-GHEE", "6", "kg", 0), ("PK-BOX250", "120", "piece", 1), ("PK-CARTON2", "6", "piece", 0)]),
    "FG-CHIKKI150": (150, [("RM-PEANUT", "14", "kg", 0), ("RM-SUGAR", "10", "kg", 0), ("PK-POUCH150", "150", "piece", 1), ("PK-CARTON2", "6", "piece", 0)]),
}

# name, type, city, state, state_code, salesman
CUSTOMERS = [
    ("Kovai Supermart", "RETAILER", "Coimbatore", "Tamil Nadu", "33", "salesman_a"), ("Sri Balaji Stores", "RETAILER", "Madurai", "Tamil Nadu", "33", "salesman_a"),
    ("Annai Provisions", "RETAILER", "Salem", "Tamil Nadu", "33", "salesman_a"), ("Murugan Traders", "RETAILER", "Erode", "Tamil Nadu", "33", "salesman_a"),
    ("Vasanth & Co", "RETAILER", "Tiruppur", "Tamil Nadu", "33", "salesman_a"), ("Lakshmi Agencies", "DISTRIBUTOR", "Chennai", "Tamil Nadu", "33", "salesman_a"),
    ("Pandian Stores", "RETAILER", "Tirunelveli", "Tamil Nadu", "33", "salesman_a"), ("Namma Fresh Mart", "RETAILER", "Mysuru", "Karnataka", "29", "salesman_b"),
    ("Bangalore Snack Hub", "DISTRIBUTOR", "Bengaluru", "Karnataka", "29", "salesman_b"), ("Malabar Foods", "RETAILER", "Kozhikode", "Kerala", "32", "salesman_b"),
    ("Kochi Wholesale Traders", "DISTRIBUTOR", "Kochi", "Kerala", "32", "salesman_b"), ("Vizag Sweets & Snacks", "RETAILER", "Visakhapatnam", "Andhra Pradesh", "37", "salesman_b"),
]

CYCLES = [145, 115, 85, 55, 28, 10]  # "days ago" of each production/sales cycle (~6 months of history)


def _dt(days_ago: int) -> date:
    return date.today() - timedelta(days=max(0, days_ago))


def seed_demo_data(db: Session) -> dict:
    if db.get(SystemSetting, MARKER):
        return {"status": "already loaded"}
    rng = random.Random(2026)
    users = {u.username: u for u in db.scalars(select(User))}
    admin, prod_user = users["admin"], users["production"]

    # ---- master data
    for i, (name, city) in enumerate(NEW_SUPPLIERS):
        db.add(Supplier(name=name, contact=f"91111{10010 + i}", gstin=f"33GHIJK{2000 + i:04d}L1Z{i}", address=city, state="Tamil Nadu", payment_terms="30 days" if i % 2 == 0 else "15 days"))
    suppliers = None
    items: dict[str, InventoryItem] = {i.sku: i for i in db.scalars(select(InventoryItem))}
    for sku, name, typ, unit, reorder, _rate, _sup in ITEMS:
        it = InventoryItem(sku=sku, name=name, item_type=typ, category="Raw material" if typ == "RAW" else "Packaging", unit=unit, reorder_level=D(reorder))
        db.add(it)
        items[sku] = it
    products: dict[str, Product] = {p.sku: p for p in db.scalars(select(Product))}
    for sku, name, cat, pack, price, hsn in NEW_PRODUCTS:
        fg = InventoryItem(sku=sku, name=f"{name} {pack}", item_type="FINISHED", category=cat, unit="packet", reorder_level=D("30"))
        db.add(fg)
        db.flush()
        products[sku] = Product(name=f"{name} {pack}", category=cat, sku=sku, pack_size=pack, unit="packet", hsn_code=hsn, gst_rate=D("5"), selling_price=D(price), reorder_level=D("30"), inventory_item_id=fg.id)
        db.add(products[sku])
    for p in products.values():  # give every demo product a sensible reorder level
        if p.sku != "FG-MURUKKU200" and p.inventory_item:
            p.reorder_level = D("30")
            p.inventory_item.reorder_level = D("30")
    db.flush()
    suppliers = {s.name: s for s in db.scalars(select(Supplier))}
    for i, (name, typ, city, state, code, sm) in enumerate(CUSTOMERS):
        db.add(Customer(name=name, customer_type=typ, gstin=f"{code}ABCDE{1000 + i:04d}F1Z{i % 10}", billing_address=f"{10 + i} Main Road, {city}", shipping_address=f"{10 + i} Main Road, {city}",
                        city=city, state=state, state_code=code, phone=f"9{800000000 + i * 1111:09d}"[:10], email=f"{name.split()[0].lower()}@example.com", salesman_id=users[sm].id,
                        credit_limit=D(150000 if typ == "DISTRIBUTOR" else 40000), payment_terms_days=45 if typ == "DISTRIBUTOR" else 30))
    db.flush()
    for psku, (out, lines) in BOMS.items():
        bom = BOM(product_id=products[psku].id, version=1, batch_size=D(1), expected_output=D(out), effective_date=_dt(CYCLES[0] + 5), notes="Standard recipe v1")
        for isku, q, u, prim in lines:
            bom.items.append(BOMItem(item_id=items[isku].id, quantity=D(q), unit=u, is_primary_pack=bool(prim)))
        db.add(bom)
    db.commit()
    custs = [c for c in db.scalars(select(Customer)) if c.name in {x[0] for x in CUSTOMERS}]
    by_sm = {k: [c for c in custs if c.salesman_id == users[k].id] for k in ("salesman_a", "salesman_b")}
    base = {s[0]: (D(s[5]), s[6]) for s in ITEMS}
    counters = {"po": 0, "pay": 0}
    stats = {"purchases": 0, "runs": 0, "orders": 0, "invoices": 0, "dispatches": 0, "payments": 0}

    def ensure(sku: str, need: Decimal, d: date) -> None:
        it = items[sku]
        bal = stock.balance(db, it.id)
        if bal >= need:
            return
        step = 100 if it.unit == "piece" else 10
        buy = D(math.ceil(float((need - bal) * D("1.6")) / step) * step)
        rate, sup = base[sku]
        rate = q2(rate * D(str(round(rng.uniform(0.94, 1.08), 3))))
        counters["po"] += 1
        purchase.create_purchase(db, admin, supplier_id=suppliers[sup].id, supplier_invoice_no=f"DEMO-{counters['po']:04d}", purchase_date=d,
                                 items=[{"item_id": it.id, "quantity": buy, "rate": rate, "unit": it.unit}])
        stats["purchases"] += 1

    def run(psku: str, d: date) -> None:
        p = products[psku]
        bom = db.scalar(select(BOM).where(BOM.product_id == p.id))
        batches = D(rng.choice([1, 1, 2]))
        for bi in bom.items:
            ensure(bi.item.sku, production.standard_qty(bi, batches) * D("1.15"), d)
        exp = bom.expected_output * batches
        good = D(int(float(exp) * (1 - rng.uniform(0.0, 0.085))))
        usage = []
        for bi in bom.items:
            if bi.is_primary_pack:
                continue
            std = production.standard_qty(bi, batches)
            factor = rng.uniform(0.9, 1.0) if bi.item.item_type == "PACKAGING" else rng.uniform(0.97, 1.09)
            usage.append({"item_id": bi.item_id, "actual_quantity": q2(std * D(str(round(factor, 3))))})
        r = production.complete_run(db, prod_user, product_id=p.id, bom_id=bom.id, batches=batches, run_date=d, good_output=good, damaged_packets=D(rng.choice([0, 0, 2, 4])),
                                    damaged_pouches=D(rng.choice([0, 2, 3, 6])), scrap_qty=D(str(round(rng.uniform(0.2, 2.5), 1))), material_wastage=D(str(round(rng.uniform(0, 1.2), 1))),
                                    actual_usage=usage, remarks="Demo production run")
        lab = q2(D(rng.randint(900, 1600)) * batches)
        production.record_overheads(db, prod_user, r.id, labour=lab, gas_power=q2(lab * D("0.5")))
        stats["runs"] += 1

    def fg_bal(psku: str) -> Decimal:
        return stock.balance(db, products[psku].inventory_item_id)

    def make_lines(psku_pool: list[str], n_lines: int, share: float) -> list[tuple[str, Decimal]]:
        out = []
        for psku in rng.sample(psku_pool, min(n_lines, len(psku_pool))):
            avail = fg_bal(psku)
            qty = D(int(float(avail) * rng.uniform(0.1, share) // 5 * 5))
            if qty >= 10:
                out.append((psku, qty))
        return out

    unpaid_dispatched: list = []

    def sale(d: date, outcome: str | None = None, dispatch: bool = True, status_only: str | None = None):
        sm = rng.choice(["salesman_a", "salesman_b"])
        cust = rng.choice(by_sm[sm])
        pool = [s for s in BOMS if fg_bal(s) >= 20] if dispatch else list(BOMS)
        lines = make_lines(pool, rng.randint(1, 3), 0.45) if dispatch else [(s, D(rng.choice([40, 60, 80, 100]))) for s in rng.sample(list(BOMS), 2)]
        if not lines:
            return None
        o = sales.create_order(db, users[sm], customer_id=cust.id, items=[{"product_id": products[s].id, "quantity": q} for s, q in lines], order_date=d, remarks="Demo order")
        stats["orders"] += 1
        if status_only == "SUBMITTED":
            return o
        if status_only == "REJECTED":
            sales.decide_order(db, admin, o.id, False, "Credit limit exceeded - pay old dues first")
            return o
        sales.decide_order(db, admin, o.id, True)
        if status_only == "APPROVED":
            return o
        inv = sales.create_invoice(db, admin, o.id, invoice_date=d)
        stats["invoices"] += 1
        if not dispatch:
            return inv
        sales.create_dispatch(db, admin, invoice_id=inv.id, lines=None, dispatch_date=d, vehicle_no=f"TN{rng.randint(10, 99)}AB{rng.randint(1000, 9999)}")
        stats["dispatches"] += 1
        outcome = outcome or rng.choices(["paid", "partial", "unpaid"], [55, 25, 20])[0]
        pay_day = min(date.today(), d + timedelta(days=rng.randint(4, 24)))
        if outcome in ("paid", "partial"):
            amt = inv.total if outcome == "paid" else q2(inv.total * D(str(round(rng.uniform(0.3, 0.7), 2))) // 10 * 10)
            if amt > 0:
                counters["pay"] += 1
                mode = rng.choice(["UPI", "BANK", "CASH", "CHEQUE"])
                sales.record_payment(db, admin, customer_id=cust.id, invoice_id=inv.id, amount=amt, mode=mode, payment_date=pay_day,
                                     reference="" if mode == "CASH" else f"DEMO-{mode}-{counters['pay']:04d}")
                stats["payments"] += 1
        if outcome == "unpaid":
            unpaid_dispatched.append(inv)
        return inv

    # ---- six cycles of production + sales
    keys = list(BOMS)
    for i, c in enumerate(CYCLES):
        for k in range(4):
            run(keys[(i + k) % len(keys)], _dt(c - k))
        for j in range(8):
            sale(_dt(c - 3 - j), outcome="unpaid" if (i == len(CYCLES) - 1 and rng.random() < 0.6) else None)

    # ---- a snapshot of "live" workflow states on the most recent days
    for _ in range(3):
        sale(_dt(0), dispatch=False, status_only="SUBMITTED")  # pending approvals
    sale(_dt(1), dispatch=False, status_only="REJECTED")
    sale(_dt(1), dispatch=False, status_only="APPROVED")  # approved, awaiting invoice
    sale(_dt(1), dispatch=False)  # invoiced, awaiting dispatch
    to_cancel = sale(_dt(1), dispatch=False)  # invoiced then cancelled (credit note)
    if to_cancel:
        sales.cancel_invoice(db, admin, to_cancel.id, "Customer cancelled the order")
    # a documented partial dispatch
    best = max(BOMS, key=fg_bal)
    if fg_bal(best) >= 80:
        cust = by_sm["salesman_a"][0]
        o = sales.create_order(db, users["salesman_a"], customer_id=cust.id, items=[{"product_id": products[best].id, "quantity": D(100)}], order_date=_dt(2))
        sales.decide_order(db, admin, o.id, True)
        inv = sales.create_invoice(db, admin, o.id, invoice_date=_dt(2))
        sales.create_dispatch(db, admin, invoice_id=inv.id, lines=[{"invoice_item_id": inv.items[0].id, "quantity": D(60)}], remarks="Balance 40 pending next production run", dispatch_date=_dt(2))
        stats["orders"] += 1; stats["invoices"] += 1; stats["dispatches"] += 1
    # a customer return with a credit note (restocked)
    if unpaid_dispatched:
        inv = unpaid_dispatched[-1]
        sales.issue_credit_note(db, admin, inv.id, [{"invoice_item_id": inv.items[0].id, "quantity": D(5)}], "Damaged packets returned by customer", True)
    # a stock write-off creating a low-stock alert + an audited adjustment
    ghee = items["RM-GHEE"]
    bal = stock.balance(db, ghee.id)
    if bal > 12:
        stock.post_movement(db, item=ghee, quantity=bal - D(10), unit=None, direction="OUT", movement_type="STOCK_ADJUSTMENT", txn_date=_dt(1), source_type="Adjustment",
                            source_id=None, user=admin, remarks="Spillage / quality write-off (demo)")
    db.add(SystemSetting(key=MARKER, value="true", description="Demo history has been loaded"))
    db.commit()
    return {"status": "loaded", **stats, "customers": len(CUSTOMERS), "suppliers": len(NEW_SUPPLIERS), "products": len(NEW_PRODUCTS), "items": len(ITEMS)}
