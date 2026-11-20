# Benchmark walkthrough

Reproduce (clean database):

```powershell
cd backend
.\.venv\Scripts\activate
python -m app.scripts.seed --reset --benchmark
```
or sign in as **owner** → *Demo tools* → *Reset demo database* → *Run benchmark scenario*. The automated version is `backend/tests/test_benchmark.py`.
Nothing is hardcoded: `app/seed.py::run_benchmark` drives the same services the API uses, and every result below is read back from the database.

| Step | Action (service called) | Resulting data |
|---|---|---|
| 0 | Seed: opening stock Flour 100 kg @42, Oil 30 L @140, Spice 5 kg @200, Pouch 500 @2.50, Carton 30 @15, Murukku 50 pkts; BOM v1 | OPENING ledger rows |
| 1 | `purchase.create_purchase` 60 kg flour @45 | flour 160 kg, avg ₹43.125 |
| 2–5 | `production.complete_run` 1 batch; flour 40, oil 10.5, spice 1.2, cartons 9; good 188, damaged pouches 6 | expected 200, yield −6 %, oil +5 % |
| 6–9 | order 150 → approve → `create_invoice` → `create_dispatch` | FG 238 → 88; taxable 7,500; CGST 187.50; SGST 187.50; total 7,875 |
| 10–11 | Salesman B order 120 (Karnataka) → `stock_check` | available 88, **shortage 32** |
| 12 | payment ₹4,000 against the invoice | outstanding ₹3,875 |
| 13 | overheads labour 1,200 + gas/power 600 | overhead 1,800; total cost 5,855; ₹31.1436/packet |
| 14 | Reports | GST summary, costing, outstanding, ledger etc. |

## Actual output (`python -m app.scripts.seed --reset --benchmark`)
```
flour_closing 120 | oil_closing 19.5 | spice_closing 3.8 | pouches_closing 306 | cartons_closing 21
finished_after_production 238 | finished_after_dispatch 88
yield_variance_pct -6.0000 | oil_variance_pct 5.0000
taxable 7500.00 | cgst 187.50 | sgst 187.50 | invoice_total 7875.00 | retailer_a_outstanding 3875.00
distributor_b_shortage 32 | cost_per_packet 31.1436
```
Costs: flour 1,725 · oil 1,470 · spice 240 · pouches 485 · cartons 135 → material 4,055; + 1,800 overhead = 5,855; ÷ 188 = 31.1436 (GP/packet 18.8564, margin 37.71 %).
Note: the 120-packet order to Distributor B is Interstate (IGST). If invoiced it would be taxable ₹6,000 + IGST ₹300 — covered by `test_gst_inter_state`.
Note: oil closing (19.5 L) is below its reorder level (20 L), so the dashboard shows one low-stock alert — generated from data, as intended. Packaging cost uses **actual** consumption (194 pouches, 9 cartons), per the brief.
