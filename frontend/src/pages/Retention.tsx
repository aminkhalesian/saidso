import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowDown, ArrowUp, ChevronsUpDown, Info } from "lucide-react";
import { api, euro, shortDate } from "../api";
import { useAsync, useClient } from "../context";
import { Chip, ErrorNote, Loading, PageHead, Panel, RiskPill } from "../components/ui";

type Col = { key: string; label: string; fmt: string };
type Kpi = { id: string; section: string; name: string; headline: string; sub: string; period: string; what: string; why: string; how: string;
  status: "ok" | "none"; note: string; rows: any[]; columns: Col[] };

const SECTIONS = [
  { key: "leadership", title: "Leadership view", intro: "Which recurring revenue is exposed, where the risk is concentrated, and where growth may be." },
  { key: "csm", title: "CSM view", intro: "What is going wrong in the accounts, and which customer needs attention first." },
];
const SORTS = [
  { key: "score", label: "Risk", dir: -1 },
  { key: "days_to_renewal", label: "Renews in", dir: 1 },
  { key: "annual_value", label: "Contract value", dir: -1 },
];

function cell(fmt: string, v: any, row: any) {
  if (v === null || v === undefined || v === "") return <span className="text-ink-3">–</span>;
  switch (fmt) {
    case "risk": return <RiskPill band={row.band} score={v} />;
    case "eur": return <span className="num">{euro(v)}</span>;
    case "pct": return <span className="num">{Math.round(v * 100)}%</span>;
    case "days": return <span className="num">{v} days</span>;
    case "date": return <span className="num">{shortDate(v)}</span>;
    case "num": return <span className="num">{typeof v === "number" ? Math.round(v * 10) / 10 : v}</span>;
    default: return <span>{String(v)}</span>;
  }
}

function Info3({ k }: { k: Kpi }) {
  return (
    <dl className="grid gap-3 text-[13px] leading-relaxed text-ink-2 md:grid-cols-3">
      <div><dt className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">What it measures</dt><dd>{k.what}</dd></div>
      <div><dt className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">Why it matters</dt><dd>{k.why}</dd></div>
      <div><dt className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">How it is calculated</dt><dd>{k.how}</dd></div>
    </dl>
  );
}

function Drill({ k, clientId }: { k: Kpi; clientId: string }) {
  const [sort, setSort] = useState<{ key: string; dir: number } | null>(null);
  const rows = useMemo(() => {
    if (!sort) return k.rows;
    return [...k.rows].sort((a, b) => sort.dir * ((a[sort.key] ?? 0) - (b[sort.key] ?? 0)) || (a.days_to_renewal - b.days_to_renewal));
  }, [k.rows, sort]);
  const toggle = (key: string, dir: number) => setSort((s) => (s?.key === key ? { key, dir: -s.dir } : { key, dir }));
  const cols = k.columns;

  return (
    <div className="mt-4 rounded-[14px] border border-line bg-panel p-5 shadow-card" role="region" aria-label={`${k.name} details`}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-bold tracking-tight">{k.name}</h3>
        <span className="text-xs text-ink-3">Period: {k.period}</span>
      </div>
      <Info3 k={k} />
      {k.note && <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-xs text-ink-2">{k.note}</p>}
      {k.status === "none" ? (
        <p className="mt-4 rounded-[10px] border border-dashed border-line-2 px-4 py-6 text-center text-sm text-ink-2">
          Data unavailable. {k.sub}. This figure is not shown as zero because nothing is connected to measure it.
        </p>
      ) : rows.length === 0 ? (
        <p className="mt-4 rounded-[10px] border border-dashed border-line-2 px-4 py-6 text-center text-sm text-ink-2">
          No customers match in this period. The source is connected, so this is a real zero.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <span>{rows.length} {rows.length === 1 ? "row" : "rows"}. Sort by</span>
            {SORTS.map((s) => {
              const on = sort?.key === s.key;
              return (
                <button key={s.key} onClick={() => toggle(s.key, s.dir)} aria-pressed={on}
                  className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-semibold ${on ? "border-act bg-act text-white" : "border-line-2 bg-panel text-ink-2 hover:bg-paper"}`}>
                  {s.label} {on ? (sort!.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />) : <ChevronsUpDown size={12} />}
                </button>
              );
            })}
          </div>
          <table className="w-full min-w-[640px] border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-y border-line bg-paper text-[11px] uppercase tracking-[0.08em] text-ink-3">
                <th className="px-3 py-2 font-semibold">Customer</th>
                {cols.map((c) => <th key={c.key} className="px-3 py-2 font-semibold">{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.account_id}-${i}`} className="border-b border-line align-top hover:bg-paper">
                  <td className="px-3 py-2.5">
                    <Link className="font-semibold text-act hover:underline" to={`/${clientId}/accounts/${r.account_id}`}>{r.name}</Link>
                    <div className="text-xs text-ink-3">{r.segment}</div>
                  </td>
                  {cols.map((c) => <td key={c.key} className="px-3 py-2.5">{cell(c.fmt, r[c.key], r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Card({ k, open, onClick }: { k: Kpi; open: boolean; onClick: () => void }) {
  const none = k.status === "none";
  return (
    <button onClick={onClick} aria-expanded={open} title={`${k.what} ${k.how}`}
      className={`group min-w-0 rounded-[12px] border px-4 py-3.5 text-left transition-colors ${open ? "border-act bg-panel shadow-card" : "border-line bg-paper hover:border-line-2 hover:bg-panel"}`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase leading-tight tracking-[0.08em] text-ink-3">{k.name}</span>
        <Info size={14} className="mt-px shrink-0 text-ink-3" aria-hidden />
      </div>
      <div className={`num mt-1.5 font-bold leading-tight ${none ? "text-[1.05rem] text-ink-3" : "text-[1.6rem]"}`}>{k.headline}</div>
      <div className="mt-0.5 text-[12px] leading-snug text-ink-2">{k.sub}</div>
      <div className="mt-1.5 text-[11px] text-ink-3">{k.period}</div>
      <div className="mt-2 text-[12px] font-semibold text-act">{open ? "Hide details" : "Show customers"}</div>
    </button>
  );
}

export function Retention() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const [window, setWindow] = useState(90);
  const [open, setOpen] = useState<string | null>(null);
  const { data, error } = useAsync(() => api.retention(clientId, window), [clientId, window]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const kpis: Kpi[] = data.kpis;

  return (
    <div className="reveal">
      <PageHead
        title="Retention analytics"
        sub={`${data.renewals} renewals in the next ${data.window} days. A snapshot of today's data. Click any figure to see the customers behind it.`}
        aside={
          <div role="group" aria-label="Renewal horizon" className="inline-flex rounded-full border border-line-2 bg-panel p-0.5 text-[13px] font-semibold">
            {data.horizons.map((h: number) => (
              <button key={h} onClick={() => { setWindow(h); setOpen(null); }} aria-pressed={window === h}
                className={`rounded-full px-3.5 py-1.5 ${window === h ? "bg-act text-white" : "text-ink-2 hover:bg-paper"}`}>Next {h} days</button>
            ))}
          </div>
        }
      />
      <p className="mb-5 max-w-[80ch] text-[13px] leading-relaxed text-ink-2">
        The renewal horizon applies to every figure on this page. Figures about recent activity (conversations, ticket age, feature use) say which period they look at, and cover only the customers renewing in the horizon.
      </p>
      <div className="grid gap-5">
        {SECTIONS.map((s) => {
          const list = kpis.filter((k) => k.section === s.key);
          const sel = list.find((k) => k.id === open);
          return (
            <Panel key={s.key} title={s.title} aside={<span className="max-w-[60ch] text-right text-[12px] text-ink-3">{s.intro}</span>}>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
                {list.map((k) => <Card key={k.id} k={k} open={open === k.id} onClick={() => setOpen(open === k.id ? null : k.id)} />)}
              </div>
              {sel && <Drill k={sel} clientId={clientId} />}
            </Panel>
          );
        })}
      </div>
      {!data.sources.usage || !data.sources.support || !data.sources.billing || !data.sources.calls ? (
        <p className="mt-4 text-xs text-ink-2"><Chip tone="high">Limited data</Chip> {" "}Figures marked "Data unavailable" have no connected source yet.</p>
      ) : null}
    </div>
  );
}
