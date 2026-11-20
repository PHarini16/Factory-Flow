import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ReactNode } from "react";
import { useAuth } from "./lib/auth";
import { Role } from "./lib/api";
import Layout from "./components/Layout";
import { Skeleton } from "./components/ui";
import Login from "./pages/Login";
import { NotFound, Unauthorized } from "./pages/Misc";
import Dashboard from "./pages/Dashboard";
import { SalesmanHome, NewOrder, MySales } from "./pages/Salesman";
import { OrdersPage, OrderDetail } from "./pages/Orders";
import { Customers, Products, Suppliers } from "./pages/MasterData";
import Purchases from "./pages/Purchases";
import Inventory from "./pages/Inventory";
import { ProductionHome, ProductionRuns, NewRun, RunDetail, BomPage } from "./pages/Production";
import { Invoices, Dispatch, Payments } from "./pages/Sales";
import Costing from "./pages/Costing";
import { Reports, AuditPage, UsersPage, DemoTools } from "./pages/Admin";

function Guard({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="p-8"><Skeleton className="h-8 w-60" /></div>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (roles && !roles.includes(user.role)) return <Unauthorized />;
  return <>{children}</>;
}

function Home() {
  const { user } = useAuth();
  if (user?.role === "SALESMAN") return <SalesmanHome />;
  if (user?.role === "PRODUCTION") return <ProductionHome />;
  return <Dashboard />;
}

const ALL: Role[] = ["OWNER", "ADMIN", "SALESMAN", "PRODUCTION", "ACCOUNTANT"];
const FIN: Role[] = ["OWNER", "ADMIN", "ACCOUNTANT"];
const OPS: Role[] = ["OWNER", "ADMIN", "PRODUCTION", "ACCOUNTANT"];

export default function App() {
  const g = (roles: Role[], el: ReactNode) => <Guard roles={roles}>{el}</Guard>;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Guard><Layout /></Guard>}>
        <Route index element={<Home />} />
        <Route path="new-order" element={g(["SALESMAN"], <NewOrder />)} />
        <Route path="my-sales" element={g(["SALESMAN"], <MySales />)} />
        <Route path="orders" element={g(["SALESMAN", "ADMIN", "OWNER", "ACCOUNTANT"], <OrdersPage />)} />
        <Route path="orders/:id" element={g(["SALESMAN", "ADMIN", "OWNER", "ACCOUNTANT"], <OrderDetail />)} />
        <Route path="customers" element={g(["ADMIN", "OWNER", "ACCOUNTANT"], <Customers />)} />
        <Route path="products" element={g(["ADMIN", "OWNER", "ACCOUNTANT", "PRODUCTION"], <Products />)} />
        <Route path="suppliers" element={g(["ADMIN", "OWNER", "ACCOUNTANT", "PRODUCTION"], <Suppliers />)} />
        <Route path="purchases" element={g(OPS, <Purchases />)} />
        <Route path="inventory" element={g(OPS, <Inventory />)} />
        <Route path="bom" element={g(OPS, <BomPage />)} />
        <Route path="production" element={g(OPS, <ProductionRuns />)} />
        <Route path="production/new" element={g(["PRODUCTION", "ADMIN"], <NewRun />)} />
        <Route path="production/:id" element={g(OPS, <RunDetail />)} />
        <Route path="costing" element={g(OPS, <Costing />)} />
        <Route path="invoices" element={g(["ADMIN", "OWNER", "ACCOUNTANT"], <Invoices />)} />
        <Route path="dispatch" element={g(["ADMIN"], <Dispatch />)} />
        <Route path="payments" element={g(FIN, <Payments />)} />
        <Route path="reports" element={g(["OWNER", "ADMIN", "ACCOUNTANT", "PRODUCTION"], <Reports />)} />
        <Route path="audit" element={g(FIN, <AuditPage />)} />
        <Route path="users" element={g(["OWNER"], <UsersPage />)} />
        <Route path="demo" element={g(["OWNER"], <DemoTools />)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
