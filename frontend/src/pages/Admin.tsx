import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FlaskConical, Plus, RotateCcw } from "lucide-react";
import { api, download, errorMessage, fmtDate, money, num, qty } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, ConfirmDialog, DataTable, Field, Modal, PageHeader, useToast } from "../components/ui";

const LABELS: Record<string, string> = { "sales-register": "Sales register", "customer-sales": "Customer-wise sales", "salesman-sales": "Salesman-wise sales", "product-sales": "Product-wise sales", "gst-summary": "GST outward supply summary",
  "purchase-register": "Purchase register", "stock-summary": "Stock summary", "stock-ledger": "Stock ledger", production: "Production report", consumption: "Planned vs actual consumption", "yield-wastage": "Yield & wastage",
  costing: "Production costing", payments: "Payments & collections", outstanding: "Customer outstanding", ageing: "Receivables ageing" };

export function Reports() {
  const toast = useToast();
  const d = new Date();
  const [name, setName] = useState("");
  const [from, setFrom] = useState(new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10));
  const [to, setTo] = useState(d.toISOString().slice(0, 10));
  const names = useQuery({ queryKey: ["report-list"], queryFn: async () => (await api.get("/reports")).data as string[] });
  const current = name || names.data?.[0] || "";
  const rep = useQuery({ queryKey: ["report", current, from, to], enabled: !!current, queryFn: async () => (await api.get(`/reports/${current}`, { params: { date_from: from, date_to: to } })).data });
  const exp = (format: string) => download(`/reports/${current}`, { date_from: from, date_to: to, format }).catch((e) => toast.error(errorMessage(e)));
  const fmt = (c: any, v: any) => {
    if (v === null || v === undefined || v === "") return "-";
    if (typeof v === "boolean") return v ? <Badge tone="red">Yes</Badge> : "No";
    if (c.key === "status" || c.key === "alert") return <Badge tone={["ALERT", "CANCELLED"].includes(v) ? "red" : "green"}>{v}</Badge>;
    if (c.numeric) return /pct|var|margin/i.test(c.key + c.label) ? `${num(v).toFixed(2)}%` : /qty|quantity|expected|good|batches|damaged|scrap|invoices|bom|days|standard|actual|difference|rate$|reorder/i.test(c.key) ? qty(v) : money(v);
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(v))) return fmtDate(v);
    return String(v);
  };
  const cols = (rep.data?.columns || []).map((c: any) => ({ key: c.key, header: c.label, align: c.numeric ? ("right" as const) : undefined, render: (r: any) => fmt(c, r[c.key]) }));
  return (
    <>
      <PageHeader title="Reports" description="Every report is a live database query with CSV and Excel export." />
      <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="lg:col-span-2"><Field label="Report"><select className="input" value={current} onChange={(e) => setName(e.target.value)}>{(names.data || []).map((n) => <option key={n} value={n}>{LABELS[n] || n}</option>)}</select></Field></div>
        <Field label="From"><input type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} /></Field><Field label="To"><input type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <div className="flex items-end gap-2"><Button variant="secondary" onClick={() => exp("csv")}><Download className="h-4 w-4" />CSV</Button><Button variant="secondary" onClick={() => exp("xlsx")}><Download className="h-4 w-4" />Excel</Button></div>
      </Card>
      {rep.data?.note && <p className="mb-3 rounded-lg bg-sky-50 p-3 text-sm text-sky-900">{rep.data.note}</p>}
      <Card><DataTable loading={rep.isLoading} error={rep.error} rows={rep.data?.rows} columns={cols} rowKey={(_: any, i: number) => i} /></Card>
      <p className="mt-2 text-xs text-slate-500">Date range applies to transaction-dated reports; Outstanding, Ageing and Stock summary are as of today.</p>
    </>
  );
}

export function AuditPage() {
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const q = useQuery({ queryKey: ["audit", entity, action], queryFn: async () => (await api.get("/audit", { params: { entity_type: entity || undefined, action: action || undefined, limit: 300 } })).data });
  return (
    <>
      <PageHeader title="Audit log" description="Who did what, and when. Old/new values are kept for financial and stock-affecting actions." />
      <div className="mb-4 flex flex-wrap gap-2">
        <select className="input max-w-[200px]" value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="Entity"><option value="">All entities</option>{["Invoice", "Dispatch", "Payment", "Purchase", "ProductionRun", "SalesOrder", "Product", "Customer", "InventoryItem", "User", "BOM"].map((e) => <option key={e}>{e}</option>)}</select>
        <input className="input max-w-[200px]" placeholder="Action (e.g. POST)" value={action} onChange={(e) => setAction(e.target.value.toUpperCase())} />
      </div>
      <Card><DataTable loading={q.isLoading} error={q.error} rows={q.data}
        columns={[{ key: "created_at", header: "When", render: (r: any) => new Date(r.created_at + "Z").toLocaleString("en-IN") }, { key: "username", header: "User" }, { key: "action", header: "Action", render: (r: any) => <Badge tone="teal">{r.action}</Badge> },
          { key: "e", header: "Entity", render: (r: any) => `${r.entity_type}${r.entity_id ? " #" + r.entity_id : ""}` }, { key: "old_values", header: "Old", className: "max-w-[220px] truncate font-mono text-xs", render: (r: any) => (r.old_values ? JSON.stringify(r.old_values) : "") },
          { key: "new_values", header: "New", className: "max-w-[260px] truncate font-mono text-xs", render: (r: any) => (r.new_values ? JSON.stringify(r.new_values) : "") }]} /></Card>
    </>
  );
}

export function UsersPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ username: "", full_name: "", password: "", role: "SALESMAN" });
  const q = useQuery({ queryKey: ["users"], queryFn: async () => (await api.get("/users")).data });
  const create = useMutation({ mutationFn: async () => (await api.post("/users", f)).data, onSuccess: () => { toast.success("User created"); setOpen(false); qc.invalidateQueries({ queryKey: ["users"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const patch = useMutation({ mutationFn: async (a: { id: number; body: any }) => (await api.patch(`/users/${a.id}`, a.body)).data, onSuccess: () => { toast.success("User updated"); qc.invalidateQueries({ queryKey: ["users"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <>
      <PageHeader title="Users & roles" description="Owner-only. Roles are enforced by the backend on every API call." actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add user</Button>} />
      <Card><DataTable loading={q.isLoading} error={q.error} rows={q.data} columns={[{ key: "username", header: "Username" }, { key: "full_name", header: "Name" },
        { key: "role", header: "Role", render: (u: any) => <select aria-label={`Role of ${u.username}`} className="input max-w-[160px]" value={u.role} disabled={u.id === user?.id} onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })}>{["OWNER", "ADMIN", "SALESMAN", "PRODUCTION", "ACCOUNTANT"].map((r) => <option key={r}>{r}</option>)}</select> },
        { key: "is_active", header: "Status", render: (u: any) => <Badge tone={u.is_active ? "green" : "slate"}>{u.is_active ? "Active" : "Disabled"}</Badge> },
        { key: "a", header: "", render: (u: any) => u.id !== user?.id && <Button variant="ghost" onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>{u.is_active ? "Disable" : "Enable"}</Button> }]} /></Card>
      <Modal open={open} title="Add user" onClose={() => setOpen(false)}>
        <div className="grid gap-3 sm:grid-cols-2"><Field label="Username"><input className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field><Field label="Full name"><input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
          <Field label="Password (min 8)"><input type="password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
          <Field label="Role"><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{["OWNER", "ADMIN", "SALESMAN", "PRODUCTION", "ACCOUNTANT"].map((r) => <option key={r}>{r}</option>)}</select></Field></div>
        <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={create.isPending} onClick={() => create.mutate()}>Create</Button></div>
      </Modal>
    </>
  );
}

export function DemoTools() {
  const { logout } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<any>(null);
  const run = useMutation({ mutationFn: async () => (await api.post("/demo/run-benchmark")).data, onSuccess: (d) => { setResult(d); toast.success("Benchmark executed through the real services"); qc.invalidateQueries(); }, onError: (e) => toast.error(errorMessage(e)) });
  const reset = useMutation({ mutationFn: async () => (await api.post("/demo/reset")).data, onSuccess: () => { toast.success("Database reset. Please sign in again."); setConfirm(false); logout(); location.href = "/login"; }, onError: (e) => toast.error(errorMessage(e)) });
  const rows = result ? [["Flour closing (kg)", result.flour_closing, "120"], ["Oil closing (L)", result.oil_closing, "19.5"], ["Spice mix closing (kg)", result.spice_closing, "3.8"], ["Pouches closing", result.pouches_closing, "306"], ["Cartons closing", result.cartons_closing, "21"],
    ["Finished after production", result.finished_after_production, "238"], ["Finished after dispatch", result.finished_after_dispatch, "88"], ["Yield variance %", result.yield_variance_pct, "-6"], ["Oil variance %", result.oil_variance_pct, "5"],
    ["Taxable amount", result.taxable, "7500"], ["CGST", result.cgst, "187.5"], ["SGST", result.sgst, "187.5"], ["Invoice total", result.invoice_total, "7875"], ["Retailer A outstanding", result.retailer_a_outstanding, "3875"],
    ["Distributor B shortage", result.distributor_b_shortage, "32"], ["Cost per packet", result.cost_per_packet, "≈31.14"]] : [];
  return (
    <>
      <PageHeader title="Demo tools" description="Reset the database to seed data, then run the mandatory benchmark scenario (steps 1–14) through the real services." />
      <div className="mb-5 flex flex-wrap gap-2"><Button variant="danger" onClick={() => setConfirm(true)}><RotateCcw className="h-4 w-4" />Reset demo database</Button><Button loading={run.isPending} onClick={() => run.mutate()}><FlaskConical className="h-4 w-4" />Run benchmark scenario</Button></div>
      <p className="mb-4 text-sm text-slate-500">Values below are read back from the database after the run — they are not hardcoded. The benchmark refuses to run twice without a reset.</p>
      {result && <Card><DataTable rows={rows.map(([k, v, e]) => ({ k, v, e }))} rowKey={(r: any) => r.k} columns={[{ key: "k", header: "Check" }, { key: "e", header: "Expected" }, { key: "v", header: "Actual", render: (r: any) => <b>{r.k.includes("Cost per") ? num(r.v).toFixed(4) : String(num(r.v))}</b> },
        { key: "ok", header: "", render: (r: any) => (r.e.startsWith("≈") ? (Math.abs(num(r.v) - 31.14) < 0.005 ? <Badge tone="green">Match</Badge> : <Badge tone="red">Differs</Badge>) : num(r.v) === num(r.e) ? <Badge tone="green">Match</Badge> : <Badge tone="red">Differs</Badge>) }]} /></Card>}
      <ConfirmDialog open={confirm} danger title="Reset database" message="This deletes ALL transactions and users you created and restores the seed data. Intended for demos only." confirmLabel="Reset everything" loading={reset.isPending} onClose={() => setConfirm(false)} onConfirm={() => reset.mutate()} />
    </>
  );
}
