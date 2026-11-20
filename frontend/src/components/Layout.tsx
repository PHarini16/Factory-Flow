import { ReactNode, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BarChart3, Boxes, ClipboardList, Factory, FileText, Home, Layers, LogOut, Menu, Package, PlusCircle, ReceiptText, ScrollText, ShieldCheck, ShoppingCart, Truck,
  Users, UserCog, Wallet, X, Wrench, Calculator, Store, FlaskConical, Database } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Role } from "../lib/api";
import { ROLE_LABEL, cx } from "./ui";

interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean }
const i = (C: any) => <C className="h-[18px] w-[18px]" />;

export const NAV: Record<Role, NavItem[]> = {
  OWNER: [
    { to: "/", label: "Dashboard", icon: i(Home), end: true }, { to: "/orders", label: "Orders", icon: i(ClipboardList) }, { to: "/invoices", label: "Invoices", icon: i(FileText) },
    { to: "/payments", label: "Payments", icon: i(Wallet) }, { to: "/inventory", label: "Inventory", icon: i(Boxes) }, { to: "/production", label: "Production", icon: i(Factory) },
    { to: "/costing", label: "Costing", icon: i(Calculator) }, { to: "/purchases", label: "Purchases", icon: i(ShoppingCart) }, { to: "/customers", label: "Customers", icon: i(Store) },
    { to: "/products", label: "Products", icon: i(Package) }, { to: "/reports", label: "Reports", icon: i(BarChart3) }, { to: "/audit", label: "Audit log", icon: i(ShieldCheck) },
    { to: "/users", label: "Users", icon: i(UserCog) }, { to: "/demo", label: "Demo tools", icon: i(FlaskConical) },
  ],
  ADMIN: [
    { to: "/", label: "Dashboard", icon: i(Home), end: true }, { to: "/orders", label: "Orders", icon: i(ClipboardList) }, { to: "/invoices", label: "Invoices", icon: i(FileText) },
    { to: "/dispatch", label: "Dispatch", icon: i(Truck) }, { to: "/payments", label: "Payments", icon: i(Wallet) }, { to: "/customers", label: "Customers", icon: i(Store) },
    { to: "/products", label: "Products", icon: i(Package) }, { to: "/suppliers", label: "Suppliers", icon: i(Users) }, { to: "/purchases", label: "Purchases", icon: i(ShoppingCart) },
    { to: "/inventory", label: "Inventory & ledger", icon: i(Boxes) }, { to: "/reports", label: "Reports", icon: i(BarChart3) }, { to: "/audit", label: "Audit log", icon: i(ShieldCheck) },
  ],
  PRODUCTION: [
    { to: "/", label: "Production home", icon: i(Home), end: true }, { to: "/production/new", label: "New production run", icon: i(PlusCircle) },
    { to: "/production", label: "Production history", icon: i(Factory), end: true }, { to: "/bom", label: "BOM", icon: i(Layers) }, { to: "/purchases", label: "Material receipts", icon: i(ShoppingCart) },
    { to: "/inventory", label: "Stock & ledger", icon: i(Boxes) }, { to: "/costing", label: "Costing", icon: i(Calculator) }, { to: "/reports", label: "Variance reports", icon: i(BarChart3) },
  ],
  ACCOUNTANT: [
    { to: "/", label: "Financial dashboard", icon: i(Home), end: true }, { to: "/invoices", label: "Invoices", icon: i(FileText) }, { to: "/payments", label: "Payments", icon: i(Wallet) },
    { to: "/purchases", label: "Purchase register", icon: i(ShoppingCart) }, { to: "/reports", label: "Reports & GST", icon: i(ScrollText) }, { to: "/audit", label: "Audit log", icon: i(ShieldCheck) },
  ],
  SALESMAN: [
    { to: "/", label: "Home", icon: i(Home), end: true }, { to: "/new-order", label: "New order", icon: i(PlusCircle) }, { to: "/orders", label: "My orders", icon: i(ReceiptText) },
    { to: "/my-sales", label: "Customer sales", icon: i(BarChart3) },
  ],
};

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-5 py-5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-white"><Wrench className="h-4 w-4" /></div>
      <div><p className="text-sm font-semibold leading-tight text-white">FactoryFlow</p><p className="text-[11px] leading-tight text-slate-400">Order-to-Audit</p></div>
    </div>
  );
}

function SideLinks({ items, onNav }: { items: NavItem[]; onNav?: () => void }) {
  return (
    <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
      {items.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} onClick={onNav}
          className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors", isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white")}>
          {n.icon}{n.label}
        </NavLink>
      ))}
    </nav>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const items = NAV[user.role];
  const out = () => { logout(); nav("/login"); };
  const isSales = user.role === "SALESMAN";

  return (
    <div className="min-h-screen">
      {!isSales && (
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col bg-navy-900 lg:flex">
          <Brand />
          <SideLinks items={items} />
          <div className="border-t border-white/10 p-4">
            <p className="truncate text-sm font-medium text-white">{user.full_name}</p>
            <p className="mb-3 text-xs text-slate-400">{ROLE_LABEL[user.role]}</p>
            <button onClick={out} className="flex items-center gap-2 text-sm text-slate-300 hover:text-white"><LogOut className="h-4 w-4" />Sign out</button>
          </div>
        </aside>
      )}

      <header className={cx("sticky top-0 z-20 flex items-center justify-between border-b border-white/10 bg-navy-900 px-4 py-2.5 text-white", !isSales && "lg:hidden")} style={{ paddingTop: "max(0.625rem, env(safe-area-inset-top))" }}>
        <div className="flex items-center gap-2">
          {!isSales && <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded p-1.5 hover:bg-white/10"><Menu className="h-5 w-5" /></button>}
          <span className="text-sm font-semibold">FactoryFlow</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-slate-300 sm:block">{user.full_name}</span>
          <button onClick={out} aria-label="Sign out" className="rounded p-1.5 hover:bg-white/10"><LogOut className="h-[18px] w-[18px]" /></button>
        </div>
      </header>

      {open && !isSales && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-slate-900/60" />
          <div className="absolute inset-y-0 left-0 flex w-72 flex-col bg-navy-900" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pr-3"><Brand /><button onClick={() => setOpen(false)} className="rounded p-1.5 text-white hover:bg-white/10" aria-label="Close menu"><X className="h-5 w-5" /></button></div>
            <SideLinks items={items} onNav={() => setOpen(false)} />
          </div>
        </div>
      )}

      <main className={cx(!isSales && "lg:pl-60", isSales && "pb-24")}>
        <div className={cx("mx-auto p-4 sm:p-6", isSales ? "max-w-2xl" : "max-w-7xl")}><Outlet /></div>
      </main>

      {isSales && (
        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-slate-200 bg-white" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cx("flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium", isActive ? "text-brand-700" : "text-slate-500")}>{n.icon}{n.label}</NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}
