import { useParams } from "react-router-dom";
import { api } from "../api";
import { useAsync, useClient } from "../context";
import { Activity, FileText, ShieldCheck, ThumbsUp } from "lucide-react";
import { Chip, ErrorNote, Kpi, KpiStrip, Loading, PageHead, Panel, Quote } from "../components/ui";

export function Trust() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error } = useAsync(() => api.trust(clientId), [clientId]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const fooled = data.decoys - data.decoys_resisted;
  const offline = data.source !== "llm";

  return (
    <div className="reveal">
      <PageHead
        title="Accuracy"
        sub={<>How saidso did on {data.conversations} test conversations for the {data.pack} pack. Model: {data.model}.</>}
      />
      <p className="-mt-2 mb-5 max-w-3xl text-sm text-ink-2">
        It caught {data.found} of {data.planted} real risk signals and was fooled by {fooled} of {data.decoys} decoys. We planted known risk statements, plus decoys
        that sound risky but aren't, like a competitor review the vendor already won, and compare what the AI flagged with those known answers.
      </p>
      {offline && (
        <p className="mb-5 rounded-lg bg-med-soft px-4 py-2.5 text-sm text-med">
          These numbers come from the offline keyword baseline, not the AI. Add the team key to .env and rerun the seed to see the AI's results.
        </p>
      )}

      <KpiStrip>
        <Kpi tone="low" icon={<ShieldCheck size={22} strokeWidth={1.8} />} label="Real signals found" value={`${data.found}/${data.planted}`} chip={<Chip tone="low">{Math.round(data.recall * 100)}%</Chip>} />
        <Kpi tone={fooled ? "high" : "low"} icon={<Activity size={22} strokeWidth={1.8} />} label="Decoys flagged" value={`${fooled}/${data.decoys}`} chip={<Chip tone={fooled ? "high" : "low"}>{Math.round((data.precision) * 100)}% precise</Chip>} />
        <Kpi icon={<FileText size={22} strokeWidth={1.8} />} label="Test conversations" value={data.conversations} />
        <Kpi icon={<ThumbsUp size={22} strokeWidth={1.8} />} label="Flags people confirmed" value={data.feedback.confirmed} chip={<Chip>{data.feedback.dismissed} dismissed</Chip>} />
      </KpiStrip>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title="By signal type" className="lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] uppercase tracking-[0.08em] text-ink-3">
                  <th className="py-2 font-medium">Signal</th>
                  <th className="py-2 text-right font-medium">Planted</th>
                  <th className="py-2 text-right font-medium">Found</th>
                  <th className="py-2 text-right font-medium">False alarms</th>
                </tr>
              </thead>
              <tbody className="num">
                {data.per_type.map((r: any) => (
                  <tr key={r.signal_type} className="border-b border-line last:border-0">
                    <td className="py-2.5 font-medium">{r.label}</td>
                    <td className="py-2.5 text-right">{r.planted}</td>
                    <td className={`py-2.5 text-right ${r.found < r.planted ? "font-semibold text-med" : ""}`}>{r.found}</td>
                    <td className={`py-2.5 text-right ${r.false_alarms ? "font-semibold text-high" : "text-ink-3"}`}>{r.false_alarms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title={`False alarms (${data.false_alarm_rows.length})`}>
          {data.false_alarm_rows.length === 0 ? (
            <p className="text-sm text-ink-3">None. Every flag matched a planted risk.</p>
          ) : (
            <ul className="space-y-4">
              {data.false_alarm_rows.slice(0, 6).map((r: any, i: number) => (
                <li key={i}>
                  <p className="mb-1 text-xs font-medium text-high">Flagged as {r.label}{r.was_decoy ? ", but it was a decoy" : ""}</p>
                  <Quote text={r.quote} />
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title={`Missed (${data.misses.length})`}>
          {data.misses.length === 0 ? (
            <p className="text-sm text-ink-3">None. Every planted risk was found.</p>
          ) : (
            <ul className="space-y-4">
              {data.misses.slice(0, 6).map((r: any, i: number) => (
                <li key={i}>
                  <p className="mb-1 text-xs font-medium text-med">Missed {r.label}</p>
                  <Quote text={r.line} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
