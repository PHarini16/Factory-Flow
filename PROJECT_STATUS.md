# Project status

**State: runnable.** Backend (FastAPI) and frontend (React) build and start; 69 backend tests pass; the benchmark reproduces every expected value from a clean database.

## Implemented
Auth + RBAC (JWT, bcrypt, server-side role checks, login throttle) · master data CRUD · purchases/receipts with weighted-average costing · immutable stock ledger · versioned BOM + production runs with variance/alerts/atomic rollback · costing & overheads · mobile salesman ordering · order approval/edit/reject · GST invoices + PDF · credit notes & cancellation · dispatch (incl. documented partial) · payments & receipts PDF · outstanding & ageing · 15 reports with CSV/XLSX export · dashboard · audit log · user management · demo reset/benchmark tools · Alembic migration · Docker/Compose · PowerShell setup.

## Not implemented / limitations (see README)
Offline PWA + IndexedDB queue (stretch) · batch/expiry/FEFO (stretch) · advance payments / refunds · purchase returns UI (ledger type exists) · PDF export of reports (CSV/XLSX only) · automated browser/UI tests · screenshots · PostgreSQL path not exercised in CI · in-memory login throttle (per process) · finished-goods valuation excludes overhead.

## Next steps
1. Capture screenshots. 2. Add Playwright UI tests. 3. Run the Compose stack against PostgreSQL and add a migration test. 4. Add advance-payment and purchase-return workflows. 5. Implement the offline order queue.
