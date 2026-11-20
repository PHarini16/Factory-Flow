# FactoryFlow — Integrated Order-to-Audit Management System

A full-stack ERP prototype for a small South-Indian snack manufacturer (Murukku, Mixture, Chips, Sweets). It links the **sales workflow** (order → approval → GST invoice → dispatch → receivable → payment) and the **production workflow** (purchase → raw stock → BOM issue → production run → wastage/variance → finished goods → costing) through one **immutable stock ledger**.

Prepared as an individual shortlisting project for the Centre for Digital Infrastructure, NIT Tiruchirappalli. All data is dummy.

## Problem statement
Small food manufacturers run orders on paper/WhatsApp, track stock in notebooks and cannot see yield loss, true cost per packet or who owes what. FactoryFlow gives salesmen a fast mobile order screen and gives the owner, admin, production and accounts teams one consistent, auditable system.

## Features (all implemented unless marked)
* JWT login, bcrypt hashes, 5 roles, **server-side** RBAC, session expiry, login throttling, access-denied page
* Master data: products, customers, suppliers, raw/packaging items
* Purchases with atomic receipt, duplicate prevention, weighted-average valuation
* Append-only stock ledger, stock summary, low-stock alerts, adjustments with reasons, CSV/XLSX export
* Versioned BOMs; production plan → actuals → atomic posting; yield & consumption variance with 3 % tolerance alerts; damaged packets/pouches, scrap and wastage recorded separately
* Costing: weighted average + overheads → cost/packet, gross profit, margin
* Mobile-first salesman flow (customer → products → review → submit → track), idempotent submission
* Admin: verify stock, edit with reason, approve/reject, invoice, dispatch (no negative stock; documented partial dispatch)
* GST invoices (CGST/SGST vs IGST), FY numbering `FF/2026-27/0001`, PDF with amount in words, immutable once posted; credit notes & cancellation
* Payments (partial, allocated), receipts PDF, outstanding, 0-30/31-60/61-90/90+ ageing
* Owner dashboard (10 KPIs, 6 charts, 6 widgets, date filter) — every number from DB queries
* 15 filterable reports with CSV/Excel export; audit log with old/new values
* Demo tools: reset DB and run the benchmark from the UI
* **Not implemented (stretch):** offline PWA/IndexedDB queue, batch/expiry/FEFO, advance payments, PDF export of reports

## Technology and why
| Layer | Choice | Reason |
|---|---|---|
| API | FastAPI + Pydantic v2 | typed validation, automatic Swagger docs |
| ORM/DB | SQLAlchemy 2, Alembic, SQLite → PostgreSQL | zero-setup locally, production-ready path |
| Money/quantities | `Decimal` stored as exact text (`DecimalString`) | no floating-point error |
| Auth | PyJWT + bcrypt | stateless, standard |
| PDF/Excel | ReportLab / OpenPyXL | pure Python |
| UI | React 18, TypeScript, Vite, Tailwind 3, TanStack Query, React Router, React Hook Form + Zod, Recharts, Lucide | fast, typed, responsive. (shadcn/ui was not used; a small in-repo design system `components/ui.tsx` provides buttons, inputs, tables, badges, dialogs, toasts) |

## Architecture
`React SPA → /api/v1 (FastAPI routers, role dependencies) → services (business rules) → SQLAlchemy → DB`. Details, ER diagram, ledger/BOM/costing/unit logic: [`docs/design-note.md`](docs/design-note.md). Schema: [`docs/database-schema.md`](docs/database-schema.md).

```
FactoryFlow/
  backend/   app/{core,routers,services,models.py,schemas.py,seed.py}  alembic/  tests/
  frontend/  src/{pages,components,lib}
  docs/  screenshots/  tests/  README.md  Dockerfile  docker-compose.yml  requirements.txt  setup.ps1
```

## Quick start on Windows (VS Code)
Prerequisites: **Python 3.12**, **Node.js 20+**, Git. Extract the zip, open the `FactoryFlow` folder in VS Code, open a PowerShell terminal.

**Option A – script** (run in the repository root):
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\run-dev.ps1          # opens backend + frontend windows and the browser
```
**Option B – manual**
```powershell
# Terminal 1 — run inside FactoryFlow\backend
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then edit SECRET_KEY
python -m app.scripts.seed      # applies Alembic migration + seeds demo data
uvicorn app.main:app --reload   # API on http://localhost:8000  (Swagger: /docs)

# Terminal 2 — run inside FactoryFlow\frontend
npm install
npm run dev                     # UI on http://localhost:5173
```
(On startup the API also auto-migrates and seeds an empty database, controlled by `AUTO_MIGRATE`.) The Vite dev server proxies `/api` to port 8000, so no CORS setup is needed. To reach the UI from a phone on your Wi-Fi: `npm run dev -- --host`.

### Database setup / seed / reset
* Create + seed: `python -m app.scripts.seed` (in `backend`)
* Clean slate: `python -m app.scripts.seed --reset`
* Clean slate **and** run the benchmark: `python -m app.scripts.seed --reset --benchmark`
* New migration after model changes: `alembic revision --autogenerate -m "msg"` then `alembic upgrade head`

### Demo credentials (dummy data, password for all: `Demo@1234`)
| Role | Username |
|---|---|
| Owner | `owner` |
| Admin | `admin` |
| Salesman A (Retailer A, Retailer C) | `salesman_a` |
| Salesman B (Distributor B) | `salesman_b` |
| Production | `production` |
| Accountant | `accountant` |

Change these and `SECRET_KEY`, and set `DEMO_MODE=false`, before any real deployment.

## Benchmark scenario
Sign in as **owner → Demo tools → Run benchmark scenario** (or `python -m app.scripts.seed --reset --benchmark`). It runs steps 1-14 of the brief through the real services and shows expected vs actual values.

| Check | Expected | Produced |
|---|---|---|
| Flour / Oil / Spice closing | 120 kg / 19.5 L / 3.8 kg | ✔ |
| Pouches / Cartons closing | 306 / 21 | ✔ |
| Finished stock after production / dispatch | 238 / 88 | ✔ |
| Yield variance / Oil variance | −6 % / +5 % | ✔ |
| Taxable / CGST / SGST / Total | 7,500 / 187.50 / 187.50 / 7,875 | ✔ |
| Retailer A outstanding | 3,875 | ✔ |
| Distributor B shortage | 32 packets | ✔ |
| Cost per packet | ≈ 31.14 (5,855 / 188) | 31.1436 |

Calculations: flour avg = (100×42 + 60×45)/160 = 43.125; pouches used = 188 + 6 = 194 → 500 − 194 = 306; FG = 50 + 188 − 150 = 88; shortage = 120 − 88 = 32; material cost 1,725 + 1,470 + 240 + 485 + 135 = 4,055; + 1,800 overhead = 5,855. Full walkthrough: [`docs/benchmark-walkthrough.md`](docs/benchmark-walkthrough.md). The benchmark refuses to run twice without a reset, so it cannot create duplicate transactions.

## Testing
```powershell
cd backend ; .\.venv\Scripts\activate ; pytest -v      # 69 tests
cd ..\frontend ; npm run build                          # strict TypeScript check + production build
```
Recorded results: [`docs/test-report.md`](docs/test-report.md).

## API documentation
Swagger UI at `http://localhost:8000/docs`; endpoint/role table in [`docs/api.md`](docs/api.md).

## Deployment
* **Docker Compose** (PostgreSQL volume, API, nginx-served UI): `docker compose up --build` → UI `http://localhost:8080`, API `http://localhost:8000/docs`. Set `SECRET_KEY` in your environment first. *The Compose/PostgreSQL path was written but not executed in the build environment (no Docker available) — test it before relying on it.*
* **Frontend hosting**: `npm run build` → serve `frontend/dist` (any static host); set `VITE_API_URL` to the public API URL at build time and add the UI origin to `CORS_ORIGINS`.
* **Backend**: `Dockerfile` at the repo root; set `DATABASE_URL`, `SECRET_KEY`, `DEMO_MODE=false`.
* **Persistence**: use PostgreSQL (or a persistent disk). Never run SQLite on ephemeral storage and expect data to survive.

## Assumptions
* Single factory in Tamil Nadu (state code 33); GST rate 5 % on all products; **GST treatment is a simplified exercise assumption, not tax advice, and not an official filing/e-invoicing system** (no IRN/e-way bill, no GSTR upload). The GST report is a mappable summary only.
* Weighted-average valuation for all stock; issues valued at the average at consumption time.
* Pouch consumption = good + damaged packets + damaged pouches.
* Order prices come from the product master; only the admin can override when editing a submitted order (with a reason).
* Invoice due date = invoice date + customer payment terms; ageing buckets use days since invoice date.

## Known limitations
* No offline/PWA mode; no batch/expiry tracking.
* Finished-goods valuation uses material cost at production time (overheads appear in the costing report only).
* Login throttling is in-memory per process (use a gateway/Redis in production). JWTs are kept in `sessionStorage` (no refresh tokens).
* Decimal columns are text, so database-level numeric aggregation/sorting is done in Python — fine at this scale, not for very large data.
* No automated UI tests, and screenshots must be captured manually (see `screenshots/README.md`).
* PostgreSQL deployment is untested here.

## Implemented vs planned
Implemented: everything under *Features*. Planned: PWA offline queue, FEFO batches, advance payments/refunds, purchase-return UI, PDF report export, Playwright tests.

## License
MIT — see `LICENSE`.
