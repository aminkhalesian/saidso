import { Link, useParams } from "react-router-dom";
import { ArrowUpRight, TrendingDown } from "lucide-react";
import { api, euro, euroShort } from "../api";
import { useAsync, useClient } from "../context";
import { ActionCard } from "../components/ActionCard";
import { ErrorNote, Loading, Quote, RiskPill } from "../components/ui";

export function MyWeek() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error } = useAsync(() => api.overview(clientId), [clientId]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const v = client.pack.vocabulary;
  const first = data.client.user_name.split(" ")[0];
  const n = data.this_week.length;

  return (
    <div className="reveal">
      <header className="mb-8 max-w-3xl">
        <h1 className="text-[2.1rem] font-bold leading-[1.15] tracking-tight md:text-[2.6rem]">
          {first}, {n === 0 ? "nothing needs you this week" : `${n} ${v.renewal.toLowerCase()}${n === 1 ? " needs" : "s need"} you this week.`}
        </h1>
        <p className="mt-3 text-[1.05rem] leading-relaxed text-ink-2">
          {euro(data.kpis.value_at_risk)} a year is at high risk across {data.kpis.high_risk} of your {data.kpis.renewals}{" "}
          {v.accounts.toLowerCase()} renewing in the next 90 days. Each one below shows what the {v.account.toLowerCase()} said
          and a drafted next step. Nothing is sent until you approve it.
        </p>
      </header>

      <div className="space-y-4">
        {data.this_week.map((row: any) => (
          <article key={row.account_id} className="grid gap-5 rounded-xl border border-line bg-panel p-5 md:grid-cols-[190px_minmax(0,1fr)] xl:grid-cols-[210px_minmax(0,1fr)_360px]">
            <div className="space-y-2">
              <RiskPill band={row.band} score={row.score} />
              <Link to={`/${clientId}/accounts/${row.account_id}`} className="group flex items-start gap-1 text-lg font-bold leading-tight hover:text-act">
                {row.name}
                <ArrowUpRight size={16} className="mt-1 opacity-40 group-hover:opacity-100" />
              </Link>
              <dl className="num space-y-0.5 text-sm text-ink-2">
                <div>
                  Renews in <span className="font-semibold text-ink">{row.days_to_renewal} days</span>
                </div>
                <div>{euroShort(row.annual_value)} a year</div>
                {row.activity_pct <= -0.08 && (
                  <div className="flex items-start gap-1 text-high">
                    <TrendingDown size={14} className="mt-0.5 shrink-0" /> <span>{v.activity}: {Math.round(row.activity_pct * 100)}%</span>
                  </div>
                )}
              </dl>
            </div>

            <div className="min-w-0 border-line md:border-l md:pl-5">
              <p className="mb-2 text-xs font-medium text-ink-3">{row.reason?.kind === "signal" ? row.reason.label : "Why it's flagged"}</p>
              {row.reason?.kind === "signal" ? (
                <Quote text={row.reason.quote} speaker={row.reason.speaker} meta={`${row.reason.title}, ${row.reason.date}`} size="lg" />
              ) : (
                <p className="text-base text-ink-2">{row.reason?.text}</p>
              )}
              {(() => {
                const others = row.signals.filter((l: string) => l !== row.reason?.label);
                return others.length > 0 && <p className="mt-3 text-xs text-ink-3">Also flagged: {others.join(", ")}</p>;
              })()}
            </div>

            <div className="space-y-2 md:col-span-2 xl:col-span-1">
              <ActionCard action={row.action} compact />
              {row.more_actions > 0 && (
                <Link to={`/${clientId}/accounts/${row.account_id}`} className="block px-1 text-xs font-medium text-act hover:underline">
                  {row.more_actions} more drafted step{row.more_actions > 1 ? "s" : ""} on the account page
                </Link>
              )}
            </div>
          </article>
        ))}
      </div>

      <p className="mt-8 text-sm text-ink-3">
        The rest of your book is on{" "}
        <Link className="font-medium text-act hover:underline" to={`/${clientId}/renewals`}>
          All renewals
        </Link>
        , ranked by risk.
      </p>
    </div>
  );
}
