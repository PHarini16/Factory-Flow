import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Boxes, ClipboardList, Factory, IndianRupee, PackageCheck, Percent, TrendingUp, Wallet } from "lucide-react";
import { api, fmtDate, money, num, pct, qty } from "../lib/api";
import { Badge, Card, DataTable, ErrorState, Kpi, PageHeader, Skeleton, StatusBadge } from "../components/ui";
import { useAuth } from "../lib/auth";

const COLORS = ["#0f766e", "#0ea5e9", "#f59e0b", "#6366f1", "#e11d48", "#64748b"];
const iso = (d: Date) => d.toISOString().slice(0, 10);

function ChartCard({ title, children, empty }: { title: string; children: React.ReactNode; empty?: boolean }) {
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">{title}</h3>
      <div className="h-60">{empty ? <p className="flex h-full items-center justify-center text-sm text-slate-400">No data in this period</p> : <ResponsiveContainer width="100%" height="100%">{children as any}</ResponsiveContainer>}</div>
    </Card>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const now = new Date();
  const [from, setFrom] = useState(iso(new Date(now.getFullYear(), now.getMonth(), 1)));
  const [to, setTo] = useState(iso(now));
  const q = useQuery({ queryKey: ["dashboard", from, to], queryFn: async () => (await api.get("/dashboard", { params: { date_from: from, date_to: to } })).data });
  const d = q.data;
  const k = d?.kpis;
  const title = user?.role === "ACCOUNTANT" ? "Financial dashboard" : user?.role === "ADMIN" ? "Admin dashboard" : "Owner dashboard";

  return (
    <>
      <PageHeader title={title} description="Live figures computed from orders, invoices, stock ledger and production records."
        actions={<div className="flex items-end gap-2">
          <label><span className="label">From</span><input type="date" className="input" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></label>
          <label><span className="label">To</span><input type="date" className="input" value={to} min={from} onChange={(e) => setTo(e.target.value)} /></label>
        </div>} />
      {q.isError ? <ErrorState error={q.error} retry={() => q.refetch()} /> : !d ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Kpi label="Today's orders" value={k.todays_orders} icon={<ClipboardList className="h-4 w-4" />} />
            <Kpi label="Today's sales" value={money(k.todays_sales)} icon={<IndianRupee className="h-4 w-4" />} />
            <Kpi label="Revenue (selected period)" value={money(k.monthly_revenue)} icon={<TrendingUp className="h-4 w-4" />} />
            <Kpi label="Total outstanding" value={money(k.total_outstanding)} icon={<Wallet className="h-4 w-4" />} />
            <Kpi label="Raw & packaging stock value" value={money(k.raw_material_stock_value)} icon={<Boxes className="h-4 w-4" />} />
            <Kpi label="Finished goods (packets)" value={qty(k.finished_goods_stock)} icon={<PackageCheck className="h-4 w-4" />} />
            <Kpi label="Production batches" value={qty(k.production_batches)} icon={<Factory className="h-4 w-4" />} />
            <Kpi label="Production yield" value={`${num(k.production_yield_pct).toFixed(1)}%`} icon={<Percent className="h-4 w-4" />} />
            <Kpi label="Low-stock alerts" value={k.low_stock_count} tone={k.low_stock_count ? "alert" : "default"} icon={<AlertTriangle className="h-4 w-4" />} />
            <Kpi label="Variance alerts" value={k.variance_alert_count} tone={k.variance_alert_count ? "alert" : "default"} icon={<AlertTriangle className="h-4 w-4" />} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Monthly sales trend (invoice value)">
              <LineChart data={d.charts.sales_trend.map((r: any) => ({ ...r, sales: num(r.sales) }))}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="month" fontSize={12} /><YAxis fontSize={12} /><Tooltip formatter={(v: any) => money(v)} /><Line dataKey="sales" stroke="#0f766e" strokeWidth={2} dot /></LineChart>
            </ChartCard>
            <ChartCard title="Product-wise sales (taxable, selected period)" empty={!d.charts.product_sales.length}>
              <BarChart data={d.charts.product_sales.map((r: any) => ({ ...r, sales: num(r.sales) }))}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="product" fontSize={12} /><YAxis fontSize={12} /><Tooltip formatter={(v: any) => money(v)} /><Bar dataKey="sales" fill="#0ea5e9" radius={[4, 4, 0, 0]} /></BarChart>
            </ChartCard>
            <ChartCard title="Production vs sales dispatch (packets)">
              <BarChart data={d.charts.production_vs_sales.map((r: any) => ({ month: r.month, produced: num(r.produced), dispatched: num(r.dispatched) }))}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="month" fontSize={12} /><YAxis fontSize={12} /><Tooltip /><Legend /><Bar dataKey="produced" fill="#0f766e" radius={[4, 4, 0, 0]} /><Bar dataKey="dispatched" fill="#f59e0b" radius={[4, 4, 0, 0]} /></BarChart>
            </ChartCard>
            <ChartCard title="Inventory value distribution" empty={!d.charts.inventory_distribution.length}>
              <PieChart><Pie data={d.charts.inventory_distribution.map((r: any) => ({ name: r.type, value: num(r.value) }))} dataKey="value" nameKey="name" outerRadius={85} label>{d.charts.inventory_distribution.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip formatter={(v: any) => money(v)} /><Legend /></PieChart>
            </ChartCard>
            <ChartCard title="Collection trend">
              <LineChart data={d.charts.collection_trend.map((r: any) => ({ ...r, collected: num(r.collected) }))}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="month" fontSize={12} /><YAxis fontSize={12} /><Tooltip formatter={(v: any) => money(v)} /><Line dataKey="collected" stroke="#6366f1" strokeWidth={2} dot /></LineChart>
            </ChartCard>
            <ChartCard title="Production wastage by run" empty={!d.charts.wastage.length}>
              <BarChart data={d.charts.wastage.map((r: any) => ({ run: r.run, "Damaged packets": num(r.damaged_packets), "Damaged pouches": num(r.damaged_pouches), Scrap: num(r.scrap) }))}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="run" fontSize={11} /><YAxis fontSize={12} /><Tooltip /><Legend /><Bar dataKey="Damaged packets" stackId="a" fill="#e11d48" /><Bar dataKey="Damaged pouches" stackId="a" fill="#f59e0b" /><Bar dataKey="Scrap" stackId="a" fill="#64748b" /></BarChart>
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Pending approvals</h3>
              <DataTable rows={d.pending_approvals} columns={[{ key: "order_no", header: "Order", render: (r: any) => <Link className="text-brand-700 hover:underline" to={`/orders/${r.id}`}>{r.order_no}</Link> }, { key: "customer", header: "Customer" }, { key: "total_estimate", header: "Est. total", align: "right", render: (r: any) => money(r.total) }]} empty={<p className="p-6 text-center text-sm text-slate-500">No orders waiting for approval.</p>} /></Card>
            <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Critical production alerts</h3>
              <DataTable rows={d.alerts} columns={[{ key: "run", header: "Run" }, { key: "item", header: "Item" }, { key: "variance_pct", header: "Variance", align: "right", render: (r: any) => <Badge tone="red">{pct(r.variance_pct)}</Badge> }]} empty={<p className="p-6 text-center text-sm text-slate-500">No variance beyond tolerance in this period.</p>} /></Card>
            <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Low-stock materials</h3>
              <DataTable rows={d.low_stock} columns={[{ key: "name", header: "Item" }, { key: "quantity", header: "On hand", align: "right", render: (r: any) => `${qty(r.quantity)} ${r.unit}` }, { key: "reorder_level", header: "Reorder at", align: "right", render: (r: any) => qty(r.reorder_level) }]} rowKey={(r: any) => r.item_id} empty={<p className="p-6 text-center text-sm text-slate-500">All items above reorder level.</p>} /></Card>
            <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Outstanding customer balances</h3>
              <DataTable rows={d.outstanding_customers} columns={[{ key: "customer", header: "Customer" }, { key: "outstanding", header: "Outstanding", align: "right", render: (r: any) => money(r.outstanding) }]} rowKey={(r: any) => r.customer} empty={<p className="p-6 text-center text-sm text-slate-500">No outstanding balances.</p>} /></Card>
            <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Recent orders</h3>
              <DataTable rows={d.recent_orders} columns={[{ key: "order_no", header: "Order", render: (r: any) => <Link className="text-brand-700 hover:underline" to={`/orders/${r.id}`}>{r.order_no}</Link> }, { key: "customer", header: "Customer" }, { key: "status", header: "Status", render: (r: any) => <StatusBadge status={r.status} /> }, { key: "total", header: "Total", align: "right", render: (r: any) => money(r.total) }]} empty={<p className="p-6 text-center text-sm text-slate-500">No orders yet.</p>} /></Card>
            <Card><h3 className="border-b px-4 py-3 text-sm font-semibold">Recent production runs</h3>
              <DataTable rows={d.recent_runs} columns={[{ key: "run_number", header: "Run", render: (r: any) => <Link className="text-brand-700 hover:underline" to={`/production/${r.id}`}>{r.run_number}</Link> }, { key: "product", header: "Product" }, { key: "good_output", header: "Good", align: "right", render: (r: any) => qty(r.good_output) }, { key: "yield_variance_pct", header: "Yield var.", align: "right", render: (r: any) => pct(r.yield_variance_pct) }]} empty={<p className="p-6 text-center text-sm text-slate-500">No production runs yet.</p>} /></Card>
          </div>
        </div>
      )}
    </>
  );
}
