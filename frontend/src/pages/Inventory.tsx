import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { api, download, errorMessage, fmtDate, money, qty, today } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, DataTable, Field, Modal, PageHeader, Tabs, useToast } from "../components/ui";

export default function Inventory() {
  const { user } = useAuth();
  const [tab, setTab] = useState("summary");
  return (
    <>
      <PageHeader title="Inventory & stock ledger" description="Stock is reconstructed from an immutable ledger — balances can never be overwritten directly." />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "summary", label: "Stock summary" }, { id: "ledger", label: "Stock ledger" }]} />
      {tab === "summary" ? <Summary canAdjust={user?.role === "ADMIN"} /> : <Ledger />}
    </>
  );
}

function Summary({ canAdjust }: { canAdjust: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [type, setType] = useState("");
  const [adj, setAdj] = useState<any>(null);
  const [f, setF] = useState({ direction: "OUT", quantity: "", reason: "" });
  const q = useQuery({ queryKey: ["inventory", type], queryFn: async () => (await api.get("/inventory/summary", { params: { item_type: type || undefined } })).data });
  const save = useMutation({
    mutationFn: async () => (await api.post("/inventory/adjustments", { item_id: adj.item_id, ...f, txn_date: today() })).data,
    onSuccess: () => { toast.success("Adjustment posted to ledger"); setAdj(null); setF({ direction: "OUT", quantity: "", reason: "" }); qc.invalidateQueries({ queryKey: ["inventory"] }); qc.invalidateQueries({ queryKey: ["ledger"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <select className="input max-w-[200px]" value={type} onChange={(e) => setType(e.target.value)} aria-label="Item type"><option value="">All items</option><option value="RAW">Raw materials</option><option value="PACKAGING">Packaging</option><option value="FINISHED">Finished goods</option></select>
        <div className="flex items-center gap-3"><p className="text-sm text-slate-600">Total value: <b>{money(q.data?.total_value)}</b></p>
          <Button variant="secondary" onClick={() => download("/reports/stock-summary", { format: "xlsx" })}>Excel</Button><Button variant="secondary" onClick={() => download("/reports/stock-summary", { format: "csv" })}>CSV</Button></div>
      </div>
      <Card><DataTable loading={q.isLoading} error={q.error} rows={q.data?.items} rowKey={(r: any) => r.item_id}
        columns={[{ key: "sku", header: "SKU" }, { key: "name", header: "Item" }, { key: "item_type", header: "Type", render: (r: any) => <Badge tone="slate">{r.item_type}</Badge> },
          { key: "quantity", header: "On hand", align: "right", render: (r: any) => `${qty(r.quantity)} ${r.unit}` }, { key: "avg_cost", header: "Avg rate", align: "right", render: (r: any) => money(r.avg_cost) },
          { key: "value", header: "Value", align: "right", render: (r: any) => money(r.value) }, { key: "reorder_level", header: "Reorder", align: "right", render: (r: any) => qty(r.reorder_level) },
          { key: "low", header: "Status", render: (r: any) => r.low_stock ? <Badge tone="red">Low stock</Badge> : <Badge tone="green">OK</Badge> },
          ...(canAdjust ? [{ key: "a", header: "", render: (r: any) => <button aria-label="Adjust stock" className="rounded p-1.5 text-slate-500 hover:bg-slate-100" onClick={() => setAdj(r)}><SlidersHorizontal className="h-4 w-4" /></button> }] : [])]} /></Card>
      <Modal open={!!adj} title={`Stock adjustment — ${adj?.name}`} onClose={() => setAdj(null)}>
        <p className="mb-3 text-sm text-slate-500">Adjustments create a STOCK_ADJUSTMENT ledger entry with a mandatory reason; negative stock is rejected.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Direction"><select className="input" value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}><option value="OUT">Reduce (OUT)</option><option value="IN">Increase (IN)</option></select></Field>
          <Field label={`Quantity (${adj?.unit})`}><input className="input" inputMode="decimal" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></Field>
          <div className="col-span-2"><Field label="Reason"><input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field></div>
        </div>
        <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={() => setAdj(null)}>Cancel</Button><Button loading={save.isPending} disabled={!f.quantity || f.reason.length < 3} onClick={() => save.mutate()}>Post adjustment</Button></div>
      </Modal>
    </>
  );
}

function Ledger() {
  const [itemId, setItemId] = useState("");
  const [type, setType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const items = useQuery({ queryKey: ["items", "all"], queryFn: async () => (await api.get("/inventory/items")).data });
  const params = { item_id: itemId || undefined, movement_type: type || undefined, date_from: from || undefined, date_to: to || undefined };
  const led = useQuery({ queryKey: ["ledger", params], queryFn: async () => (await api.get("/stock-ledger", { params })).data });
  const sum = useQuery({ queryKey: ["ledger-summary", itemId, from, to], enabled: !!itemId, queryFn: async () => (await api.get(`/stock-ledger/summary/${itemId}`, { params: { date_from: from || undefined, date_to: to || undefined } })).data });
  const types = ["OPENING", "PURCHASE_RECEIPT", "PRODUCTION_ISSUE", "PRODUCTION_OUTPUT", "PACKAGING_CONSUMPTION", "SALES_DISPATCH", "SALES_RETURN", "PURCHASE_RETURN", "STOCK_ADJUSTMENT"];
  return (
    <>
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <select className="input" value={itemId} onChange={(e) => setItemId(e.target.value)} aria-label="Item"><option value="">All items</option>{(items.data || []).map((i: any) => <option key={i.id} value={i.id}>{i.name}</option>)}</select>
        <select className="input" value={type} onChange={(e) => setType(e.target.value)} aria-label="Movement type"><option value="">All movement types</option>{types.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select>
        <input type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From date" /><input type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date" />
        <div className="flex gap-2"><Button variant="secondary" onClick={() => download("/reports/stock-ledger", { ...params, format: "xlsx" })}>Excel</Button><Button variant="secondary" onClick={() => download("/reports/stock-ledger", { ...params, format: "csv" })}>CSV</Button></div>
      </div>
      {sum.data && (
        <Card className="mb-4 grid grid-cols-2 gap-3 p-4 sm:grid-cols-5">
          {[["Opening", sum.data.opening], ["Receipts", sum.data.receipts], ["Issues", sum.data.issues], ["Adjustments", sum.data.adjustments], ["Closing", sum.data.closing]].map(([l, v]) => <div key={l as string}><p className="text-xs text-slate-500">{l}</p><p className="font-semibold tabular-nums">{qty(v)} {sum.data.unit}</p></div>)}
        </Card>
      )}
      <Card><DataTable loading={led.isLoading} error={led.error} rows={led.data?.rows}
        columns={[{ key: "id", header: "#" }, { key: "date", header: "Date", render: (r: any) => fmtDate(r.date) }, { key: "item", header: "Item" }, { key: "type", header: "Movement", render: (r: any) => <Badge tone={r.direction === "IN" ? "green" : "amber"}>{r.type.replace(/_/g, " ")}</Badge> },
          { key: "quantity", header: "Qty", align: "right", render: (r: any) => `${r.direction === "IN" ? "+" : "−"}${qty(r.quantity)} ${r.unit}` }, { key: "value", header: "Value", align: "right", render: (r: any) => money(r.value) },
          { key: "source", header: "Source doc" }, { key: "user", header: "User" }, { key: "remarks", header: "Remarks" }]} /></Card>
    </>
  );
}
