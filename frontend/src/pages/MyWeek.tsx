import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, Bell, ChevronDown, Clock, ListChecks } from "lucide-react";
import { api, euro, euroShort } from "../api";
import { useAsync, useClient } from "../context";
import { ActionCard } from "../components/ActionCard";
import { BAND_FILL, Chip, ErrorNote, Initials, Kpi, KpiStrip, Loading, Panel, Quote, RiskPill, ScoreRing } from "../components/ui";

export function MyWeek() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error } = useAsync(() => api.overview(clientId), [clientId]);
  const [open, setOpen] = useState<number | null>(null);

  const stats = useMemo(() => {
    const rows: any[] = data?.renewals ?? [];
    const money = { high: 0, medium: 0, low: 0 } as Record<string, number>;
    const count = { high: 0, medium: 0, low: 0 } as Record<string, number>;
    const sigs = new Map<string, number>();
    rows.forEach((r) => {
      money[r.band] += r.annual_value;
      count[r.band] += 1;
      r.signals.forEach((s: string) => sigs.set(s, (sigs.get(s) ?? 0) + 1));
    });
    const next = rows.length ? rows.reduce((a, b) => (b.days_to_renewal < a.days_to_renewal ? b : a)) : null;
    return { money, count, signals: [...sigs.entries()].sort((a, b) => b[1] - a[1]), next };
  }, [data]);

  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const v = client.pack.vocabulary;
  const n = data.this_week.length;
  const first = (open === null && data.this_week[0]?.account_id) || open;
  const total = stats.money.high + stats.money.medium + stats.money.low;

  return (
    <div className="reveal">
      <header className="mb-5">
        <h1 className="text-[1.65rem] font-bold leading-tight tracking-tight">My week</h1>
        <p className="text-[13px] text-ink-2">{data.client.user_name} · {v.renewal.toLowerCase()}s in the next 90 days</p>
      </header>

      <KpiStrip>
        <Kpi tone="high" icon={<AlertTriangle size={22} strokeWidth={1.8} />} label="High-risk value" value={euroShort(data.kpis.value_at_risk)} chip={<Chip tone="high">{data.kpis.high_risk} of {data.kpis.renewals} {v.accounts.toLowerCase()}</Chip>} />
        <Kpi icon={<Bell size={22} strokeWidth={1.8} />} label="Need you this week" value={n} chip={<Chip tone="high">to approve</Chip>} />
        <Kpi icon={<Clock size={22} strokeWidth={1.8} />} label={`Next ${v.renewal.toLowerCase()}`} value={stats.next ? `${stats.next.days_to_renewal} days` : "–"} chip={stats.next && <Chip>{stats.next.name}</Chip>} />
        <Kpi icon={<ListChecks size={22} strokeWidth={1.8} />} label="Drafted steps waiting" value={data.kpis.open_actions} chip={<Chip>{data.kpis.signals} signals</Chip>} />
      </KpiStrip>

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Panel className="!p-0">
          <div className="flex items-center gap-3 px-6 pb-3.5 pt-5">
            <h2 className="text-base font-bold tracking-tight">Needs you</h2>
            <Chip tone="high">{n}</Chip>
          </div>
          <div className="hidden grid-cols-[minmax(0,1.5fr)_56px_160px_110px_80px_24px] gap-3.5 border-y border-line bg-paper px-6 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3 lg:grid">
            <span>{v.account}</span><span>Risk</span><span>Signal</span><span>Renews in</span><span className="text-right">{v.activity.split(" ").slice(-1)[0] === "users" ? "Usage" : "Activity"}</span><span />
          </div>
          {n === 0 && <p className="px-6 py-10 text-center text-ink-3">Nothing needs you this week.</p>}
          {data.this_week.map((row: any) => {
            const isOpen = first === row.account_id;
            const urgent = row.days_to_renewal <= 14;
            const others = row.signals.filter((l: string) => l !== row.reason?.label);
            return (
              <article key={row.account_id} className="border-b border-line last:border-0">
                <button
                  className="grid w-full grid-cols-[minmax(0,1fr)_42px_24px] items-center gap-3.5 px-6 py-3.5 text-left hover:bg-paper lg:grid-cols-[minmax(0,1.5fr)_56px_160px_110px_80px_24px]"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? -1 : row.account_id)}
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <Initials name={row.name} />
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{row.name}</span>
                      <span className="num block text-xs text-ink-2">{row.segment} · {euroShort(row.annual_value)} a year</span>
                    </span>
                  </span>
                  <ScoreRing score={row.score} band={row.band} />
                  <span className="hidden whitespace-nowrap lg:block">
                    <Chip tone="high">{row.reason?.label ?? "Flagged"}</Chip>
                    {others.length > 0 && <span className="ml-1 text-[11px] text-ink-2">+{others.length}</span>}
                  </span>
                  <span className="num hidden lg:block">
                    <b className={urgent ? "text-high" : ""}>{row.days_to_renewal} days</b>
                    <span className="mt-1 block h-1 rounded-full bg-paper-2" title={`Time left until renewal, out of 90 days`}><i className="block h-full rounded-full" style={{ width: `${Math.max(6, Math.min(100, (row.days_to_renewal / 90) * 100))}%`, background: urgent ? BAND_FILL.high : "#111827" }} /></span>
                  </span>
                  <span className="hidden text-right lg:block">{row.usage_known === false ? <span className="text-xs text-ink-3">–</span> : row.activity_pct <= -0.08 ? <Chip tone="high">{Math.round(row.activity_pct * 100)}%</Chip> : <span className="text-xs text-ink-3">{Math.round(row.activity_pct * 100)}%</span>}</span>
                  <ChevronDown size={18} className={`text-ink-3 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                </button>
                {!isOpen && row.reason?.kind === "signal" && (
                  <p className="quote flex min-w-0 items-center gap-2.5 truncate px-6 pb-3.5 pl-[74px] text-sm text-ink-2">
                    <i className="inline-block h-4 w-[3px] shrink-0 rounded-sm bg-brass" />
                    <span className="truncate">“{row.reason.quote}”</span>
                  </p>
                )}
                {isOpen && (
                  <div className="mx-6 mb-5 rounded-xl border border-line bg-paper p-5">
                    <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-med">{row.reason?.kind === "signal" ? row.reason.label : "Why it's flagged"}</p>
                    {row.reason?.kind === "signal" ? (
                      <Quote text={row.reason.quote} speaker={row.reason.speaker} meta={`${row.reason.title}, ${row.reason.date}`} size="lg" />
                    ) : (
                      <p className="text-ink-2">{row.reason?.text}</p>
                    )}
                    {others.length > 0 && <p className="mt-3 text-xs text-ink-2">Also flagged: {others.join(", ")}</p>}
                    <div className="mt-4 space-y-2 border-t border-line pt-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">Drafted next step</p>
                      <ActionCard action={row.action} compact />
                      <div className="flex justify-between pt-1 text-xs">
                        {row.more_actions > 0 ? <span className="text-ink-2">{row.more_actions} more drafted step{row.more_actions > 1 ? "s" : ""}</span> : <span />}
                        <Link to={`/${clientId}/accounts/${row.account_id}`} className="font-semibold text-act hover:underline">Open {v.account.toLowerCase()} →</Link>
                      </div>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
          <div className="border-t border-line px-6 py-3.5 text-[13px]">
            <Link className="font-semibold text-act hover:underline" to={`/${clientId}/renewals`}>See all {data.kpis.renewals} {v.renewal.toLowerCase()}s →</Link>
          </div>
        </Panel>

        <div className="space-y-5">
          <Panel title="What clients are saying">
            <div className="flex flex-wrap gap-2">
              {stats.signals.map(([label, c]) => (
                <span key={label} className="inline-flex items-center gap-2 rounded-full border border-line bg-paper py-1 pl-3 pr-1.5 text-xs font-medium">
                  {label}
                  <b className="num grid min-w-[22px] place-items-center rounded-full bg-ink px-1.5 text-[11px] text-paper">{c}</b>
                </span>
              ))}
              {stats.signals.length === 0 && <span className="text-sm text-ink-3">No signals yet.</span>}
            </div>
            <p className="mt-4 text-xs text-ink-3">Number of {v.accounts.toLowerCase()} that raised each signal. One can raise several.</p>
          </Panel>

          <Panel title="Where the money sits">
            <Pie parts={[["high", stats.money.high], ["medium", stats.money.medium], ["low", stats.money.low]]} />
            <ul className="mt-2">
              {([["high", "High risk"], ["medium", "Watch"], ["low", "Healthy"]] as const).map(([b, l]) => (
                <li key={b} className="grid grid-cols-[12px_1fr_auto] items-center gap-2.5 border-t border-line py-2 text-[13px]">
                  <i className="size-2.5 rounded-[3px]" style={{ background: BAND_FILL[b] }} />
                  <b className="font-semibold">{l}</b>
                  <span className="num text-ink-2">{euroShort(stats.money[b])} · {stats.count[b]} {stats.count[b] === 1 ? v.account.toLowerCase() : v.accounts.toLowerCase()}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-ink-3">{euro(total)} renewing in the next 90 days.</p>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Pie({ parts }: { parts: readonly (readonly [keyof typeof BAND_FILL, number])[] }) {
  const total = parts.reduce((t, p) => t + p[1], 0) || 1;
  let a = -Math.PI / 2;
  const paths = parts.filter((p) => p[1] > 0).map(([b, val]) => {
    const f = val / total;
    const a2 = a + f * 2 * Math.PI;
    const d = f >= 0.9999
      ? "M0 -1 A1 1 0 1 1 0 1 A1 1 0 1 1 0 -1Z"
      : `M0 0 L${Math.cos(a)} ${Math.sin(a)} A1 1 0 ${f > 0.5 ? 1 : 0} 1 ${Math.cos(a2)} ${Math.sin(a2)}Z`;
    a = a2;
    return <path key={b} d={d} fill={BAND_FILL[b]} stroke="#fff" strokeWidth=".04" />;
  });
  return (
    <div className="my-3 flex justify-center">
      <svg width="150" height="150" viewBox="-1 -1 2 2" role="img" aria-label="Renewal value by risk band">{paths}</svg>
    </div>
  );
}
