# Test report

Executed in the development sandbox with Python 3.12, pytest 9, SQLite (fresh database per test, copied from a seeded template).

```
cd backend && pytest -v
```
**Result: 69 passed, 0 failed** (≈13 s). Frontend: `npm run build` (TypeScript strict type-check + Vite production build) succeeded. The UI itself has **no automated browser tests**; its screens were type-checked and the API calls it makes are covered by the backend tests (see Known limitations in the README).

## Coverage of the 20 required areas
| # | Area | Test(s) |
|---|---|---|
| 1 | Authentication | `test_api_auth_rbac`: login ok/fail, rate limit (429), expired token, hashed passwords |
| 2 | Role permissions | salesman/accountant/production/admin/owner restriction tests, own-customer filter |
| 3 | Weighted-average costing | `test_weighted_average_flour`, `..._with_unit_conversion`, `test_costing_benchmark` |
| 4 | GST | intra-state, inter-state, rounding, amount in words, invoice-level tests |
| 5 | Unit conversion | `test_unit_conversions`, `test_incompatible_units_rejected` |
| 6 | Purchase stock updates | `test_purchase_updates_stock_and_writes_ledger` |
| 7 | BOM expected consumption | `test_bom_expected_consumption`, `test_plan_flags_shortage` |
| 8 | Production deductions | `test_production_deductions_and_fg_addition` |
| 9 | FG additions | same test (238 packets) |
| 10–11 | Yield / consumption variance | `test_variance_formula`, `test_variances_and_alerts` |
| 12 | Ledger calculations | `test_ledger_reconstructs_balance`, `test_ledger_is_immutable` |
| 13 | Order approval | `test_order_submission_does_not_touch_stock`, reject/edit tests |
| 14 | Dispatch deduction | `test_dispatch_deducts_stock_and_updates_status`, partial dispatch |
| 15 | Insufficient stock | `test_insufficient_stock_blocks_dispatch`, `test_no_negative_stock`, `test_production_rolls_back_on_insufficient_stock` |
| 16–17 | Partial payments / outstanding | `test_partial_payments_and_outstanding`, `test_overpayment_rejected` |
| 18 | Duplicate prevention | duplicate supplier invoice, double receipt, idempotent order/run/dispatch/payment, duplicate payment reference |
| 19 | Cancellation / credit notes | `test_partial_credit_note_with_restock`, `test_invoice_cancellation_returns_stock...`, `test_cancel_blocked_when_payments_exist` |
| 20 | Benchmark end-to-end | `test_benchmark.py` (all expected values, dashboard/reports driven by DB, exports, PDF, HTTP-only flow) |

## Full list (pytest -v)
```
test_api_auth_rbac.py::test_login_success_and_me PASSED
test_api_auth_rbac.py::test_login_failure PASSED
test_api_auth_rbac.py::test_login_rate_limit PASSED
test_api_auth_rbac.py::test_protected_routes_require_token PASSED
test_api_auth_rbac.py::test_expired_token_rejected PASSED
test_api_auth_rbac.py::test_password_is_hashed PASSED
test_api_auth_rbac.py::test_salesman_cannot_use_admin_functions PASSED
test_api_auth_rbac.py::test_accountant_is_read_only PASSED
test_api_auth_rbac.py::test_production_role_scope PASSED
test_api_auth_rbac.py::test_owner_manages_users_admin_cannot_create PASSED
test_api_auth_rbac.py::test_salesman_sees_only_assigned_customers PASSED
test_api_auth_rbac.py::test_openapi_lists_all_modules PASSED
test_benchmark.py::test_inventory_closings PASSED
test_benchmark.py::test_finished_goods_and_shortage PASSED
test_benchmark.py::test_variances PASSED
test_benchmark.py::test_gst_invoice_and_outstanding PASSED
test_benchmark.py::test_costing PASSED
test_benchmark.py::test_benchmark_not_repeatable_without_reset PASSED
test_benchmark.py::test_benchmark_reports_and_dashboard_are_database_driven PASSED
test_benchmark.py::test_exports_and_pdf PASSED
test_benchmark.py::test_audit_log_traceability PASSED
test_benchmark.py::test_ledger_source_documents PASSED
test_benchmark.py::test_end_to_end_via_http_api PASSED
test_sales_flow.py::test_order_submission_does_not_touch_stock PASSED
test_sales_flow.py::test_salesman_cannot_order_for_unassigned_customer PASSED
test_sales_flow.py::test_salesman_price_override_ignored PASSED
test_sales_flow.py::test_order_idempotency PASSED
test_sales_flow.py::test_edit_requires_reason_and_is_audited PASSED
test_sales_flow.py::test_reject_needs_reason_and_blocks_invoice PASSED
test_sales_flow.py::test_invoice_intra_state_and_numbering PASSED
test_sales_flow.py::test_invoice_interstate_igst PASSED
test_sales_flow.py::test_second_invoice_for_same_order_blocked PASSED
test_sales_flow.py::test_dispatch_deducts_stock_and_updates_status PASSED
test_sales_flow.py::test_insufficient_stock_blocks_dispatch PASSED
test_sales_flow.py::test_partial_dispatch_requires_remarks_then_completes PASSED
test_sales_flow.py::test_dispatch_idempotent PASSED
test_sales_flow.py::test_partial_payments_and_outstanding PASSED
test_sales_flow.py::test_overpayment_rejected PASSED
test_sales_flow.py::test_duplicate_payment_reference_and_key_blocked PASSED
test_sales_flow.py::test_fifo_allocation_without_invoice PASSED
test_sales_flow.py::test_partial_credit_note_with_restock PASSED
test_sales_flow.py::test_invoice_cancellation_returns_stock_and_issues_credit_note PASSED
test_sales_flow.py::test_cancel_blocked_when_payments_exist PASSED
test_sales_flow.py::test_posted_invoices_have_no_edit_or_delete_api PASSED
test_stock_purchase_production.py::test_purchase_updates_stock_and_writes_ledger PASSED
test_stock_purchase_production.py::test_duplicate_supplier_invoice_blocked PASSED
test_stock_purchase_production.py::test_idempotent_purchase_returns_same_record PASSED
test_stock_purchase_production.py::test_double_receipt_prevented PASSED
test_stock_purchase_production.py::test_no_negative_stock PASSED
test_stock_purchase_production.py::test_ledger_is_immutable PASSED
test_stock_purchase_production.py::test_ledger_reconstructs_balance PASSED
test_stock_purchase_production.py::test_bom_expected_consumption PASSED
test_stock_purchase_production.py::test_plan_flags_shortage PASSED
test_stock_purchase_production.py::test_production_deductions_and_fg_addition PASSED
test_stock_purchase_production.py::test_variances_and_alerts PASSED
test_stock_purchase_production.py::test_production_rolls_back_on_insufficient_stock PASSED
test_stock_purchase_production.py::test_production_idempotent PASSED
test_stock_purchase_production.py::test_unit_conversion_in_actuals PASSED
test_stock_purchase_production.py::test_bom_versioning_keeps_history PASSED
test_stock_purchase_production.py::test_costing_benchmark PASSED
test_units_gst_costing.py::test_unit_conversions PASSED
test_units_gst_costing.py::test_incompatible_units_rejected PASSED
test_units_gst_costing.py::test_gst_intra_state PASSED
test_units_gst_costing.py::test_gst_inter_state PASSED
test_units_gst_costing.py::test_gst_rounding_is_decimal_exact PASSED
test_units_gst_costing.py::test_amount_in_words PASSED
test_units_gst_costing.py::test_variance_formula PASSED
test_units_gst_costing.py::test_weighted_average_flour PASSED
test_units_gst_costing.py::test_weighted_average_with_unit_conversion PASSED
```
