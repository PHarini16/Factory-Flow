import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, Plus } from "lucide-react";
import { api, download, errorMessage, fmtDate, money, newKey, num, qty, today } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, ConfirmDialog, DataTable, Field, Modal, PageHeader, StatusBadge, useToast } from "../components/ui";

const invalidate = (qc: any) => ["invoices", "orders", "order", "payments", "dashboard", "inventory", "ledger"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

export function Invoices() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const isAdmin = user?.role === "ADMIN";
  const [sel, setSel] = useState<any>(null);
  const [mode, setMode] = useState<"" | "cancel" | "credit">("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [cq, setCq] = useState<Record<number, string>>({});
  const [status, setStatus] = useState("");
  const list = useQuery({ queryKey: ["invoices", status], queryFn: async () => (await api.get("/invoices", { params: { status: status || undefined } })).data });
  const cur = (list.data || []).find((i: any) => i.id === sel?.id) || sel;

  const act = useMutation({
    mutationFn: async () => mode === "cancel" ? (await api.post(`/invoices/${cur.id}/cancel`, { reason })).data
      : (await api.post(`/invoices/${cur.id}/credit-notes`, { reason, restock, lines: Object.entries(cq).filter(([, v]) => num(v) > 0).map(([k, v]) => ({ invoice_item_id: Number(k), quantity: v })) })).data,
    onSuccess: () => { toast.success(mode === "cancel" ? "Invoice cancelled; credit note issued and stock returned" : "Credit note issued"); setMode(""); setReason(""); setCq({}); invalidate(qc); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="Invoices" description="Posted GST invoices are immutable. Corrections use cancellation or credit notes." />
      <select className="input mb-4 max-w-[200px]" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All</option><option value="POSTED">Posted</option><option value="CANCELLED">Cancelled</option></select>
      <Card><DataTable loading={list.isLoading} error={list.error} rows={list.data} onRowClick={setSel}
        columns={[{ key: "invoice_no", header: "Invoice" }, { key: "invoice_date", header: "Date", render: (r: any) => fmtDate(r.invoice_date) }, { key: "buyer_name", header: "Customer" }, { key: "t", header: "Taxable", align: "right", render: (r: any) => money(r.taxable_amount) },
          { key: "tax", header: "GST", align: "right", render: (r: any) => money(num(r.cgst) + num(r.sgst) + num(r.igst)) }, { key: "total", header: "Total", align: "right", render: (r: any) => money(r.total) }, { key: "outstanding", header: "Outstanding", align: "right", render: (r: any) => money(r.outstanding) },
          { key: "status", header: "Status", render: (r: any) => <StatusBadge status={r.status} /> }, { key: "d", header: "Dispatch", render: (r: any) => <StatusBadge status={r.dispatch_status} /> }]} /></Card>

      <Modal open={!!cur && !mode} title={cur?.invoice_no || ""} onClose={() => setSel(null)} wide>
        {cur && <>
          <div className="mb-3 grid gap-3 text-sm sm:grid-cols-2">
            <div><p className="text-xs text-slate-500">Bill to</p><p className="font-medium">{cur.buyer_name}</p><p className="text-slate-600">{cur.buyer_address}</p><p className="text-slate-600">GSTIN: {cur.buyer_gstin || "Unregistered"}</p></div>
            <div><p className="text-xs text-slate-500">Place of supply</p><p className="font-medium">{cur.place_of_supply} ({cur.place_of_supply_code})</p><p className="text-slate-600">{cur.is_interstate ? "Inter-state → IGST" : "Intra-state → CGST + SGST"}</p><p className="text-slate-600">Due {fmtDate(cur.due_date)} · FY {cur.financial_year}</p></div>
          </div>
          <DataTable rows={cur.items} rowKey={(i: any) => i.id} columns={[{ key: "description", header: "Item" }, { key: "hsn_code", header: "HSN" }, { key: "quantity", header: "Qty", align: "right", render: (i: any) => qty(i.quantity) }, { key: "unit_price", header: "Rate", align: "right", render: (i: any) => money(i.unit_price) },
            { key: "taxable_amount", header: "Taxable", align: "right", render: (i: any) => money(i.taxable_amount) }, { key: "cgst", header: "CGST", align: "right", render: (i: any) => money(i.cgst) }, { key: "sgst", header: "SGST", align: "right", render: (i: any) => money(i.sgst) }, { key: "igst", header: "IGST", align: "right", render: (i: any) => money(i.igst) },
            { key: "total", header: "Total", align: "right", render: (i: any) => money(i.total) }, { key: "dq", header: "Dispatched", align: "right", render: (i: any) => qty(i.dispatched_qty) }]} />
          <div className="mt-3 grid grid-cols-3 gap-3 rounded-lg bg-slate-50 p-3 text-sm"><div><p className="text-xs text-slate-500">Invoice total</p><p className="font-semibold">{money(cur.total)}</p></div><div><p className="text-xs text-slate-500">Received + credits</p><p className="font-semibold">{money(num(cur.paid) + num(cur.credited))}</p></div><div><p className="text-xs text-slate-500">Outstanding</p><p className="font-semibold text-rose-600">{money(cur.outstanding)}</p></div></div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => download(`/invoices/${cur.id}/pdf`).catch((e) => toast.error(errorMessage(e)))}><Download className="h-4 w-4" />Download PDF</Button>
            {isAdmin && cur.status === "POSTED" && <><Button variant="secondary" onClick={() => setMode("credit")}>Issue credit note</Button><Button variant="danger" onClick={() => setMode("cancel")}>Cancel invoice</Button></>}
          </div>
        </>}
      </Modal>

      <ConfirmDialog open={mode === "cancel"} danger title="Cancel invoice" message="This issues a full credit note and returns dispatched goods to stock. Not allowed once payments are allocated." confirmLabel="Cancel invoice" loading={act.isPending}
        onClose={() => setMode("")} onConfirm={() => (reason.trim() ? act.mutate() : toast.error("Reason is required"))}><input className="input" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} /></ConfirmDialog>

      <Modal open={mode === "credit"} title="Issue credit note" onClose={() => setMode("")}>
        {cur && <div className="space-y-3">
          {cur.items.map((i: any) => <div key={i.id} className="grid grid-cols-[1fr_100px] items-end gap-2"><p className="text-sm">{i.description} <span className="text-xs text-slate-500">(creditable {qty(num(i.quantity) - num(i.returned_qty))})</span></p><Field label="Credit qty"><input className="input" inputMode="decimal" value={cq[i.id] || ""} onChange={(e) => setCq({ ...cq, [i.id]: e.target.value })} /></Field></div>)}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />Goods returned to stock (SALES_RETURN)</label>
          <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setMode("")}>Back</Button><Button loading={act.isPending} disabled={reason.length < 3 || !Object.values(cq).some((v) => num(v) > 0)} onClick={() => act.mutate()}>Issue credit note</Button></div>
        </div>}
      </Modal>
    </>
  );
}

export function Dispatch() {
  const qc = useQueryClient();
  const toast = useToast();
  const [invId, setInvId] = useState("");
  const [lines, setLines] = useState<Record<number, string>>({});
  const [remarks, setRemarks] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [shortage, setShortage] = useState<any[] | null>(null);
  const [key, setKey] = useState(newKey);
  const invs = useQuery({ queryKey: ["invoices", "POSTED"], queryFn: async () => (await api.get("/invoices", { params: { status: "POSTED" } })).data });
  const prods = useQuery({ queryKey: ["products", "all"], queryFn: async () => (await api.get("/products")).data });
  const stock = useQuery({ queryKey: ["inventory", "FINISHED"], queryFn: async () => (await api.get("/inventory/summary", { params: { item_type: "FINISHED" } })).data });
  const hist = useQuery({ queryKey: ["dispatches"], queryFn: async () => (await api.get("/dispatches")).data });
  const open = (invs.data || []).filter((i: any) => i.dispatch_status !== "DISPATCHED");
  const inv = open.find((i: any) => String(i.id) === invId);
  const avail = (pid: number) => { const p = (prods.data || []).find((x: any) => x.id === pid); return num((stock.data?.items || []).find((s: any) => s.item_id === p?.inventory_item_id)?.quantity); };
  const remaining = (i: any) => num(i.quantity) - num(i.returned_qty) - num(i.dispatched_qty);
  const want = (i: any) => (lines[i.id] !== undefined ? num(lines[i.id]) : remaining(i));
  const partial = inv?.items.some((i: any) => want(i) < remaining(i) && remaining(i) > 0);

  const go = useMutation({
    mutationFn: async () => (await api.post("/dispatches", { invoice_id: Number(invId), remarks, vehicle_no: vehicle, idempotency_key: key, lines: inv.items.filter((i: any) => remaining(i) > 0 && want(i) > 0).map((i: any) => ({ invoice_item_id: i.id, quantity: String(want(i)) })) })).data,
    onSuccess: (d) => { toast.success(`Dispatch ${d.dispatch_no} recorded — finished goods reduced`); setInvId(""); setLines({}); setRemarks(""); setShortage(null); setKey(newKey()); invalidate(qc); qc.invalidateQueries({ queryKey: ["dispatches"] }); },
    onError: (e: any) => { setShortage(e?.response?.data?.detail?.shortages || null); toast.error(errorMessage(e)); },
  });

  return (
    <>
      <PageHeader title="Dispatch" description="Finished-goods stock is reduced only when a dispatch is confirmed. Negative stock is never allowed." />
      <Card className="mb-6 p-4">
        <Field label="Invoice awaiting dispatch"><select className="input max-w-md" value={invId} onChange={(e) => { setInvId(e.target.value); setLines({}); setShortage(null); }}><option value="">Select invoice…</option>{open.map((i: any) => <option key={i.id} value={i.id}>{i.invoice_no} — {i.buyer_name} ({i.dispatch_status.replace("_", " ").toLowerCase()})</option>)}</select></Field>
        {inv && <>
          <div className="mt-4"><DataTable rows={inv.items} rowKey={(i: any) => i.id} columns={[{ key: "description", header: "Item" }, { key: "quantity", header: "Invoiced", align: "right", render: (i: any) => qty(i.quantity) }, { key: "dispatched_qty", header: "Already sent", align: "right", render: (i: any) => qty(i.dispatched_qty) },
            { key: "remaining", header: "Remaining", align: "right", render: (i: any) => qty(remaining(i)) }, { key: "av", header: "In stock", align: "right", render: (i: any) => <span className={avail(i.product_id) < want(i) ? "font-semibold text-rose-600" : ""}>{qty(avail(i.product_id))}</span> },
            { key: "q", header: "Dispatch now", render: (i: any) => <input aria-label={`Dispatch ${i.description}`} className="input w-24" inputMode="decimal" value={lines[i.id] ?? String(remaining(i))} onChange={(e) => setLines({ ...lines, [i.id]: e.target.value })} /> }]} /></div>
          {inv.items.some((i: any) => avail(i.product_id) < want(i)) && <p className="mt-3 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle className="h-4 w-4" />Requested quantity exceeds available stock. Reduce the quantity for a documented partial dispatch.</p>}
          {shortage && <div className="mt-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-800" role="alert">{shortage.map((s) => <p key={s.product}>{s.product}: requested {s.requested}, available {s.available}, shortage <b>{s.shortage}</b></p>)}</div>}
          <div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="Vehicle no. (optional)"><input className="input" value={vehicle} onChange={(e) => setVehicle(e.target.value)} /></Field>
            <Field label={partial ? "Remarks (required for partial dispatch)" : "Remarks"}><input className="input" value={remarks} onChange={(e) => setRemarks(e.target.value)} /></Field></div>
          <div className="mt-4 flex justify-end"><Button loading={go.isPending} disabled={partial && !remarks.trim()} onClick={() => go.mutate()}>Confirm dispatch</Button></div>
        </>}
      </Card>
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Dispatch history</h2>
      <Card><DataTable loading={hist.isLoading} rows={hist.data} columns={[{ key: "dispatch_no", header: "Dispatch" }, { key: "dispatch_date", header: "Date", render: (r: any) => fmtDate(r.dispatch_date) }, { key: "invoice", header: "Invoice", render: (r: any) => (invs.data || []).find((i: any) => i.id === r.invoice_id)?.invoice_no || `#${r.invoice_id}` },
        { key: "q", header: "Quantity", align: "right", render: (r: any) => qty(r.items.reduce((s: number, i: any) => s + num(i.quantity), 0)) }, { key: "remarks", header: "Remarks" }]} /></Card>
    </>
  );
}

export function Payments() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const isAdmin = user?.role === "ADMIN";
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ customer_id: "", invoice_id: "", amount: "", mode: "UPI", reference: "", payment_date: today() });
  const [key, setKey] = useState(newKey);
  const pays = useQuery({ queryKey: ["payments"], queryFn: async () => (await api.get("/payments")).data });
  const invs = useQuery({ queryKey: ["invoices", "POSTED"], queryFn: async () => (await api.get("/invoices", { params: { status: "POSTED" } })).data });
  const out = useQuery({ queryKey: ["outstanding"], queryFn: async () => (await api.get("/reports/outstanding")).data });
  const custs = useMemo(() => { const m = new Map(); (invs.data || []).forEach((i: any) => m.set(i.customer_id, i.buyer_name)); return [...m.entries()]; }, [invs.data]);
  const openInv = (invs.data || []).filter((i: any) => String(i.customer_id) === f.customer_id && num(i.outstanding) > 0);
  const chosen = openInv.find((i: any) => String(i.id) === f.invoice_id);
  const save = useMutation({
    mutationFn: async () => (await api.post("/payments", { ...f, customer_id: Number(f.customer_id), invoice_id: f.invoice_id ? Number(f.invoice_id) : null, idempotency_key: key })).data,
    onSuccess: (p) => { toast.success(`Receipt ${p.receipt_no} recorded`); setOpen(false); setKey(newKey()); setF({ ...f, amount: "", reference: "" }); invalidate(qc); qc.invalidateQueries({ queryKey: ["outstanding"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <PageHeader title="Payments & receivables" description="Partial payments are allocated to invoices; overpayment is rejected." actions={isAdmin && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Record payment</Button>} />
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Outstanding invoices</h2>
      <Card className="mb-6"><DataTable loading={out.isLoading} error={out.error} rows={out.data?.rows} rowKey={(r: any) => r.invoice}
        columns={[{ key: "customer", header: "Customer" }, { key: "invoice", header: "Invoice" }, { key: "due_date", header: "Due", render: (r: any) => fmtDate(r.due_date) }, { key: "amount", header: "Invoice amt", align: "right", render: (r: any) => money(r.amount) },
          { key: "received", header: "Received", align: "right", render: (r: any) => money(r.received) }, { key: "outstanding", header: "Outstanding", align: "right", render: (r: any) => <b>{money(r.outstanding)}</b> },
          { key: "days_overdue", header: "Days overdue", align: "right", render: (r: any) => (r.days_overdue > 0 ? <Badge tone="red">{r.days_overdue}</Badge> : "-") }]} /></Card>
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Payment register</h2>
      <Card><DataTable loading={pays.isLoading} error={pays.error} rows={pays.data}
        columns={[{ key: "receipt_no", header: "Receipt" }, { key: "payment_date", header: "Date", render: (r: any) => fmtDate(r.payment_date) }, { key: "c", header: "Customer", render: (r: any) => r.customer.name }, { key: "mode", header: "Mode" }, { key: "reference", header: "Reference" },
          { key: "amount", header: "Amount", align: "right", render: (r: any) => money(r.amount) }, { key: "r", header: "", render: (r: any) => <button className="text-brand-700 hover:underline" onClick={() => download(`/payments/${r.id}/receipt`).catch((e) => toast.error(errorMessage(e)))}>Receipt PDF</button> }]} /></Card>

      <Modal open={open} title="Record payment" onClose={() => setOpen(false)}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Customer"><select className="input" value={f.customer_id} onChange={(e) => setF({ ...f, customer_id: e.target.value, invoice_id: "" })}><option value="">Select…</option>{custs.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></Field>
          <Field label="Invoice"><select className="input" value={f.invoice_id} onChange={(e) => { const i = openInv.find((x: any) => String(x.id) === e.target.value); setF({ ...f, invoice_id: e.target.value, amount: i ? String(num(i.outstanding)) : f.amount }); }}><option value="">Oldest first (auto-allocate)</option>{openInv.map((i: any) => <option key={i.id} value={i.id}>{i.invoice_no} — due {money(i.outstanding)}</option>)}</select></Field>
          <Field label="Amount (₹)" hint={chosen ? `Outstanding ${money(chosen.outstanding)}` : undefined}><input className="input" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field label="Mode"><select className="input" value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>{["CASH", "UPI", "BANK", "CHEQUE"].map((m) => <option key={m}>{m}</option>)}</select></Field>
          <Field label="Transaction reference"><input className="input" value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
          <Field label="Payment date"><input type="date" className="input" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} /></Field>
        </div>
        <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={save.isPending} disabled={!f.customer_id || !num(f.amount)} onClick={() => save.mutate()}>Record payment</Button></div>
      </Modal>
    </>
  );
}
