import { createContext, ReactNode, useCallback, useContext, useState } from "react";
import { AlertTriangle, CheckCircle2, Inbox, Loader2, X, XCircle } from "lucide-react";
import { Role } from "../lib/api";

export const cx = (...a: (string | false | undefined | null)[]) => a.filter(Boolean).join(" ");

// ---------- toasts
type Toast = { id: number; kind: "success" | "error"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});
export const useToast = () => {
  const t = useContext(ToastCtx);
  return { success: (s: string) => t("success", s), error: (s: string) => t("error", s) };
};
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-3 bottom-20 z-[100] flex flex-col items-center gap-2 sm:inset-x-auto sm:bottom-4 sm:right-4 sm:items-end" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cx("pointer-events-auto flex max-w-md items-start gap-2 rounded-lg border px-4 py-3 text-sm shadow-lg", t.kind === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-rose-200 bg-rose-50 text-rose-900")}>
            {t.kind === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ---------- primitives
export function Button({ variant = "primary", loading, className, children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; loading?: boolean }) {
  return (
    <button {...p} disabled={p.disabled || loading} className={cx("btn", `btn-${variant}`, className)}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Field({ label, error, children, hint }: { label: string; error?: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-rose-600" role="alert">{error}</span>}
    </label>
  );
}

export const Card = ({ children, className }: { children: ReactNode; className?: string }) => <div className={cx("card", className)}>{children}</div>;

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const TONES: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200", red: "bg-rose-50 text-rose-700 ring-rose-200", amber: "bg-amber-50 text-amber-800 ring-amber-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200", slate: "bg-slate-100 text-slate-700 ring-slate-200", teal: "bg-teal-50 text-teal-700 ring-teal-200",
};
const STATUS_TONE: Record<string, string> = {
  DRAFT: "slate", SUBMITTED: "amber", APPROVED: "blue", REJECTED: "red", INVOICED: "teal", PARTIALLY_DISPATCHED: "amber", DISPATCHED: "green", CANCELLED: "red",
  POSTED: "green", RECEIVED: "green", ORDERED: "amber", PARTIAL: "amber", NOT_DISPATCHED: "slate", ALERT: "red", OK: "green", COMPLETED: "green",
};
export function Badge({ children, tone }: { children: ReactNode; tone?: keyof typeof TONES }) {
  return <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", TONES[tone || "slate"])}>{children}</span>;
}
export const StatusBadge = ({ status }: { status: string }) => <Badge tone={STATUS_TONE[status] || "slate"}>{status.replace(/_/g, " ")}</Badge>;

export function Skeleton({ className }: { className?: string }) { return <div className={cx("animate-pulse rounded bg-slate-200", className)} />; }
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return <div className="space-y-2 p-4">{Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>;
}
export function EmptyState({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
      <Inbox className="mb-3 h-10 w-10 text-slate-300" />
      <p className="font-medium text-slate-700">{title}</p>
      {text && <p className="mt-1 max-w-sm text-sm text-slate-500">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
export function ErrorState({ error, retry }: { error: any; retry?: () => void }) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      <AlertTriangle className="mb-2 h-8 w-8 text-rose-400" />
      <p className="text-sm text-slate-700">{error?.response?.data?.message || error?.response?.data?.detail || error?.message || "Failed to load"}</p>
      {retry && <Button variant="secondary" className="mt-3" onClick={retry}>Retry</Button>}
    </div>
  );
}

// ---------- dialogs
export function Modal({ open, title, onClose, children, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-0 sm:items-center sm:p-4" onMouseDown={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className={cx("max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:rounded-2xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Close"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", danger, onConfirm, onClose, loading, children }:
  { open: boolean; title: string; message: string; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onClose: () => void; loading?: boolean; children?: ReactNode }) {
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <p className="mb-4 text-sm text-slate-600">{message}</p>
      {children}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}

// ---------- KPI + data table
export function Kpi({ label, value, hint, icon, tone }: { label: string; value: ReactNode; hint?: string; icon?: ReactNode; tone?: "default" | "alert" }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        {icon && <span className={cx("rounded-lg p-1.5", tone === "alert" ? "bg-rose-50 text-rose-600" : "bg-brand-50 text-brand-700")}>{icon}</span>}
      </div>
      <p className={cx("mt-2 text-xl font-semibold tabular-nums sm:text-2xl", tone === "alert" ? "text-rose-600" : "text-slate-900")}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}

export interface Column<T> { key: string; header: string; render?: (row: T) => ReactNode; align?: "right"; className?: string }
export function DataTable<T extends Record<string, any>>({ columns, rows, loading, error, empty, onRowClick, rowKey }: {
  columns: Column<T>[]; rows?: T[]; loading?: boolean; error?: any; empty?: ReactNode; onRowClick?: (r: T) => void; rowKey?: (r: T, i: number) => string | number;
}) {
  if (loading) return <TableSkeleton />;
  if (error) return <ErrorState error={error} />;
  if (!rows || rows.length === 0) return <>{empty || <EmptyState title="No records found" text="Try adjusting your filters." />}</>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200">
        <thead><tr>{columns.map((c) => <th key={c.key} className={cx("th", c.align === "right" && "text-right")}>{c.header}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r, i) : (r.id ?? i)} onClick={onRowClick ? () => onRowClick(r) : undefined} className={cx(onRowClick && "cursor-pointer hover:bg-slate-50")}>
              {columns.map((c) => <td key={c.key} className={cx("td", c.align === "right" && "text-right tabular-nums", c.className)}>{c.render ? c.render(r) : (r[c.key] as ReactNode)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)} className={cx("whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium", value === t.id ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800")}>{t.label}</button>
      ))}
    </div>
  );
}

export const ROLE_LABEL: Record<Role, string> = { OWNER: "Owner", ADMIN: "Administrator", SALESMAN: "Salesman", PRODUCTION: "Production", ACCOUNTANT: "Accountant" };
