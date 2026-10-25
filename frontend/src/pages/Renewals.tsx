import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, euroShort, pct, shortDate } from "../api";
import { useAsync, useClient } from "../context";
import { ErrorNote, Loading, RiskBar, RiskPill } from "../components/ui";

const WINDOWS = [30, 60, 90];

export function Renewals() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const nav = useNavigate();
  const [window, setWindow] = useState(90);
  const [band, setBand] = useState<"all" | "high" | "medium" | "low">("all");
  const { data, error } = useAsync(() => api.overview(clientId, window), [clientId, window]);
  const rows = useMemo(() => (data?.renewals ?? []).filter((r: any) => band === "all" || r.band === band), [data, band]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const v = client.pack.vocabulary;

  return (
    <div className="reveal">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[1.9rem] font-bold tracking-tight">All renewals</h1>
          <p className="mt-1 text-ink-2">
            {data.kpis.renewals} {v.accounts.toLowerCase()} renew in the next {window} days, worth {euroShort(data.kpis.total_value)} a year.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Segmented value={window} options={WINDOWS.map((w) => ({ value: w, label: `${w} days` }))} onChange={setWindow} />
          <Segmented
            value={band}
            options={[{ value: "all", label: "All" }, { value: "high", label: "High risk" }, { value: "medium", label: "Watch" }, { value: "low", label: "Healthy" }]}
            onChange={setBand}
          />
        </div>
      </header>

      <div className="overflow-x-auto rounded-xl border border-line bg-panel">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-ink-3">
              <th className="px-4 py-3 font-medium">{v.account}</th>
              <th className="px-4 py-3 font-medium">Risk</th>
              <th className="px-4 py-3 font-medium">Renews</th>
              <th className="px-4 py-3 text-right font-medium">Per year</th>
              <th className="px-4 py-3 text-right font-medium">{v.activity}</th>
              <th className="px-4 py-3 font-medium">What was said</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr
                key={r.account_id}
                tabIndex={0}
                onClick={() => nav(`/${clientId}/accounts/${r.account_id}`)}
                onKeyDown={(e) => e.key === "Enter" && nav(`/${clientId}/accounts/${r.account_id}`)}
                className="cursor-pointer border-b border-line last:border-0 hover:bg-paper"
              >
                <td className="px-4 py-3">
                  <div className="font-semibold">{r.name}</div>
                  <div className="text-xs text-ink-3">{r.segment}</div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <RiskBar score={r.score} band={r.band} />
                    <span className="hidden xl:inline"><RiskPill band={r.band} /></span>
                  </div>
                </td>
                <td className="num px-4 py-3">
                  {shortDate(r.renewal_date)} <span className="text-ink-3">({r.days_to_renewal} d)</span>
                </td>
                <td className="num px-4 py-3 text-right">{euroShort(r.annual_value)}</td>
                <td className={`num px-4 py-3 text-right ${r.activity_pct <= -0.08 ? "font-semibold text-high" : "text-ink-2"}`}>{pct(r.activity_pct)}</td>
                <td className="px-4 py-3 text-ink-2">{r.signals.length ? r.signals.join(", ") : <span className="text-ink-3">Nothing flagged</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="px-4 py-10 text-center text-sm text-ink-3">No renewals match these filters. Widen the window or pick another risk level.</p>}
      </div>
    </div>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-panel p-0.5" role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${o.value === value ? "bg-ink text-white" : "text-ink-2 hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
