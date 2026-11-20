import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Wrench } from "lucide-react";
import { useAuth } from "../lib/auth";
import { errorMessage } from "../lib/api";
import { Button, Field } from "../components/ui";

const schema = z.object({ username: z.string().min(1, "Enter your username"), password: z.string().min(1, "Enter your password") });
type F = z.infer<typeof schema>;

const DEMO = [["owner", "Owner"], ["admin", "Admin"], ["salesman_a", "Salesman A"], ["salesman_b", "Salesman B"], ["production", "Production"], ["accountant", "Accountant"]];

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [err, setErr] = useState("");
  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<F>({ resolver: zodResolver(schema) });
  if (user) return <Navigate to="/" replace />;
  const expired = new URLSearchParams(loc.search).get("expired");

  const submit = async (v: F) => {
    setErr("");
    try { await login(v.username, v.password); nav((loc.state as any)?.from || "/", { replace: true }); }
    catch (e: any) { setErr(errorMessage(e)); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-900 p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3 text-white">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500"><Wrench className="h-5 w-5" /></div>
          <div><p className="text-lg font-semibold leading-tight">FactoryFlow</p><p className="text-xs text-slate-400">Integrated Order-to-Audit Management</p></div>
        </div>
        <form onSubmit={handleSubmit(submit)} className="card space-y-4 p-6" noValidate>
          <h1 className="text-lg font-semibold text-slate-900">Sign in</h1>
          {expired && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Your session expired. Please sign in again.</p>}
          {err && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{err}</p>}
          <Field label="Username" error={errors.username?.message}><input className="input" autoComplete="username" autoCapitalize="none" {...register("username")} /></Field>
          <Field label="Password" error={errors.password?.message}><input className="input" type="password" autoComplete="current-password" {...register("password")} /></Field>
          <Button type="submit" className="w-full" loading={isSubmitting}>Sign in</Button>
          <div className="border-t border-slate-200 pt-4">
            <p className="mb-2 text-xs font-medium text-slate-500">Demo accounts (password: Demo@1234)</p>
            <div className="flex flex-wrap gap-2">
              {DEMO.map(([u, l]) => <button type="button" key={u} className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50" onClick={() => { setValue("username", u); setValue("password", "Demo@1234"); }}>{l}</button>)}
            </div>
          </div>
        </form>
        <p className="mt-4 text-center text-xs text-slate-500">Prototype with dummy data. GST handling is a simplified exercise assumption.</p>
      </div>
    </div>
  );
}
