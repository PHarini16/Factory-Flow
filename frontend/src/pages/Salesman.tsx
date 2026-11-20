import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { CheckCircle2, ChevronLeft, Minus, Plus, Search } from "lucide-react";
import { api, errorMessage, money, newKey, num, qty } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Card, DataTable, EmptyState, Kpi, PageHeader, Skeleton, StatusBadge, cx, useToast } from "../components/ui";

export function SalesmanHome() {
  const { user } = useAuth();
  const orders = useQuery({ queryKey: ["orders"], queryFn: async () => (await api.get("/orders")).data });
  const list: any[] = orders.data || [];
  const today = new Date().toISOString().slice(0, 10);
  const todays = list.filter((o) => o.order_date === today);
  return (
    <>
      <PageHeader title={`Hello, ${user?.full_name.split(" - ")[1] || user?.full_name}`} description="Place an order in under a minute." />
      <Link to="/new-order"><Button className="mb-5 w-full py-4 text-base"><Plus className="h-5 w-5" />New order</Button></Link>
      <div className="mb-5 grid grid-cols-2 gap-3">
        <Kpi label="Orders today" value={todays.length} />
        <Kpi label="Pending approval" value={list.filter((o) => o.status === "SUBMITTED").length} />
      </div>
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Recent orders</h2>
      <OrderCards list={list.slice(0, 5)} loading={orders.isLoading} />
    </>
  );
}

export function OrderCards({ list, loading }: { list: any[]; loading?: boolean }) {
  if (loading) return <div className="space-y-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>;
  if (!list.length) return <Card><EmptyState title="No orders yet" text="Orders you submit appear here with live status." /></Card>;
  return (
    <div className="space-y-2">
      {list.map((o) => (
        <Link key={o.id} to={`/orders/${o.id}`} className="card block p-3.5 active:bg-slate-50">
          <div className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-900">{o.order_no}</span><StatusBadge status={o.status} /></div>
          <p className="mt-0.5 truncate text-sm text-slate-600">{o.customer.name}</p>
          <p className="mt-1 text-xs text-slate-500">{o.items.length} item(s) · est. {money(o.total_estimate)}</p>
        </Link>
      ))}
    </div>
  );
}

export function NewOrder() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState<"customer" | "products" | "review" | "done">("customer");
  const [customer, setCustomer] = useState<any>(null);
  const [cart, setCart] = useState<Record<number, number>>({});
  const [remarks, setRemarks] = useState("");
  const [search, setSearch] = useState("");
  const [placed, setPlaced] = useState<any>(null);
  const [key] = useState(newKey); // idempotency key: a double-tap can never create two orders
  const customers = useQuery({ queryKey: ["my-customers"], queryFn: async () => (await api.get("/customers")).data });
  const products = useQuery({ queryKey: ["products", "active"], queryFn: async () => (await api.get("/products", { params: { active: true } })).data });

  const lines = useMemo(() => (products.data || []).filter((p: any) => cart[p.id] > 0).map((p: any) => ({ p, q: cart[p.id], sub: num(p.selling_price) * cart[p.id], tax: (num(p.selling_price) * cart[p.id] * num(p.gst_rate)) / 100 })), [cart, products.data]);
  const subtotal = lines.reduce((s: number, l: any) => s + l.sub, 0);
  const tax = lines.reduce((s: number, l: any) => s + l.tax, 0);
  const setQ = (id: number, v: number) => setCart((c) => ({ ...c, [id]: Math.max(0, Math.floor(v || 0)) }));

  const submit = useMutation({
    mutationFn: async () => (await api.post("/orders", { customer_id: customer.id, remarks, idempotency_key: key, items: lines.map((l: any) => ({ product_id: l.p.id, quantity: String(l.q) })) })).data,
    onSuccess: (o) => { setPlaced(o); setStep("done"); qc.invalidateQueries({ queryKey: ["orders"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (step === "done") return (
    <div className="flex flex-col items-center py-10 text-center">
      <CheckCircle2 className="mb-3 h-16 w-16 text-emerald-500" />
      <h1 className="text-xl font-semibold">Order submitted</h1>
      <p className="mt-1 text-slate-600">{placed.order_no} · {placed.customer.name}</p>
      <p className="mt-1 text-sm text-slate-500">Status: <StatusBadge status={placed.status} /> — awaiting admin approval.</p>
      <div className="mt-6 flex w-full flex-col gap-2"><Button onClick={() => nav(`/orders/${placed.id}`)}>Track this order</Button><Button variant="secondary" onClick={() => nav("/")}>Back to home</Button></div>
    </div>
  );

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        {step !== "customer" && <button className="rounded p-1.5 hover:bg-slate-200" aria-label="Back" onClick={() => setStep(step === "review" ? "products" : "customer")}><ChevronLeft className="h-5 w-5" /></button>}
        <h1 className="text-xl font-semibold">{step === "customer" ? "Select customer" : step === "products" ? "Select products" : "Review order"}</h1>
      </div>

      {step === "customer" && (
        <div className="space-y-2">
          <div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" /><input className="input pl-9" placeholder="Search assigned customers" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
          {customers.isLoading && <Skeleton className="h-16" />}
          {(customers.data || []).filter((c: any) => c.name.toLowerCase().includes(search.toLowerCase())).map((c: any) => (
            <button key={c.id} onClick={() => { setCustomer(c); setStep("products"); }} className="card block w-full p-4 text-left active:bg-slate-50">
              <p className="font-medium text-slate-900">{c.name}</p><p className="text-sm text-slate-500">{c.city} · {c.state}</p>
            </button>
          ))}
          {customers.data?.length === 0 && <Card><EmptyState title="No customers assigned" text="Ask the administrator to assign customers to you." /></Card>}
        </div>
      )}

      {step === "products" && (
        <>
          <p className="mb-3 text-sm text-slate-600">Customer: <b>{customer.name}</b></p>
          <div className="space-y-2">
            {products.isLoading && <Skeleton className="h-20" />}
            {(products.data || []).map((p: any) => (
              <div key={p.id} className={cx("card flex items-center justify-between gap-3 p-3.5", cart[p.id] > 0 && "border-brand-600 ring-1 ring-brand-600")}>
                <div className="min-w-0"><p className="truncate font-medium text-slate-900">{p.name}</p><p className="text-sm text-slate-500">{money(p.selling_price)} · GST {num(p.gst_rate)}%</p></div>
                <div className="flex items-center gap-1.5">
                  <button aria-label={`Decrease ${p.name}`} className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-300 active:bg-slate-100" onClick={() => setQ(p.id, (cart[p.id] || 0) - 1)}><Minus className="h-4 w-4" /></button>
                  <input aria-label={`Quantity of ${p.name}`} inputMode="numeric" className="input w-16 text-center" value={cart[p.id] || ""} placeholder="0" onChange={(e) => setQ(p.id, Number(e.target.value.replace(/\D/g, "")))} />
                  <button aria-label={`Increase ${p.name}`} className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-300 active:bg-slate-100" onClick={() => setQ(p.id, (cart[p.id] || 0) + 1)}><Plus className="h-4 w-4" /></button>
                </div>
              </div>
            ))}
          </div>
          <div className="fixed inset-x-0 bottom-[60px] z-20 border-t bg-white p-3">
            <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
              <div><p className="text-xs text-slate-500">{lines.length} product(s)</p><p className="font-semibold">{money(subtotal)}</p></div>
              <Button disabled={!lines.length} onClick={() => setStep("review")}>Review order</Button>
            </div>
          </div>
        </>
      )}

      {step === "review" && (
        <div className="space-y-4">
          <Card className="p-4"><p className="text-xs text-slate-500">Customer</p><p className="font-medium">{customer.name}</p></Card>
          <Card className="divide-y">
            {lines.map((l: any) => <div key={l.p.id} className="flex justify-between p-3.5 text-sm"><span>{l.p.name} × {l.q}</span><span className="tabular-nums">{money(l.sub)}</span></div>)}
            <div className="flex justify-between p-3.5 text-sm text-slate-600"><span>Subtotal</span><span>{money(subtotal)}</span></div>
            <div className="flex justify-between p-3.5 text-sm text-slate-600"><span>GST estimate</span><span>{money(tax)}</span></div>
            <div className="flex justify-between p-3.5 font-semibold"><span>Estimated total</span><span>{money(subtotal + tax)}</span></div>
          </Card>
          <p className="text-xs text-slate-500">Prices come from the server price list. Final tax (CGST/SGST or IGST) is computed at invoicing.</p>
          <label className="block"><span className="label">Remarks (optional)</span><textarea className="input" rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></label>
          <Button className="w-full py-3.5" loading={submit.isPending} onClick={() => submit.mutate()}>Submit order</Button>
        </div>
      )}
    </>
  );
}

export function MySales() {
  const q = useQuery({ queryKey: ["my-sales"], queryFn: async () => (await api.get("/orders/my-customer-sales")).data });
  return (
    <>
      <PageHeader title="Customer-wise sales" description="Value of your submitted, approved and invoiced orders (excluding rejected/cancelled)." />
      <Card><DataTable loading={q.isLoading} error={q.error} rows={q.data} rowKey={(r: any) => r.customer}
        columns={[{ key: "customer", header: "Customer" }, { key: "orders", header: "Orders", align: "right" }, { key: "value", header: "Value", align: "right", render: (r: any) => money(r.value) }]} /></Card>
    </>
  );
}
