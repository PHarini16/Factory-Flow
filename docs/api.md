# API documentation

Interactive Swagger UI: **http://localhost:8000/docs** (ReDoc at `/redoc`, OpenAPI JSON at `/openapi.json`).
Base path `/api/v1`. Authenticate with `POST /auth/login` `{username,password}` → `Authorization: Bearer <token>`. Decimals are serialised as strings. Errors: `{error, message, detail}`; insufficient stock returns **409** with `detail.shortages`.

| Module | Endpoints | Roles (write / read) |
|---|---|---|
| auth | `POST /auth/login`, `GET /auth/me` | all |
| users | `GET/POST /users`, `PATCH /users/{id}` | OWNER (read: OWNER, ADMIN) |
| products | `GET/POST /products`, `PATCH /products/{id}` | ADMIN / all |
| customers | `GET/POST /customers`, `PUT /customers/{id}` | ADMIN / ADMIN, OWNER, ACCOUNTANT, SALESMAN (own only) |
| suppliers | `GET/POST /suppliers`, `PUT /suppliers/{id}` | ADMIN / ops roles |
| inventory | `GET/POST /inventory/items`, `GET /inventory/summary`, `POST /inventory/adjustments` | ADMIN, PRODUCTION (items); ADMIN (adjust) / ops roles |
| stock-ledger | `GET /stock-ledger`, `GET /stock-ledger/summary/{item_id}` | ops roles |
| purchases | `GET/POST /purchases`, `POST /purchases/{id}/receive` | ADMIN, PRODUCTION / ops roles |
| bom | `GET/POST /bom`, `GET /bom/{id}` | ADMIN, PRODUCTION / ops roles |
| production | `POST /production/plan`, `POST/GET /production/runs`, `GET /production/runs/{id}`, `POST /production/runs/{id}/costs` | PRODUCTION, ADMIN / ops roles |
| orders | `GET/POST /orders`, `GET/PUT /orders/{id}`, `POST /orders/{id}/submit\|approve\|reject\|cancel`, `GET /orders/{id}/stock-check`, `GET /orders/my-customer-sales` | SALESMAN (own), ADMIN |
| invoices | `POST /invoices/from-order/{id}`, `GET /invoices`, `GET /invoices/{id}`, `GET /invoices/{id}/pdf`, `POST /invoices/{id}/cancel`, `POST/GET /invoices/{id}/credit-notes` | ADMIN / ADMIN, OWNER, ACCOUNTANT (+SALESMAN own). *No PUT/PATCH/DELETE exists.* |
| dispatches | `GET/POST /dispatches` | ADMIN |
| payments | `GET/POST /payments`, `GET /payments/{id}/receipt` | ADMIN / ADMIN, OWNER, ACCOUNTANT |
| costing | `GET /costing/runs`, `GET /costing/weighted-average` | ops roles |
| reports | `GET /reports`, `GET /reports/{name}?date_from&date_to&format=json\|csv\|xlsx` | OWNER, ADMIN, ACCOUNTANT (PRODUCTION: production/stock/costing reports) |
| audit | `GET /audit?entity_type&action&username&limit` | OWNER, ADMIN, ACCOUNTANT |
| dashboard | `GET /dashboard?date_from&date_to` | OWNER, ADMIN, ACCOUNTANT |
| demo | `POST /demo/reset`, `POST /demo/run-benchmark` | OWNER, only when `DEMO_MODE=true` |

Report names: `sales-register, customer-sales, salesman-sales, product-sales, gst-summary, purchase-register, stock-summary, stock-ledger, production, consumption, yield-wastage, costing, payments, outstanding, ageing`.
Idempotency: orders, purchases, production runs, dispatches and payments accept `idempotency_key`; re-sending returns the original record without a second posting.
