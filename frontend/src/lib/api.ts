import axios from "axios";

export const TOKEN_KEY = "ff_token";
export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || "/api/v1" });

api.interceptors.request.use((cfg) => {
  const t = sessionStorage.getItem(TOKEN_KEY);
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    // Session expiry / invalid token: drop it and return to the login page.
    if (err.response?.status === 401 && !err.config?.url?.includes("/auth/login")) {
      sessionStorage.removeItem(TOKEN_KEY);
      if (location.pathname !== "/login") location.href = "/login?expired=1";
    }
    return Promise.reject(err);
  }
);

export function errorMessage(e: any): string {
  const d = e?.response?.data;
  if (d?.message) return d.message;
  if (typeof d?.detail === "string") return d.detail;
  if (Array.isArray(d?.detail)) return d.detail.map((x: any) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; ");
  return e?.message || "Something went wrong";
}

export async function download(path: string, params: Record<string, any> = {}, filename?: string) {
  const r = await api.get(path, { params, responseType: "blob" });
  const cd = r.headers["content-disposition"] as string | undefined;
  const name = filename || cd?.match(/filename="?([^"]+)"?/)?.[1] || "download";
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

export const num = (v: any) => (v === null || v === undefined || v === "" ? 0 : Number(v));
export const money = (v: any) => "₹" + num(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const qty = (v: any) => num(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });
export const pct = (v: any) => `${num(v) > 0 ? "+" : ""}${num(v).toFixed(2)}%`;
export const fmtDate = (v: any) => (v ? new Date(v).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "-");
export const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
export const today = () => new Date().toISOString().slice(0, 10);

export type Role = "OWNER" | "ADMIN" | "SALESMAN" | "PRODUCTION" | "ACCOUNTANT";
export interface User { id: number; username: string; full_name: string; role: Role; email?: string; is_active: boolean }
