import { Link } from "react-router-dom";
import { Button } from "../components/ui";
import { ShieldAlert, SearchX } from "lucide-react";

export function Unauthorized() {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <ShieldAlert className="mb-3 h-12 w-12 text-amber-500" />
      <h1 className="text-xl font-semibold">Access denied</h1>
      <p className="mt-1 max-w-sm text-sm text-slate-500">Your role is not permitted to view this page. The server enforces the same restriction on its APIs.</p>
      <Link to="/" className="mt-5"><Button>Back to home</Button></Link>
    </div>
  );
}
export function NotFound() {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <SearchX className="mb-3 h-12 w-12 text-slate-400" />
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-5"><Button>Go to home</Button></Link>
    </div>
  );
}
