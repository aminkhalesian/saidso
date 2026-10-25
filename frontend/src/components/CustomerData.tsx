import type { ReactNode } from "react";
import { Activity, LifeBuoy, Phone, Receipt } from "lucide-react";
import { euro, shortDate } from "../api";
import { Chip, Panel } from "./ui";

const n0 = (x: number) => new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 }).format(x);
const n1 = (x: number) => new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(x);
const sign = (p: number | null) => (p === null ? "" : `${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(Math.round(p * 100))}%`);

function Delta({ p }: { p: number | null }) {
  if (p === null) return null;
  return <Chip tone={p <= -0.15 ? "high" : p <= -0.05 ? "med" : "neutral"}>{sign(p)}</Chip>;
}

function Card({ icon, title, note, children }: { icon: ReactNode; title: string; note: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-xl border border-line p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <span className="grid size-6 shrink-0 place-items-center rounded-md bg-act-soft text-act">{icon}</span>
        {title}
      </h3>
      <p className="mb-3 mt-0.5 text-[11px] text-ink-3">{note}</p>
      <div className="space-y-2 text-sm">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-2">{label}</span>
      <span className="num flex items-center gap-1.5 text-right font-semibold">{children}</span>
    </div>
  );
}

const STATUS = { open: "Open", pending: "Waiting on us", solved: "Solved" } as const;
const INV = { paid: ["Paid", "low"], paid_late: ["Paid late", "med"], overdue: ["Overdue", "high"], open: ["Not due yet", "neutral"] } as const;

export function CustomerData({ s, vocab, account }: { s: any; vocab: any; account: string }) {
  const L = s.labels ?? {};
  const u = s.usage, sup = s.support, com = s.commercial, conv = s.conversations;
  const worst = u ? s.usage.features.filter((f: any) => f.pct !== null && f.pct <= -0.3).slice(0, 2) : [];
  return (
    <Panel title="Across all sources" aside={<span className="hidden text-xs text-ink-3 sm:inline">Usage, conversations, support and commercial data for {account}</span>}>
      <div className="grid gap-3 md:grid-cols-2">
        <Card icon={<Activity size={14} />} title={L.usage ?? "Product usage"} note={L.metric_note ?? ""}>
          {u ? (
            <>
              <Row label={L.metric ?? "Active users"}>{n1(u.metric)} <Delta p={u.metric_pct} /></Row>
              <Row label={`${L.logins ?? "Logins"}, 30 days`}>{n0(u.logins)} <Delta p={u.logins_pct} /></Row>
              <Row label="Last login">
                <span className={u.days_since_login >= 7 ? "text-high" : ""}>{u.days_since_login === 0 ? "today" : `${u.days_since_login} days ago`}</span>
              </Row>
              <Row label={L.utilization ?? "In use"}>{Math.round(u.utilization * 100)}%</Row>
              <Row label={L.features ?? "Features used"}>{u.features_used} of {u.features_total}</Row>
              {worst.length > 0 && (
                <p className="rounded-md bg-high-soft px-2.5 py-2 text-xs text-high">
                  {worst.map((f: any) => `${f.name}: ${n0(f.prev)} → ${n0(f.value)} ${L.feature_unit ?? ""}`).join(" · ")}
                </p>
              )}
            </>
          ) : <p className="text-ink-3">Not connected for this account.</p>}
        </Card>

        <Card icon={<Phone size={14} />} title="Conversations" note="Transcripts, with the exact quotes in Evidence">
          <Row label="Calls on record">{conv.count}</Row>
          <Row label="Most recent">{conv.last ? shortDate(conv.last) : "none"}</Row>
          <div>
            <p className="mb-1.5 text-ink-2">Signals raised</p>
            {conv.signals.length ? (
              <div className="flex flex-wrap gap-1.5">{conv.signals.map((l: string) => <Chip key={l} tone="high">{l}</Chip>)}</div>
            ) : <p className="text-ink-3">None. Nothing risky was said.</p>}
          </div>
        </Card>

        <Card icon={<LifeBuoy size={14} />} title={L.support ?? "Support"} note="Open tickets, complaints and unresolved issues">
          {sup ? (
            <>
              <Row label="Unresolved">
                {sup.unresolved} <span className="font-normal text-ink-3">of {sup.total}</span>
                {sup.high_priority > 0 && <Chip tone="high">{sup.high_priority} high priority</Chip>}
              </Row>
              {sup.unresolved > 0 && <Row label="Oldest unresolved">{sup.oldest_open_days} days</Row>}
              <ul className="divide-y divide-line">
                {sup.items.slice(0, 3).map((t: any) => (
                  <li key={t.id} className="flex items-start justify-between gap-3 py-2 first:pt-1">
                    <span className={`min-w-0 leading-snug ${t.status === "solved" ? "text-ink-3" : ""}`}>{t.subject}</span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <Chip tone={t.status === "solved" ? "low" : t.priority === "high" ? "high" : "med"}>{STATUS[t.status as keyof typeof STATUS]}</Chip>
                      {t.status !== "solved" && <span className="num text-[11px] text-ink-3">no update for {t.idle_days}d</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : <p className="text-ink-3">Not connected for this account.</p>}
        </Card>

        <Card icon={<Receipt size={14} />} title={L.commercial ?? "Commercial"} note="Contract, seats and payments">
          <Row label="Value a year">{euro(com.annual_value)}</Row>
          <Row label={L.purchased ?? vocab.capacity}>
            {com.seats} {com.seats_prev > com.seats && <Chip tone="high">was {com.seats_prev}</Chip>}
          </Row>
          <Row label={vocab.renewal}>in {com.days_to_renewal} days</Row>
          {com.invoices.length > 0 && (
            <>
              {com.overdue > 0 ? (
                <p className="rounded-md bg-high-soft px-2.5 py-2 text-xs font-medium text-high">
                  {com.overdue} overdue invoice{com.overdue > 1 ? "s" : ""}, {euro(com.overdue_amount)} unpaid
                </p>
              ) : com.paid_late > 0 ? (
                <p className="rounded-md bg-med-soft px-2.5 py-2 text-xs font-medium text-med">{com.paid_late} invoice paid late recently</p>
              ) : (
                <p className="rounded-md bg-low-soft px-2.5 py-2 text-xs font-medium text-low">All invoices paid on time</p>
              )}
              <ul className="divide-y divide-line">
                {com.invoices.slice(0, 3).map((i: any) => (
                  <li key={i.number} className="flex items-center justify-between gap-3 py-1.5 text-[13px]">
                    <span className="num text-ink-2">{i.number}</span>
                    <span className="num">{euro(i.amount)}</span>
                    <Chip tone={INV[i.status as keyof typeof INV][1]}>
                      {INV[i.status as keyof typeof INV][0]}{i.status === "overdue" ? ` ${i.days}d` : ""}
                    </Chip>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      </div>
      <p className="mt-3 text-xs text-ink-3">
        All four sources count toward the score: the usage trend, any cut in {vocab.capacity.toLowerCase()}, unresolved support tickets and overdue invoices, together with what customers said on calls.
      </p>
    </Panel>
  );
}
