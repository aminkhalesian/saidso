import type { ReactNode } from "react";
import { euroShort } from "../api";
import { Panel } from "./ui";

function Tile({ label, value, note, tone }: { label: string; value: ReactNode; note: ReactNode; tone?: "high" | "low" }) {
  const color = tone === "high" ? "text-high" : tone === "low" ? "text-low" : "text-ink";
  return (
    <div className="min-w-0 rounded-[10px] border border-line bg-paper px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">{label}</div>
      <div className={`num mt-1 text-[1.45rem] font-bold leading-tight ${color}`}>{value}</div>
      <div className="mt-0.5 text-[12px] leading-snug text-ink-2">{note}</div>
    </div>
  );
}

function Group({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className="text-[13px] font-bold">{title}</h3>
        <span className="text-[12px] text-ink-3">{hint}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">{children}</div>
    </div>
  );
}

export function Outlook({ o }: { o: any }) {
  const g = o.grr_outlook;
  const gTone = g.pct == null ? undefined : g.pct >= g.benchmark.good ? "low" : "high";
  return (
    <Panel aside={<span className="text-[12px] text-ink-3">Snapshot of the renewals in view. Revenue figures are an outlook, not reported GRR or NRR.</span>} >
      <div className="grid gap-5">
        <Group title="Leadership view" hint="Revenue and customer health">
          <Tile label="Revenue retained, outlook" value={g.pct == null ? "–" : `${g.pct}%`} tone={gTone}
            note={<>If every high-risk renewal were lost. Industry GRR: median {g.benchmark.median}%, best {g.benchmark.best}%+.</>} />
          <Tile label="Customers at risk" value={`${o.logos_at_risk.count} of ${o.logos_at_risk.of}`} tone={o.logos_at_risk.count ? "high" : undefined}
            note={<>{euroShort(o.logos_at_risk.value)} a year ({o.logos_at_risk.pct}% of customers).</>} />
          <Tile label="Average health" value={o.health.average ?? "–"}
            note={<>{o.health.bands.low} healthy, {o.health.bands.medium} watch, {o.health.bands.high} high-risk.</>} />
          <Tile label="Contraction" value={euroShort(o.contraction.value)}
            note={<>Already lost to cuts at {o.contraction.logos} customers (estimated per seat).</>} />
          <Tile label="Expansion candidates" value={o.expansion.count} tone={o.expansion.count ? "low" : undefined}
            note={<>{euroShort(o.expansion.value)} a year with growing use or seats, not at risk.</>} />
        </Group>
        <Group title="CSM view" hint="What to act on this week">
          <Tile label="Licence utilisation" value={o.utilization.avg_pct == null ? "–" : `${o.utilization.avg_pct}%`} note="Average of what customers use against what they bought." />
          <Tile label="Features in decline" value={`${o.features.accounts_declining} of ${o.features.of}`} tone={o.features.accounts_declining ? "high" : undefined}
            note="Customers using at least two features 25% less than a month ago." />
          <Tile label="Call coverage" value={`${o.call_coverage.pct ?? "–"}%`} note={<>Customers with a recorded conversation in the last {o.call_coverage.window_days} days.</>} />
          <Tile label="Urgent open tickets" value={o.support.high_priority_open} tone={o.support.high_priority_open ? "high" : undefined}
            note={<>Across {o.support.accounts_with_open} customers with unresolved tickets.</>} />
          <Tile label="Overdue invoices" value={o.payments.overdue_invoices} tone={o.payments.overdue_invoices ? "high" : undefined}
            note={o.payments.overdue_invoices ? <>{euroShort(o.payments.overdue_amount)} unpaid, {o.payments.accounts} customers.</> : "Nothing overdue."} />
        </Group>
      </div>
    </Panel>
  );
}
