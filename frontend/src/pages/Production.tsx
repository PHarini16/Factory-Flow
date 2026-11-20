import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Copy, Factory, Plus } from "lucide-react";
import { api, errorMessage, fmtDate, money, newKey, num, pct, qty, today } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, DataTable, Field, Kpi, Modal, PageHeader, Skeleton, useToast } from "../components/ui";

const runsQ = () => ({ queryKey: ["runs"], queryFn: async () => (await api.get("/production/runs")).data });

export function ProductionHome() {
  const runs = useQuery(runsQ());
  const stock = useQuery({ queryKey: ["inventory", ""], queryFn: async () => (await api.get("/inventory/summary")).data });
  const list: any[] = runs.data || [];
  const exp = list.reduce((s, r) => s + num(r.expected_output), 0), good = list.reduce((s, r) => s + num(r.good_output), 0);
  const alerts = list.reduce((s, r) => s + (r.yield_alert ? 1 : 0) + r.usages.filter((u: any) => u.alert).length, 0);
  return (
    <>
      <PageHeader title="Production dashboard" description="Runs, yield, variance alerts and material availability." actions={<Link to="/production/new"><Button><Plus className="h-4 w-4" />New production run</Button></Link>} />
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Production runs" value={list.length} icon={<Factory className="h-4 w-4" />} /><Kpi label="Good packets produced" value={qty(good)} />
        <Kpi label="Overall yield" value={exp ? `${((good / exp) * 100).toFixed(1)}%` : "-"} /><Kpi label="Variance alerts" value={alerts} tone={alerts ? "alert" : "default"} icon={<AlertTriangle className="h-4 w-4" />} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Recent runs</h3>
          <DataTable loading={runs.isLoading} rows={list.slice(0, 6)} columns={[{ key: "run_number", header: "Run", render: (r: any) => <Link className="text-brand-700 hover:underline" to={`/production/${r.id}`}>{r.run_number}</Link> }, { key: "good_output", header: "Good", align: "right", render: (r: any) => qty(r.good_output) },
            { key: "yield_variance_pct", header: "Yield var.", align: "right", render: (r: any) => <Badge tone={r.yield_alert ? "red" : "green"}>{pct(r.yield_variance_pct)}</Badge> }]} /></Card>
        <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Production stock</h3>
          <DataTable loading={stock.isLoading} rows={stock.data?.items} rowKey={(r: any) => r.item_id} columns={[{ key: "name", header: "Item" }, { key: "quantity", header: "On hand", align: "right", render: (r: any) => `${qty(r.quantity)} ${r.unit}` }, { key: "s", header: "", render: (r: any) => r.low_stock && <Badge tone="red">Low</Badge> }]} /></Card>
      </div>
    </>
  );
}

export function ProductionRuns() {
  const nav = useNavigate();
  const { user } = useAuth();
  const q = useQuery(runsQ());
  return (
    <>
      <PageHeader title="Production history" description="Every completed run with yield and material variance." actions={["PRODUCTION", "ADMIN"].includes(user!.role) && <Link to="/production/new"><Button><Plus className="h-4 w-4" />New run</Button></Link>} />
      <Card><DataTable loading={q.isLoading} error={q.error} rows={q.data} onRowClick={(r: any) => nav(`/production/${r.id}`)}
        columns={[{ key: "run_number", header: "Run" }, { key: "run_date", header: "Date", render: (r: any) => fmtDate(r.run_date) }, { key: "product", header: "Product", render: (r: any) => r.product.name }, { key: "bom", header: "BOM", render: (r: any) => `v${r.bom_id}` },
          { key: "batches", header: "Batches", align: "right", render: (r: any) => qty(r.batches) }, { key: "expected_output", header: "Expected", align: "right", render: (r: any) => qty(r.expected_output) }, { key: "good_output", header: "Good", align: "right", render: (r: any) => qty(r.good_output) },
          { key: "yv", header: "Yield variance", align: "right", render: (r: any) => <Badge tone={r.yield_alert ? "red" : "green"}>{pct(r.yield_variance_pct)}</Badge> }]} /></Card>
    </>
  );
}

export function NewRun() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [productId, setProductId] = useState("");
  const [batches, setBatches] = useState("1");
  const [bomId, setBomId] = useState("");
  const [runDate, setRunDate] = useState(today());
  const [actual, setActual] = useState<Record<number, string>>({});
  const [out, setOut] = useState({ good_output: "", damaged_packets: "0", damaged_pouches: "0", scrap_qty: "0", material_wastage: "0", remarks: "" });
  const [key] = useState(newKey);
  const boms = useQuery({ queryKey: ["bom"], queryFn: async () => (await api.get("/bom")).data });
  const products = useMemo(() => { const m = new Map(); (boms.data || []).forEach((b: any) => m.set(b.product_id, b.product)); return [...m.values()]; }, [boms.data]);
  const versions = (boms.data || []).filter((b: any) => String(b.product_id) === productId && b.is_active);
  const plan = useQuery({ queryKey: ["plan", productId, bomId, batches], enabled: !!productId && num(batches) > 0, queryFn: async () => (await api.post("/production/plan", { product_id: Number(productId), bom_id: bomId ? Number(bomId) : null, batches })).data });
  const p = plan.data;
  const tol = num(p?.tolerance_pct ?? 3);
  const good = num(out.good_output);
  const actualFor = (l: any) => (l.is_primary_pack ? good + num(out.damaged_packets) + num(out.damaged_pouches) : actual[l.item_id] !== undefined && actual[l.item_id] !== "" ? num(actual[l.item_id]) : num(l.standard_qty));
  const yv = p && num(p.expected_output) ? ((good - num(p.expected_output)) / num(p.expected_output)) * 100 : 0;
  const shortage = p?.lines.filter((l: any) => actualFor(l) > num(l.available));

  const submit = useMutation({
    mutationFn: async () => (await api.post("/production/runs", { product_id: Number(productId), bom_id: p.bom_id, batches, run_date: runDate, ...out, idempotency_key: key,
      actual_usage: p.lines.filter((l: any) => !l.is_primary_pack).map((l: any) => ({ item_id: l.item_id, actual_quantity: String(actualFor(l)) })) })).data,
    onSuccess: (r) => { toast.success(`${r.run_number} completed — stock and costing updated`); ["runs", "inventory", "dashboard", "costing", "plan"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); nav(`/production/${r.id}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="New production run" description="Plan from the BOM, enter actuals, and post — all stock changes commit atomically or not at all." />
      <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-4">
        <Field label="Finished product"><select className="input" value={productId} onChange={(e) => { setProductId(e.target.value); setBomId(""); }}><option value="">Select…</option>{products.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="BOM version"><select className="input" value={bomId} onChange={(e) => setBomId(e.target.value)}><option value="">Latest active</option>{versions.map((b: any) => <option key={b.id} value={b.id}>v{b.version} (from {fmtDate(b.effective_date)})</option>)}</select></Field>
        <Field label="Number of batches"><input className="input" inputMode="decimal" value={batches} onChange={(e) => setBatches(e.target.value)} /></Field>
        <Field label="Run date"><input type="date" className="input" value={runDate} onChange={(e) => setRunDate(e.target.value)} /></Field>
      </Card>

      {plan.isLoading && <Skeleton className="h-48" />}
      {plan.isError && <p className="text-sm text-rose-600">{errorMessage(plan.error)}</p>}
      {p && (
        <>
          <Card className="mb-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3"><h3 className="text-sm font-semibold">Materials — BOM v{p.bom_version} · expected output {qty(p.expected_output)} packets</h3>
              {!p.can_produce && <Badge tone="red">Planned consumption exceeds stock</Badge>}</div>
            <DataTable rows={p.lines} rowKey={(l: any) => l.item_id} columns={[{ key: "item", header: "Item" },
              { key: "standard_qty", header: "Standard", align: "right", render: (l: any) => `${qty(l.standard_qty)} ${l.unit}` }, { key: "available", header: "Available", align: "right", render: (l: any) => `${qty(l.available)} ${l.unit}` },
              { key: "actual", header: "Actual consumption", render: (l: any) => l.is_primary_pack ? <span className="text-xs text-slate-500">auto = good + damaged ({qty(actualFor(l))})</span> :
                <input aria-label={`Actual ${l.item}`} className="input w-28" inputMode="decimal" placeholder={String(num(l.standard_qty))} value={actual[l.item_id] ?? ""} onChange={(e) => setActual({ ...actual, [l.item_id]: e.target.value })} /> },
              { key: "var", header: "Variance", align: "right", render: (l: any) => { const v = num(l.standard_qty) ? ((actualFor(l) - num(l.standard_qty)) / num(l.standard_qty)) * 100 : 0; return <Badge tone={Math.abs(v) > tol ? "red" : "green"}>{pct(v)}</Badge>; } },
              { key: "cost", header: "Est. cost @ avg", align: "right", render: (l: any) => money(actualFor(l) * num(l.avg_cost)) }]} />
          </Card>

          <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5">
            <Field label="Actual good output (packets)"><input className="input" inputMode="decimal" value={out.good_output} onChange={(e) => setOut({ ...out, good_output: e.target.value })} /></Field>
            <Field label="Damaged packets"><input className="input" inputMode="decimal" value={out.damaged_packets} onChange={(e) => setOut({ ...out, damaged_packets: e.target.value })} /></Field>
            <Field label="Damaged pouches"><input className="input" inputMode="decimal" value={out.damaged_pouches} onChange={(e) => setOut({ ...out, damaged_pouches: e.target.value })} /></Field>
            <Field label="Scrap (kg)"><input className="input" inputMode="decimal" value={out.scrap_qty} onChange={(e) => setOut({ ...out, scrap_qty: e.target.value })} /></Field>
            <Field label="Material wastage"><input className="input" inputMode="decimal" value={out.material_wastage} onChange={(e) => setOut({ ...out, material_wastage: e.target.value })} /></Field>
            <div className="sm:col-span-3 lg:col-span-5"><Field label="Remarks"><input className="input" value={out.remarks} onChange={(e) => setOut({ ...out, remarks: e.target.value })} /></Field></div>
          </Card>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">Yield variance: <Badge tone={Math.abs(yv) > tol ? "red" : "green"}>{pct(yv)}</Badge> <span className="text-xs text-slate-500">(tolerance ±{tol}%)</span></p>
            {shortage?.length > 0 && <p className="flex items-center gap-1 text-sm text-rose-600"><AlertTriangle className="h-4 w-4" />Insufficient stock for {shortage.map((l: any) => l.item).join(", ")} — posting will be rejected.</p>}
            <Button loading={submit.isPending} disabled={!out.good_output || shortage?.length > 0} onClick={() => submit.mutate()}>Complete & post run</Button>
          </div>
        </>
      )}
    </>
  );
}

export function RunDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [oh, setOh] = useState({ labour: "", gas_power: "", other: "0" });
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["run", id], queryFn: async () => (await api.get(`/production/runs/${id}`)).data });
  const save = useMutation({
    mutationFn: async () => (await api.post(`/production/runs/${id}/costs`, oh)).data,
    onSuccess: () => { toast.success("Overheads recorded; cost per packet recalculated"); setOpen(false); qc.invalidateQueries({ queryKey: ["run", id] }); qc.invalidateQueries({ queryKey: ["costing"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const r = q.data;
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (!r) return <p className="text-slate-500">Run not found.</p>;
  const c = r.cost;
  return (
    <>
      <Link to="/production" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft className="h-4 w-4" />Production history</Link>
      <PageHeader title={r.run_number} description={`${r.product.name} · ${fmtDate(r.run_date)} · BOM v${r.bom_id} · ${qty(r.batches)} batch(es)`} actions={["PRODUCTION", "ADMIN"].includes(user!.role) && <Button variant="secondary" onClick={() => { setOh({ labour: String(num(c.labour)), gas_power: String(num(c.gas_power)), other: String(num(c.other_overhead)) }); setOpen(true); }}>Record overheads</Button>} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Expected output" value={qty(r.expected_output)} /><Kpi label="Good output" value={qty(r.good_output)} /><Kpi label="Yield variance" value={pct(r.yield_variance_pct)} tone={r.yield_alert ? "alert" : "default"} hint={`Tolerance ±${num(r.tolerance_pct)}%`} />
        <Kpi label="Damaged packets / pouches" value={`${qty(r.damaged_packets)} / ${qty(r.damaged_pouches)}`} /><Kpi label="Scrap" value={qty(r.scrap_qty)} />
      </div>
      <Card className="mb-5"><h3 className="border-b px-4 py-3 text-sm font-semibold">Planned vs actual consumption</h3>
        <DataTable rows={r.usages} rowKey={(u: any) => u.item_id} columns={[{ key: "i", header: "Item", render: (u: any) => u.item.name }, { key: "standard_qty", header: "Standard", align: "right", render: (u: any) => `${qty(u.standard_qty)} ${u.unit}` },
          { key: "actual_qty", header: "Actual", align: "right", render: (u: any) => `${qty(u.actual_qty)} ${u.unit}` }, { key: "difference", header: "Difference", align: "right", render: (u: any) => qty(u.difference) },
          { key: "variance_pct", header: "Variance", align: "right", render: (u: any) => <Badge tone={u.alert ? "red" : "green"}>{pct(u.variance_pct)}{u.alert ? " · ALERT" : ""}</Badge> },
          { key: "unit_cost", header: "Avg rate", align: "right", render: (u: any) => money(u.unit_cost) }, { key: "cost", header: "Cost", align: "right", render: (u: any) => money(u.cost) }]} /></Card>
      <Card className="p-4"><h3 className="mb-3 text-sm font-semibold">Costing</h3>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          {[["Material + packaging", money(c.material_cost)], ["Labour", money(c.labour)], ["Gas & power", money(c.gas_power)], ["Other overhead", money(c.other_overhead)], ["Total cost", money(c.total_cost)], ["Cost per good packet", money(c.cost_per_packet)], ["Selling price", money(c.selling_price)], ["Gross profit / packet", `${money(c.gross_profit_per_packet)} (${num(c.gross_margin_pct).toFixed(2)}%)`]].map(([k, v]) => <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-semibold tabular-nums">{v}</dd></div>)}
        </dl></Card>
      <Modal open={open} title="Record overheads" onClose={() => setOpen(false)}>
        <div className="grid grid-cols-3 gap-3">{(["labour", "gas_power", "other"] as const).map((k) => <Field key={k} label={k === "gas_power" ? "Gas & power ₹" : k === "labour" ? "Labour ₹" : "Other ₹"}><input className="input" inputMode="decimal" value={(oh as any)[k]} onChange={(e) => setOh({ ...oh, [k]: e.target.value })} /></Field>)}</div>
        <p className="mt-3 text-xs text-slate-500">Values replace previous overheads for this run (old values are kept in the audit log).</p>
        <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></div>
      </Modal>
    </>
  );
}

export function BomPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [view, setView] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const q = useQuery({ queryKey: ["bom"], queryFn: async () => (await api.get("/bom")).data });
  const canWrite = ["PRODUCTION", "ADMIN"].includes(user!.role);
  const save = useMutation({
    mutationFn: async () => (await api.post("/bom", { product_id: draft.product_id, expected_output: draft.expected_output, batch_size: "1", effective_date: today(), notes: draft.notes,
      items: draft.items.map((i: any) => ({ item_id: i.item_id, quantity: i.quantity, unit: i.unit, is_primary_pack: i.is_primary_pack })) })).data,
    onSuccess: (b) => { toast.success(`BOM v${b.version} created. Existing runs keep their original version.`); setDraft(null); qc.invalidateQueries({ queryKey: ["bom"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <PageHeader title="Bills of materials" description="Versioned recipes. Changing a recipe creates a new version, so historical production records are never rewritten." />
      <Card><DataTable loading={q.isLoading} error={q.error} rows={q.data} onRowClick={setView}
        columns={[{ key: "p", header: "Product", render: (b: any) => b.product.name }, { key: "version", header: "Version", render: (b: any) => `v${b.version}` }, { key: "expected_output", header: "Output / batch", align: "right", render: (b: any) => qty(b.expected_output) },
          { key: "n", header: "Components", align: "right", render: (b: any) => b.items.length }, { key: "effective_date", header: "Effective", render: (b: any) => fmtDate(b.effective_date) }, { key: "a", header: "Status", render: (b: any) => <Badge tone={b.is_active ? "green" : "slate"}>{b.is_active ? "Active" : "Inactive"}</Badge> }]} /></Card>
      <Modal open={!!view} title={view ? `${view.product.name} — BOM v${view.version}` : ""} onClose={() => setView(null)}>
        {view && <>
          <p className="mb-3 text-sm text-slate-600">Expected output per batch: <b>{qty(view.expected_output)}</b> {view.product.unit}s</p>
          <DataTable rows={view.items} rowKey={(i: any) => i.item_id} columns={[{ key: "i", header: "Item", render: (i: any) => i.item.name }, { key: "quantity", header: "Standard qty", align: "right", render: (i: any) => `${qty(i.quantity)} ${i.unit}` }, { key: "t", header: "Type", render: (i: any) => i.item.item_type }]} />
          {canWrite && <div className="mt-4 flex justify-end"><Button variant="secondary" onClick={() => { setDraft({ product_id: view.product_id, expected_output: String(num(view.expected_output)), notes: `Revision of v${view.version}`, items: view.items.map((i: any) => ({ item_id: i.item_id, name: i.item.name, quantity: String(num(i.quantity)), unit: i.unit, is_primary_pack: i.is_primary_pack })) }); setView(null); }}><Copy className="h-4 w-4" />Create new version from this</Button></div>}
        </>}
      </Modal>
      <Modal open={!!draft} title="New BOM version" onClose={() => setDraft(null)}>
        {draft && <div className="space-y-3">
          <Field label="Expected output per batch"><input className="input" inputMode="decimal" value={draft.expected_output} onChange={(e) => setDraft({ ...draft, expected_output: e.target.value })} /></Field>
          {draft.items.map((i: any, idx: number) => <div key={i.item_id} className="grid grid-cols-[1fr_110px] items-end gap-2"><p className="pb-2 text-sm">{i.name} ({i.unit})</p><Field label="Quantity"><input className="input" inputMode="decimal" value={i.quantity} onChange={(e) => setDraft({ ...draft, items: draft.items.map((x: any, j: number) => (j === idx ? { ...x, quantity: e.target.value } : x)) })} /></Field></div>)}
          <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setDraft(null)}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Create version</Button></div>
        </div>}
      </Modal>
    </>
  );
}
