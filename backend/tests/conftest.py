import os

os.environ["AUTO_MIGRATE"] = "false"
os.environ["DEMO_MODE"] = "true"
import shutil
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import seed
from app.core.db import Base, get_db, make_engine
from app.deps import reset_throttle
from app.main import app
from app.models import InventoryItem, Product, User

D = Decimal


@pytest.fixture(scope="session")
def template_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("tpl") / "template.db"
    eng = make_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng, expire_on_commit=False)() as s:
        seed.seed_master(s)
    eng.dispose()
    return path


@pytest.fixture()
def engine(template_db, tmp_path):
    path = tmp_path / "test.db"
    shutil.copy(template_db, path)
    eng = make_engine(f"sqlite:///{path}")
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        yield s


@pytest.fixture()
def client(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        s = Session()
        try:
            yield s
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    reset_throttle()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def users(db):
    return {u.username: u for u in db.scalars(select(User))}


@pytest.fixture()
def items(db):
    return {i.sku: i for i in db.scalars(select(InventoryItem))}


@pytest.fixture()
def murukku(db):
    return db.scalar(select(Product).where(Product.sku == "FG-MURUKKU200"))


def login(client, username, password=seed.DEMO_PASSWORD):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    cache = {}

    def _h(username):
        if username not in cache:
            cache[username] = login(client, username)
        return cache[username]
    return _h
