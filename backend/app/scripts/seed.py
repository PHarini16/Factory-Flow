"""CLI:  python -m app.scripts.seed [--reset] [--benchmark]

  (no flags)   apply migrations, seed demo master data if the DB is empty
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


def migrate_and_seed() -> None:
    command.upgrade(_alembic_cfg(), "head")
    from app import seed
    with SessionLocal() as db:
        seed.seed_master(db)


def reset() -> None:
    import app.models  # noqa: F401
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    migrate_and_seed()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    args = ap.parse_args()
    if args.reset:
        reset()
        print("Database reset and seeded.")
    else:
        migrate_and_seed()
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
