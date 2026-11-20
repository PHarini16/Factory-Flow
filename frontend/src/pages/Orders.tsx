import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, FileText } from "lucide-react";
import { api, errorMessage, fmtDate, money, num, qty } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Card, ConfirmDialog, DataTable, Modal, PageHeader, Skeleton, StatusBadge, useToast } from "../components/ui";
import { OrderCards } from "./Salesman";

const STATUSES = ["", "DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "INVOICED", "PARTIALLY_DISPATCHED", "DISPATCHED", "CANCELLED"];

export function OrdersPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const q = useQuery({ queryKey: ["orders", status], queryFn: async () => (await api.get("/orders", { params: { status: status || undefined } })).data });
  const rows = (q.data || []).filter((o: any) => !search || (o.order_no + o.customer.name).toLowerCase().includes(search.toLowerCase()));
  return (
    <>
      <PageHeader title={user?.role === "SALESMAN" ? "My orders" : "Orders"} description="Track every order from submission to dispatch."
        actions={user?.role === "SALESMAN" ? undefined : undefined} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input className="input max-w-xs" placeholder="Search order or customer" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input max-w-[220px]" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">{STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, " ") : "All statuses"}</option>)}</select>
      </div>
      {user?.role === "SALESMAN" ? <OrderCards list={rows} loading={q.isLoading} /> : (
        <Card><DataTable loading={q.isLoading} error={q.error} rows={rows} onRowClick={(r: any) => nav(`/orders/${r.id}`)}
          columns={[{ key: "order_no", header: "Order" }, { key: "order_date", header: "Date", render: (r: any) => fmtDate(r.order_date) }, { key: "customer", header: "Customer", render: (r: any) => r.customer.name },
            { key: "status", header: "Status", render: (r: any) => <StatusBadge status={r.status} /> }, { key: "total_estimate", header: "Est. total", align: "right", render: (r: any) => money(r.total_estimate) }]} /></Card>
      )}
    </>
  );
}

export function OrderDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<"reject" | "cancel" | "edit" | null>(null);
  const [reason, setReason] = useState("");
  const [edit, setEdit] = useState<Record<number, { q: string; price: string }>>({});
  const isAdmin = user?.role === "ADMIN";
  const order = useQuery({ queryKey: ["order", id], queryFn: async () => (await api.get(`/orders/${id}`)).data });
  const o = order.data;
  const check = useQuery({ queryKey: ["stock-check", id, o?.status], enabled: !!o && ["ADMIN", "OWNER"].includes(user!.role) && ["SUBMITTED", "APPROVED"].includes(o.status), queryFn: async () => (await api.get(`/orders/${id}/stock-check`)).data });
  const invoice = useQuery({ queryKey: ["order-invoice", id], enabled: !!o && ["INVOICED", "PARTIALLY_DISPATCHED", "DISPATCHED"].includes(o.status) && user!.role !== "SALESMAN", queryFn: async () => ((await api.get("/invoices")).data as any[]).find((i) => i.order_id === Number(id)) });

  const refresh = () => { qc.invalidateQueries({ queryKey: ["order", id] }); qc.invalidateQueries({ queryKey: ["orders"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); };
  const act = useMutation({
    mutationFn: async (a: { path: string; body?: any; method?: "post" | "put" }) => (await api[a.method || "post"](`/orders/${id}${a.path}`, a.body)).data,
    onSuccess: (d, a) => {
      setDialog(null); setReason(""); refresh();
      if (a.path === "/approve") toast[d.stock_warning ? "error" : "success"](d.stock_warning ? "Approved — but current finished stock is insufficient for the full quantity (see stock check)." : "Order approved");
      else toast.success("Order updated");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const mkInvoice = useMutation({
    mutationFn: async () => (await api.post(`/invoices/from-order/${id}`)).data,
    onSuccess: (inv) => { toast.success(`Invoice ${inv.invoice_no} generated`); refresh(); qc.invalidateQueries({ queryKey: ["invoices"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (order.isLoading) return <Skeleton className="h-64" />;
  if (!o) return <p className="p-6 text-slate-500">Order not found or not accessible.</p>;
  const startEdit = () => { setEdit(Object.fromEntries(o.items.map((i: any) => [i.product_id, { q: String(num(i.quantity)), price: String(num(i.unit_price)) }]))); setDialog("edit"); };

  return (
    <>
      <button onClick={() => nav(-1)} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft className="h-4 w-4" />Back</button>
      <PageHeader title={o.order_no} description={`${o.customer.name} · ${fmtDate(o.order_date)}`} actions={<StatusBadge status={o.status} />} />

      {check.data && !check.data.all_sufficient && (
        <div className="mb-4 flex gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" role="alert">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <div><p className="font-semibold">Insufficient finished-goods stock</p>
            {check.data.lines.filter((l: any) => !l.sufficient).map((l: any) => <p key={l.product_id}>{l.product}: requested {qty(l.requested)}, available {qty(l.available)}, <b>shortage {qty(l.shortage)}</b></p>)}
            <p className="mt-1 text-xs">Stock is only reduced at dispatch; a full dispatch will be blocked until production covers the shortage.</p></div>
        </div>
      )}

      <Card className="mb-4">
        <DataTable rows={o.items} rowKey={(r: any) => r.id} columns={[{ key: "p", header: "Product", render: (r: any) => r.product.name }, { key: "quantity", header: "Qty", align: "right", render: (r: any) => qty(r.quantity) },
          { key: "unit_price", header: "Price", align: "right", render: (r: any) => money(r.unit_price) }, { key: "t", header: "Taxable", align: "right", render: (r: any) => money(num(r.quantity) * num(r.unit_price)) }]} />
        <div className="space-y-1 border-t p-4 text-sm"><div className="flex justify-between"><span className="text-slate-500">Subtotal</span><span>{money(o.subtotal)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">GST estimate</span><span>{money(o.tax_estimate)}</span></div>
          <div className="flex justify-between font-semibold"><span>Estimated total</span><span>{money(o.total_estimate)}</span></div></div>
      </Card>
      {o.remarks && <p className="mb-2 text-sm text-slate-600"><b>Remarks:</b> {o.remarks}</p>}
      {o.change_reason && <p className="mb-2 text-sm text-slate-600"><b>Admin change:</b> {o.change_reason}</p>}
      {o.rejection_reason && <p className="mb-2 text-sm text-rose-700"><b>Reason:</b> {o.rejection_reason}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {isAdmin && o.status === "SUBMITTED" && <>
          <Button loading={act.isPending} onClick={() => act.mutate({ path: "/approve" })}>Approve</Button>
          <Button variant="secondary" onClick={startEdit}>Edit order</Button>
          <Button variant="danger" onClick={() => setDialog("reject")}>Reject</Button></>}
        {isAdmin && o.status === "APPROVED" && <Button loading={mkInvoice.isPending} onClick={() => mkInvoice.mutate()}><FileText className="h-4 w-4" />Generate GST invoice</Button>}
        {invoice.data && <Link to="/invoices"><Button variant="secondary">View invoice {invoice.data.invoice_no}</Button></Link>}
        {isAdmin && o.status === "INVOICED" && <Link to="/dispatch"><Button variant="secondary">Go to dispatch</Button></Link>}
        {["DRAFT", "SUBMITTED"].includes(o.status) && (user?.role === "SALESMAN" || isAdmin) && <Button variant="ghost" onClick={() => setDialog("cancel")}>Cancel order</Button>}
      </div>

      <ConfirmDialog open={dialog === "reject" || dialog === "cancel"} danger title={dialog === "reject" ? "Reject order" : "Cancel order"} message="Please provide a reason. This is recorded in the audit log."
        confirmLabel={dialog === "reject" ? "Reject order" : "Cancel order"} loading={act.isPending} onClose={() => setDialog(null)}
        onConfirm={() => reason.trim() ? act.mutate({ path: dialog === "reject" ? "/reject" : "/cancel", body: { reason } }) : toast.error("A reason is required")}>
        <textarea className="input" rows={3} placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </ConfirmDialog>

      <Modal open={dialog === "edit"} title="Edit order before approval" onClose={() => setDialog(null)}>
        <div className="space-y-3">
          {o.items.map((i: any) => (
            <div key={i.id} className="grid grid-cols-[1fr_90px_100px] items-end gap-2">
              <p className="text-sm font-medium">{i.product.name}</p>
              <label><span className="label">Qty</span><input className="input" inputMode="decimal" value={edit[i.product_id]?.q || ""} onChange={(e) => setEdit({ ...edit, [i.product_id]: { ...edit[i.product_id], q: e.target.value } })} /></label>
              <label><span className="label">Price</span><input className="input" inputMode="decimal" value={edit[i.product_id]?.price || ""} onChange={(e) => setEdit({ ...edit, [i.product_id]: { ...edit[i.product_id], price: e.target.value } })} /></label>
            </div>
          ))}
          <label className="block"><span className="label">Reason for change (required)</span><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setDialog(null)}>Cancel</Button>
            <Button loading={act.isPending} onClick={() => act.mutate({ method: "put", path: "", body: { reason, items: o.items.map((i: any) => ({ product_id: i.product_id, quantity: edit[i.product_id].q, unit_price: edit[i.product_id].price })) } })}>Save changes</Button></div>
        </div>
      </Modal>
    </>
  );
}
