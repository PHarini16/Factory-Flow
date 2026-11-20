import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, fmtDate, money, num, pct, qty } from "../lib/api";
import { Card, DataTable, PageHeader } from "../components/ui";

export default function Costing() {
  const runs = useQuery({ queryKey: ["costing"], queryFn: async () => (await api.get("/costing/runs")).data });
  const wa = useQuery({ queryKey: ["wavg"], queryFn: async () => (await api.get("/costing/weighted-average")).data });
  return (
    <>
      <PageHeader title="Product costing" description="Weighted-average material cost + allocated overhead, divided by good packets." />
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Production cost per run</h2>
      <Card className="mb-6"><DataTable loading={runs.isLoading} error={runs.error} rows={runs.data?.rows} rowKey={(r: any) => r.run}
        columns={[{ key: "run", header: "Run" }, { key: "date", header: "Date", render: (r: any) => fmtDate(r.date) }, { key: "product", header: "Product" }, { key: "good", header: "Good pkts", align: "right", render: (r: any) => qty(r.good) },
          { key: "material", header: "Material + pack", align: "right", render: (r: any) => money(r.material) }, { key: "overhead", header: "Overhead", align: "right", render: (r: any) => money(num(r.labour) + num(r.gas_power) + num(r.other)) },
          { key: "total", header: "Total cost", align: "right", render: (r: any) => money(r.total) }, { key: "cost_per_packet", header: "Cost / packet", align: "right", render: (r: any) => <b>{money(r.cost_per_packet)}</b> },
          { key: "selling_price", header: "Selling price", align: "right", render: (r: any) => money(r.selling_price) }, { key: "gp", header: "GP / packet", align: "right", render: (r: any) => money(r.gp_per_packet) }, { key: "margin_pct", header: "Margin", align: "right", render: (r: any) => `${num(r.margin_pct).toFixed(2)}%` }]} /></Card>
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Current weighted-average rates</h2>
      <Card><DataTable loading={wa.isLoading} rows={wa.data} rowKey={(r: any) => r.item}
        columns={[{ key: "item", header: "Item" }, { key: "quantity", header: "On hand", align: "right", render: (r: any) => `${qty(r.quantity)} ${r.unit}` }, { key: "avg_cost", header: "Avg rate", align: "right", render: (r: any) => `${money(r.avg_cost)} / ${r.unit}` }, { key: "value", header: "Value", align: "right", render: (r: any) => money(r.value) }]} /></Card>
      <p className="mt-3 text-xs text-slate-500">New average = (existing value + purchase value) ÷ (existing qty + purchased qty). Issues are costed at the average at the time of consumption.</p>
    </>
  );
}
