import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { api, errorMessage, fmtDate, money, newKey, qty, today } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Card, DataTable, Modal, PageHeader, StatusBadge, useToast } from "../components/ui";

export default function Purchases() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const canWrite = ["ADMIN", "PRODUCTION"].includes(user!.role);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ supplier_id: "", supplier_invoice_no: "", purchase_date: today() });
  const [lines, setLines] = useState([{ item_id: "", quantity: "", rate: "" }]);
  const [key, setKey] = useState(newKey);
  const list = useQuery({ queryKey: ["purchases"], queryFn: async () => (await api.get("/purchases")).data });
  const suppliers = useQuery({ queryKey: ["/suppliers"], enabled: canWrite, queryFn: async () => (await api.get("/suppliers")).data });
  const items = useQuery({ queryKey: ["items", "mat"], enabled: canWrite, queryFn: async () => ((await api.get("/inventory/items")).data as any[]).filter((i) => i.item_type !== "FINISHED") });

  const save = useMutation({
    mutationFn: async () => (await api.post("/purchases", { ...f, supplier_id: Number(f.supplier_id), receive: true, idempotency_key: key,
      items: lines.map((l) => ({ item_id: Number(l.item_id), quantity: l.quantity, rate: l.rate })) })).data,
    onSuccess: (p) => { toast.success(`${p.po_number} received — stock ledger updated`); setOpen(false); setKey(newKey()); setLines([{ item_id: "", quantity: "", rate: "" }]); setF({ ...f, supplier_invoice_no: "" });
      ["purchases", "inventory", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const rows = (list.data || []).flatMap((p: any) => p.items.map((it: any, i: number) => ({ ...p, it, rid: `${p.id}-${i}` })));
  const total = lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.rate || 0), 0);
  const unitOf = (id: string) => (items.data || []).find((i: any) => String(i.id) === id)?.unit || "";

  return (
    <>
      <PageHeader title="Purchases" description="Purchase register. Receiving a purchase posts ledger entries and updates weighted-average cost." actions={canWrite && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Record purchase</Button>} />
      <Card><DataTable loading={list.isLoading} error={list.error} rows={rows} rowKey={(r: any) => r.rid}
        columns={[{ key: "po_number", header: "PO" }, { key: "purchase_date", header: "Date", render: (r: any) => fmtDate(r.purchase_date) }, { key: "s", header: "Supplier", render: (r: any) => r.supplier.name }, { key: "supplier_invoice_no", header: "Supplier invoice" },
          { key: "item", header: "Item", render: (r: any) => r.it.item.name }, { key: "q", header: "Qty", align: "right", render: (r: any) => `${qty(r.it.quantity)} ${r.it.unit}` }, { key: "rate", header: "Rate", align: "right", render: (r: any) => money(r.it.rate) },
          { key: "amount", header: "Amount", align: "right", render: (r: any) => money(r.it.amount) }, { key: "status", header: "Status", render: (r: any) => <StatusBadge status={r.status} /> }]} /></Card>

      <Modal open={open} title="Record purchase receipt" onClose={() => setOpen(false)} wide>
        <div className="grid gap-3 sm:grid-cols-3">
          <label><span className="label">Supplier</span><select className="input" value={f.supplier_id} onChange={(e) => setF({ ...f, supplier_id: e.target.value })}><option value="">Select…</option>{(suppliers.data || []).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label><span className="label">Supplier invoice no.</span><input className="input" value={f.supplier_invoice_no} onChange={(e) => setF({ ...f, supplier_invoice_no: e.target.value })} /></label>
          <label><span className="label">Date</span><input type="date" className="input" value={f.purchase_date} onChange={(e) => setF({ ...f, purchase_date: e.target.value })} /></label>
        </div>
        <div className="mt-4 space-y-2">
          {lines.map((l, i) => (
            <div key={i} className="grid grid-cols-[1fr_90px_90px_40px] items-end gap-2">
              <label><span className="label">Item</span><select className="input" value={l.item_id} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, item_id: e.target.value } : x)))}><option value="">Select…</option>{(items.data || []).map((it: any) => <option key={it.id} value={it.id}>{it.name} ({it.unit})</option>)}</select></label>
              <label><span className="label">Qty {unitOf(l.item_id)}</span><input className="input" inputMode="decimal" value={l.quantity} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} /></label>
              <label><span className="label">Rate ₹</span><input className="input" inputMode="decimal" value={l.rate} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, rate: e.target.value } : x)))} /></label>
              <button aria-label="Remove line" className="mb-1 rounded p-2 text-slate-400 hover:bg-slate-100 hover:text-rose-600 disabled:opacity-30" disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
          <Button variant="ghost" onClick={() => setLines([...lines, { item_id: "", quantity: "", rate: "" }])}><Plus className="h-4 w-4" />Add line</Button>
        </div>
        <div className="mt-4 flex items-center justify-between border-t pt-4"><p className="text-sm">Total: <b>{money(total)}</b></p>
          <div className="flex gap-2"><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={save.isPending} disabled={!f.supplier_id || !f.supplier_invoice_no || lines.some((l) => !l.item_id || !l.quantity || l.rate === "")} onClick={() => save.mutate()}>Receive goods</Button></div></div>
      </Modal>
    </>
  );
}
