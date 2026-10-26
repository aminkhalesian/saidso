import snapshot from "snapshot-data";

export type Band = "high" | "medium" | "low";

// Offline copy: every page reads from a snapshot of the API taken when the file was made.
export const STATIC = import.meta.env.VITE_STATIC === "1";

function findAction(id: number): any {
  for (const [k, v] of Object.entries<any>(snapshot)) {
    if (k.includes("/overview")) {
      for (const r of v.this_week ?? []) if (r.action?.id === id) return r.action;
    } else if (/\/accounts\/\d+$/.test(k)) {
      const a = (v.actions ?? []).find((x: any) => x.id === id);
      if (a) return a;
    }
  }
  return null;
}

async function staticReq<T>(path: string, init?: RequestInit): Promise<T> {
  if (!init?.method || init.method === "GET") {
    const snap = snapshot as Record<string, any>;
    const hit = snap[path] ?? snap[path.split("?")[0]];
    if (hit === undefined) throw new Error("404: not part of the offline copy");
    return hit as T;
  }
  const body = init.body ? JSON.parse(String(init.body)) : {};
  const m = path.match(/\/actions\/(\d+)$/);
  if (m) {                                             // decisions only live in this browser tab
    const a = findAction(Number(m[1])) ?? { id: Number(m[1]) };
    return { ...a, status: body.status, body: body.body ?? a.body } as T;
  }
  if (/\/signals\//.test(path)) return { ok: true, feedback: body.feedback } as T;
  throw new Error("Not available in the offline copy. Run the live app to analyse a new call.");
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  if (STATIC) return staticReq<T>(path, init);
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export const api = {
  health: () => req<any>("/health"),
  clients: () => req<any[]>("/clients"),
  overview: (c: string, window = 90) => req<any>(`/clients/${c}/overview?window=${window}`),
  account: (c: string, id: number | string) => req<any>(`/clients/${c}/accounts/${id}`),
  portfolio: (c: string) => req<any>(`/clients/${c}/portfolio`),
  sources: (c: string) => req<any>(`/clients/${c}/sources`),
  trust: (c: string) => req<any>(`/clients/${c}/trust`),
  sample: (c: string) => req<{ transcript: string }>(`/clients/${c}/sample-transcript`),
  analyze: (c: string, transcript: string) =>
    req<any>(`/clients/${c}/analyze`, { method: "POST", body: JSON.stringify({ transcript }) }),
  retention: (c: string, window = 90) => req<any>(`/clients/${c}/retention?window=${window}`),
  importTemplate: (c: string) => req<{ csv: string }>(`/clients/${c}/import-template`),
  importCsv: (c: string, csv: string) => req<any>(`/clients/${c}/import`, { method: "POST", body: JSON.stringify({ csv }) }),
  acceptImport: (c: string) => req<any>(`/clients/${c}/import/accept`, { method: "POST" }),
  declineImport: (c: string) => req<any>(`/clients/${c}/import/pending`, { method: "DELETE" }),
  undoImport: (c: string) => req<any>(`/clients/${c}/import`, { method: "DELETE" }),
  decide: (client: string, id: number, status: "approved" | "dismissed" | "draft", body?: string) =>
    req<any>(`/clients/${client}/actions/${id}`, { method: "POST", body: JSON.stringify({ status, body }) }),
  feedback: (client: string, id: number, feedback: "confirmed" | "dismissed" | "open") =>
    req<any>(`/clients/${client}/signals/${id}/feedback`, { method: "POST", body: JSON.stringify({ feedback }) }),
};

export const euro = (n: number) =>
  new Intl.NumberFormat("en-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

export const euroShort = (n: number) =>
  n >= 1_000_000 ? `€${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `€${Math.round(n / 1000)}k` : euro(n);

export const pct = (n: number) => `${n > 0 ? "+" : ""}${Math.round(n * 100)}%`;

export const shortDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
