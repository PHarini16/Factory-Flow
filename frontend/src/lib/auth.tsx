import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, TOKEN_KEY, User } from "./api";

interface AuthCtx { user: User | null; loading: boolean; login: (u: string, p: string) => Promise<User>; logout: () => void }
const Ctx = createContext<AuthCtx>(null as any);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!sessionStorage.getItem(TOKEN_KEY));

  useEffect(() => {
    if (!sessionStorage.getItem(TOKEN_KEY)) return;
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => sessionStorage.removeItem(TOKEN_KEY)).finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api.post("/auth/login", { username, password });
    sessionStorage.setItem(TOKEN_KEY, r.data.access_token);
    setUser(r.data.user);
    return r.data.user as User;
  };
  const logout = () => { sessionStorage.removeItem(TOKEN_KEY); setUser(null); };
  return <Ctx.Provider value={{ user, loading, login, logout }}>{children}</Ctx.Provider>;
}
