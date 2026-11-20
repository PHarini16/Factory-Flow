import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api, errorMessage, money, num } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, Column, DataTable, Field, Modal, PageHeader, useToast } from "../components/ui";

interface FieldDef { name: string; label: string; type?: "text" | "number" | "select" | "checkbox"; options?: { value: string; label: string }[]; required?: boolean; readOnlyOnEdit?: boolean }

function CrudPage({ title, description, path, columns, fields, schema, defaults, method, canEdit, mapIn, extra }: {
  title: string; description: string; path: string; columns: Column<any>[]; fields: FieldDef[]; schema: z.ZodTypeAny; defaults: any; method: "put" | "patch"; canEdit: boolean;
  mapIn?: (v: any) => any; extra?: Record<string, any>;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<any | null>(null);
  const [open, setOpen] = useState(false);
  const list = useQuery({ queryKey: [path], queryFn: async () => (await api.get(path)).data });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<any>({ resolver: zodResolver(schema) as any, defaultValues: defaults });

  const save = useMutation({
    mutationFn: async (v: any) => { const body = mapIn ? mapIn(v) : v; return editing ? (await api[method](`${path}/${editing.id}`, body)).data : (await api.post(path, body)).data; },
    onSuccess: () => { toast.success(editing ? "Saved" : "Created"); setOpen(false); qc.invalidateQueries({ queryKey: [path] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const openNew = () => { setEditing(null); reset(defaults); setOpen(true); };
  const openEdit = (r: any) => { if (!canEdit) return; setEditing(r); reset({ ...defaults, ...Object.fromEntries(Object.entries(r).map(([k, v]) => [k, v === null ? "" : typeof v === "boolean" ? v : String(v)])) }); setOpen(true); };
  const rows = (list.data || []).filter((r: any) => !search || JSON.stringify(r).toLowerCase().includes(search.toLowerCase()));

  return (
    <>
      <PageHeader title={title} description={description} actions={canEdit && <Button onClick={openNew}><Plus className="h-4 w-4" />Add</Button>} />
      <input className="input mb-4 max-w-xs" placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} />
      <Card><DataTable loading={list.isLoading} error={list.error} rows={rows} columns={columns} onRowClick={canEdit ? openEdit : undefined} /></Card>
      <Modal open={open} title={editing ? `Edit ${title.replace(/s$/, "")}` : `Add ${title.replace(/s$/, "")}`} onClose={() => setOpen(false)} wide>
        <form onSubmit={handleSubmit((v) => save.mutate(v))} className="grid gap-3 sm:grid-cols-2" noValidate>
          {fields.map((f) => (
            <div key={f.name} className={f.type === "checkbox" ? "flex items-end pb-2" : ""}>
              {f.type === "checkbox" ? <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" {...register(f.name)} />{f.label}</label> : (
                <Field label={f.label} error={(errors as any)[f.name]?.message as string}>
                  {f.type === "select" ? <select className="input" {...register(f.name)}>{(f.name === "salesman_id" ? extra?.salesmen : f.options)?.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                    : <input className="input" inputMode={f.type === "number" ? "decimal" : undefined} disabled={!!editing && f.readOnlyOnEdit} {...register(f.name)} />}
                </Field>)}
            </div>
          ))}
          <div className="col-span-full mt-2 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" loading={save.isPending}>Save</Button></div>
        </form>
      </Modal>
    </>
  );
}

const numStr = (label: string, min = 0) => z.string().min(1, `${label} is required`).refine((v) => !isNaN(Number(v)) && Number(v) >= min, `${label} must be a number ≥ ${min}`);
const active = (r: any) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge>;

export function Products() {
  const { user } = useAuth();
  const schema = z.object({ name: z.string().min(2, "Name is required"), category: z.string().optional(), sku: z.string().min(2, "SKU is required"), pack_size: z.string().optional(), unit: z.string().optional(),
    hsn_code: z.string().min(4, "HSN code needs 4+ digits"), gst_rate: numStr("GST rate"), selling_price: numStr("Selling price"), reorder_level: numStr("Reorder level"), is_active: z.boolean().optional() });
  return <CrudPage title="Products" description="Finished goods, selling prices and GST rates." path="/products" method="patch" canEdit={user?.role === "ADMIN"} schema={schema}
    defaults={{ name: "", category: "", sku: "", pack_size: "", unit: "packet", hsn_code: "1905", gst_rate: "5", selling_price: "", reorder_level: "0", is_active: true }}
    fields={[{ name: "name", label: "Product name" }, { name: "sku", label: "SKU", readOnlyOnEdit: true }, { name: "category", label: "Category" }, { name: "pack_size", label: "Pack size" }, { name: "hsn_code", label: "HSN code" },
      { name: "gst_rate", label: "GST rate %", type: "number" }, { name: "selling_price", label: "Selling price (₹, before tax)", type: "number" }, { name: "reorder_level", label: "Reorder level", type: "number" }, { name: "is_active", label: "Active", type: "checkbox" }]}
    columns={[{ key: "sku", header: "SKU" }, { key: "name", header: "Product" }, { key: "category", header: "Category" }, { key: "pack_size", header: "Pack" }, { key: "hsn_code", header: "HSN" },
      { key: "gst_rate", header: "GST", align: "right", render: (r) => `${num(r.gst_rate)}%` }, { key: "selling_price", header: "Price", align: "right", render: (r) => money(r.selling_price) }, { key: "is_active", header: "Status", render: active }]} />;
}

export function Customers() {
  const { user } = useAuth();
  const users = useQuery({ queryKey: ["salesmen"], enabled: ["ADMIN", "OWNER"].includes(user!.role), queryFn: async () => (await api.get("/users", { params: { role: "SALESMAN" } })).data });
  const salesmen = [{ value: "", label: "— Unassigned —" }, ...(users.data || []).map((u: any) => ({ value: String(u.id), label: u.full_name }))];
  const schema = z.object({ name: z.string().min(2, "Name is required"), customer_type: z.string(), gstin: z.string().max(15, "GSTIN is 15 characters").optional(), billing_address: z.string().optional(), shipping_address: z.string().optional(),
    city: z.string().optional(), state: z.string().min(2, "State is required"), state_code: z.string().length(2, "2-digit state code, e.g. 33"), phone: z.string().optional(), email: z.string().optional(),
    salesman_id: z.string().optional(), credit_limit: numStr("Credit limit"), payment_terms_days: numStr("Payment terms"), is_active: z.boolean().optional() });
  return <CrudPage title="Customers" description="Retailers and distributors. State code decides CGST/SGST vs IGST (factory: Tamil Nadu, 33)." path="/customers" method="put" canEdit={user?.role === "ADMIN"} schema={schema} extra={{ salesmen }}
    mapIn={(v) => ({ ...v, gstin: v.gstin || null, phone: v.phone || null, email: v.email || null, salesman_id: v.salesman_id ? Number(v.salesman_id) : null, payment_terms_days: Number(v.payment_terms_days) })}
    defaults={{ name: "", customer_type: "RETAILER", gstin: "", billing_address: "", shipping_address: "", city: "", state: "Tamil Nadu", state_code: "33", phone: "", email: "", salesman_id: "", credit_limit: "0", payment_terms_days: "30", is_active: true }}
    fields={[{ name: "name", label: "Name" }, { name: "customer_type", label: "Type", type: "select", options: [{ value: "RETAILER", label: "Retailer" }, { value: "DISTRIBUTOR", label: "Distributor" }] }, { name: "gstin", label: "GSTIN (optional)" },
      { name: "billing_address", label: "Billing address" }, { name: "shipping_address", label: "Shipping address" }, { name: "city", label: "City" }, { name: "state", label: "State" }, { name: "state_code", label: "State code" },
      { name: "phone", label: "Phone" }, { name: "email", label: "Email" }, { name: "salesman_id", label: "Assigned salesman", type: "select" }, { name: "credit_limit", label: "Credit limit (₹)", type: "number" },
      { name: "payment_terms_days", label: "Payment terms (days)", type: "number" }, { name: "is_active", label: "Active", type: "checkbox" }]}
    columns={[{ key: "name", header: "Customer" }, { key: "customer_type", header: "Type", render: (r) => <Badge tone="teal">{r.customer_type}</Badge> }, { key: "city", header: "City" }, { key: "state", header: "State", render: (r) => `${r.state} (${r.state_code})` },
      { key: "gstin", header: "GSTIN", render: (r) => r.gstin || "-" }, { key: "credit_limit", header: "Credit limit", align: "right", render: (r) => money(r.credit_limit) }, { key: "is_active", header: "Status", render: active }]} />;
}

export function Suppliers() {
  const { user } = useAuth();
  const schema = z.object({ name: z.string().min(2, "Name is required"), contact: z.string().optional(), gstin: z.string().max(15).optional(), address: z.string().optional(), state: z.string().min(2), payment_terms: z.string().optional(), is_active: z.boolean().optional() });
  return <CrudPage title="Suppliers" description="Raw-material and packaging vendors." path="/suppliers" method="put" canEdit={user?.role === "ADMIN"} schema={schema}
    mapIn={(v) => ({ ...v, contact: v.contact || null, gstin: v.gstin || null })} defaults={{ name: "", contact: "", gstin: "", address: "", state: "Tamil Nadu", payment_terms: "30 days", is_active: true }}
    fields={[{ name: "name", label: "Supplier name" }, { name: "contact", label: "Contact" }, { name: "gstin", label: "GSTIN" }, { name: "address", label: "Address" }, { name: "state", label: "State" }, { name: "payment_terms", label: "Payment terms" }, { name: "is_active", label: "Active", type: "checkbox" }]}
    columns={[{ key: "name", header: "Supplier" }, { key: "contact", header: "Contact" }, { key: "gstin", header: "GSTIN", render: (r) => r.gstin || "-" }, { key: "state", header: "State" }, { key: "payment_terms", header: "Terms" }, { key: "is_active", header: "Status", render: active }]} />;
}
