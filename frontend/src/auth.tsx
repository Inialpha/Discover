import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokenStore, type User } from "./api";

interface Ctx { user: User | null; ready: boolean; signIn(t: string, u: User): void; signOut(): void }
const AuthCtx = createContext<Ctx>({ user: null, ready: false, signIn() {}, signOut() {} });
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return; }
    api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setReady(true));
  }, []);
  return (
    <AuthCtx.Provider value={{
      user, ready,
      signIn: (t, u) => { tokenStore.set(t); setUser(u); },
      signOut: () => { tokenStore.clear(); setUser(null); },
    }}>{children}</AuthCtx.Provider>
  );
}
