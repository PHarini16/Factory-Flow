from tests.conftest import login

API = "/api/v1"


def test_login_success_and_me(client):
    r = client.post(f"{API}/auth/login", json={"username": "owner", "password": "Demo@1234"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "OWNER"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/auth/me", headers=h).json()["username"] == "owner"


def test_login_failure(client):
    assert client.post(f"{API}/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_login_rate_limit(client):
    codes = [client.post(f"{API}/auth/login", json={"username": "owner", "password": "bad"}).status_code for _ in range(12)]
    assert codes[-1] == 429


def test_protected_routes_require_token(client):
    assert client.get(f"{API}/products").status_code == 401
    assert client.get(f"{API}/products", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "access_token_minutes", -1)
    r = client.post(f"{API}/auth/login", json={"username": "owner", "password": "Demo@1234"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401


def test_password_is_hashed(db, users):
    assert users["owner"].password_hash.startswith("$2") and "Demo@1234" not in users["owner"].password_hash


def test_salesman_cannot_use_admin_functions(client, auth):
    h = auth("salesman_a")
    assert client.post(f"{API}/products", headers=h, json={"name": "x", "sku": "x", "selling_price": "1"}).status_code == 403
    assert client.post(f"{API}/orders/1/approve", headers=h).status_code == 403
    assert client.get(f"{API}/inventory/summary", headers=h).status_code == 403
    assert client.get(f"{API}/dashboard", headers=h).status_code == 403
    assert client.get(f"{API}/audit", headers=h).status_code == 403
    assert client.get(f"{API}/users", headers=h).status_code == 403


def test_accountant_is_read_only(client, auth):
    h = auth("accountant")
    assert client.get(f"{API}/invoices", headers=h).status_code == 200
    assert client.get(f"{API}/reports/gst-summary", headers=h).status_code == 200
    assert client.post(f"{API}/payments", headers=h, json={"customer_id": 1, "amount": "10", "mode": "CASH"}).status_code == 403
    assert client.post(f"{API}/invoices/from-order/1", headers=h).status_code == 403
    assert client.post(f"{API}/dispatches", headers=h, json={"invoice_id": 1}).status_code == 403


def test_production_role_scope(client, auth):
    h = auth("production")
    assert client.get(f"{API}/bom", headers=h).status_code == 200
    assert client.get(f"{API}/reports/production", headers=h).status_code == 200
    assert client.get(f"{API}/reports/sales-register", headers=h).status_code == 403
    assert client.get(f"{API}/invoices", headers=h).status_code == 403
    assert client.post(f"{API}/orders", headers=h, json={"customer_id": 1, "items": [{"product_id": 1, "quantity": "1"}]}).status_code == 403


def test_owner_manages_users_admin_cannot_create(client, auth):
    body = {"username": "newguy", "full_name": "New Guy", "password": "Password1!", "role": "SALESMAN"}
    assert client.post(f"{API}/users", headers=auth("admin"), json=body).status_code == 403
    r = client.post(f"{API}/users", headers=auth("owner"), json=body)
    assert r.status_code == 201 and r.json()["role"] == "SALESMAN"
    assert login(client, "newguy", "Password1!")


def test_salesman_sees_only_assigned_customers(client, auth):
    names = [c["name"] for c in client.get(f"{API}/customers", headers=auth("salesman_a")).json()]
    assert any("Retailer A" in n for n in names) and not any("Distributor B" in n for n in names)


def test_openapi_lists_all_modules(client):
    paths = client.get("/openapi.json").json()["paths"]
    for prefix in ["auth", "users", "products", "customers", "suppliers", "inventory", "stock-ledger", "purchases", "bom", "production",
                   "orders", "invoices", "dispatches", "payments", "costing", "reports", "audit", "dashboard"]:
        assert any(p.startswith(f"{API}/{prefix}") for p in paths), prefix
