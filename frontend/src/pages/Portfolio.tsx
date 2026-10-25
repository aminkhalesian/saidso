import { useParams } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, euro, euroShort } from "../api";
import { useAsync, useClient } from "../context";
import { ErrorNote, Loading, Panel } from "../components/ui";

const COLORS = { high: "#B3263E", medium: "#E0A43A", low: "#9DC7B2" };

export function Portfolio() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error } = useAsync(() => api.portfolio(clientId), [clientId]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const v = client.pack.vocabulary;
  const share = data.total_value ? Math.round((data.at_risk_value / data.total_value) * 100) : 0;
  const maxDriver = Math.max(1, ...data.drivers.map((d: any) => d.value));
  const months = data.months.map((m: any) => ({ ...m, label: new Date(m.key + "-01").toLocaleDateString("en-GB", { month: "short" }) }));

  return (
    <div className="reveal">
      <header className="mb-7 max-w-3xl">
        <h1 className="text-[1.9rem] font-bold leading-tight tracking-tight">
          {euro(data.at_risk_value)} of {euro(data.total_value)} renewing in the next six months is at high risk.
        </h1>
        <p className="mt-2 text-ink-2">
          That's {share}% of the value across {data.accounts} {v.accounts.toLowerCase()}. Below: what's driving it, where it sits, and when it lands.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="What's driving the risk" className="lg:row-span-2">
          <ul className="space-y-4">
            {data.drivers.map((d: any) => (
              <li key={d.signal_type}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-semibold">{d.label}</span>
                  <span className="num text-ink-2">
                    {d.count} {d.count === 1 ? v.account.toLowerCase() : v.accounts.toLowerCase()}, {euroShort(d.value)}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-line">
                  <div className="h-full rounded-full bg-ink" style={{ width: `${(d.value / maxDriver) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs text-ink-3">Value of renewals where customers raised each signal in a conversation. One renewal can carry several signals.</p>
        </Panel>

        <Panel title="When it lands" aside={<Legend />}>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={months} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#7B8494" }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(n) => euroShort(n)} tick={{ fontSize: 11, fill: "#7B8494" }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(n: any) => euro(n)} cursor={{ fill: "#F3F5F8" }} />
                <Bar isAnimationActive={false} dataKey="high" stackId="a" fill={COLORS.high} name="High risk" />
                <Bar isAnimationActive={false} dataKey="medium" stackId="a" fill={COLORS.medium} name="Watch" />
                <Bar isAnimationActive={false} dataKey="low" stackId="a" fill={COLORS.low} name="Healthy" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Where it sits">
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.segments.slice(0, 7)} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
                <XAxis type="number" tickFormatter={(n) => euroShort(n)} tick={{ fontSize: 11, fill: "#7B8494" }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="key" width={130} tick={{ fontSize: 12, fill: "#4A5566" }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(n: any) => euro(n)} cursor={{ fill: "#F3F5F8" }} />
                <Bar isAnimationActive={false} dataKey="high" stackId="a" fill={COLORS.high} name="High risk" />
                <Bar isAnimationActive={false} dataKey="medium" stackId="a" fill={COLORS.medium} name="Watch" />
                <Bar isAnimationActive={false} dataKey="low" stackId="a" fill={COLORS.low} name="Healthy" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <span className="flex gap-3 text-xs text-ink-3">
      {(["high", "medium", "low"] as const).map((k) => (
        <span key={k} className="flex items-center gap-1">
          <span className="size-2 rounded-sm" style={{ background: COLORS[k] }} />
          {k === "high" ? "High risk" : k === "medium" ? "Watch" : "Healthy"}
        </span>
      ))}
    </span>
  );
}
