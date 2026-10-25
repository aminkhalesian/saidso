import { createContext, useContext, useEffect, useState, ReactNode, DependencyList } from "react";
import { api } from "./api";

type Ctx = { clients: any[]; health: any | null };
const AppCtx = createContext<Ctx>({ clients: [], health: null });

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Ctx>({ clients: [], health: null });
  useEffect(() => {
    Promise.all([api.clients(), api.health()]).then(([clients, health]) => setState({ clients, health })).catch(() => {});
  }, []);
  return <AppCtx.Provider value={state}>{children}</AppCtx.Provider>;
}

export const useApp = () => useContext(AppCtx);

export function useClient(id?: string) {
  const { clients } = useApp();
  return clients.find((c) => c.id === id);
}

export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setError(null);
    fn().then((d) => alive && setData(d)).catch((e) => alive && setError(String(e.message ?? e)));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, reload: () => setTick((t) => t + 1), setData };
}
