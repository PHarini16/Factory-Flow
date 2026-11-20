from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_handlers
from app.routers import auth_users, master, operations

API = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup: apply Alembic migrations and seed demo data if the database is empty."""
    if get_settings().auto_migrate:
        from app.scripts.seed import migrate_and_seed
        migrate_and_seed()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="FactoryFlow API", version="1.0.0", lifespan=lifespan,
                  description="Integrated Order-to-Audit Management System for small-scale food manufacturers.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    install_handlers(app)
    for r in (auth_users.auth, auth_users.users, master.products, master.customers, master.suppliers, master.inventory, master.ledger,
              master.purchases, master.bom, operations.production, operations.orders, operations.invoices, operations.dispatches,
              operations.payments, operations.costing, operations.report_router, operations.audit_router, operations.dashboard, operations.demo):
        app.include_router(r, prefix=API)

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
