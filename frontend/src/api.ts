export type Band = "high" | "medium" | "low";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
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
  trust: (c: string) => req<any>(`/clients/${c}/trust`),
  sample: (c: string) => req<{ transcript: string }>(`/clients/${c}/sample-transcript`),
  analyze: (c: string, transcript: string) =>
    req<any>(`/clients/${c}/analyze`, { method: "POST", body: JSON.stringify({ transcript }) }),
  decide: (id: number, status: "approved" | "dismissed" | "draft", body?: string) =>
    req<any>(`/actions/${id}`, { method: "POST", body: JSON.stringify({ status, body }) }),
  feedback: (id: number, feedback: "confirmed" | "dismissed" | "open") =>
    req<any>(`/signals/${id}/feedback`, { method: "POST", body: JSON.stringify({ feedback }) }),
};

export const euro = (n: number) =>
  new Intl.NumberFormat("en-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

export const euroShort = (n: number) =>
  n >= 1_000_000 ? `€${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `€${Math.round(n / 1000)}k` : euro(n);

export const pct = (n: number) => `${n > 0 ? "+" : ""}${Math.round(n * 100)}%`;

export const shortDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
