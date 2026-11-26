"""CLI:  python -m app.scripts.seed [--reset] [--benchmark]

  (no flags)   apply migrations, seed demo master data if the DB is empty
  --no-demo-data  skip the dummy history (master data only)
  --reset      DROP everything, re-migrate, re-seed (clean slate)
  --benchmark  additionally execute the mandatory benchmark scenario (fails if already run)
"""
import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.db import Base, SessionLocal, engine


def _alembic_cfg() -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def migrate_and_seed(demo_data: bool | None = None) -> None:
    from app import seed
    from app.core.config import get_settings
    command.upgrade(_alembic_cfg(), "head")
    if demo_data is None:
        demo_data = get_settings().seed_demo_data
    with SessionLocal() as db:
        seed.seed_all(db, demo_data)


def reset(demo_data: bool | None = None) -> None:
    import app.models  # noqa: F401
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    migrate_and_seed(demo_data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--no-demo-data", action="store_true", help="seed only master data (empty transactions)")
    args = ap.parse_args()
    demo = False if args.no_demo_data else None
    if args.reset:
        reset(demo)
        print("Database reset and seeded.")
    else:
        migrate_and_seed(demo)
        print("Migrations applied; seed data present.")
    if args.benchmark:
        from app import seed
        with SessionLocal() as db:
            res = seed.run_benchmark(db)
        print("Benchmark executed. Key results:")
        for k in ("flour_closing", "oil_closing", "spice_closing", "pouches_closing", "cartons_closing", "finished_after_production",
                  "finished_after_dispatch", "yield_variance_pct", "oil_variance_pct", "taxable", "cgst", "sgst", "invoice_total",
                  "retailer_a_outstanding", "distributor_b_shortage", "cost_per_packet"):
            print(f"  {k:28} {res[k]}")


if __name__ == "__main__":
    main()
