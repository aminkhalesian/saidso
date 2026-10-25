import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, X, Phone, CalendarClock, Minus, Link2 } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, euro, pct, shortDate } from "../api";
import { useAsync, useClient } from "../context";
import { ActionCard } from "../components/ActionCard";
import { CustomerData } from "../components/CustomerData";
import { Cite, ErrorNote, Loading, Panel, Quote, RiskPill } from "../components/ui";

export function Account() {
  const { clientId = "", accountId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error, reload } = useAsync(() => api.account(clientId, accountId), [clientId, accountId]);
  const [flash, setFlash] = useState<string | null>(null);
  const [openConv, setOpenConv] = useState<number | null>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  const v = client.pack.vocabulary;
  const { account: a, contract: c, score: sc, brief } = data;

  function jump(id: string) {
    const ev = brief.evidence.find((e: any) => e.id === id);
    if (ev?.conversation_id) setOpenConv(null);
    document.getElementById(`ev-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(id);
    setTimeout(() => setFlash(null), 1600);
  }

  async function feedback(signalId: number, f: "confirmed" | "dismissed" | "open") {
    await api.feedback(signalId, f);
    reload();
  }

  const signalById = Object.fromEntries(data.signals.map((s: any) => [s.id, s]));
  const quotes: string[] = data.signals.map((s: any) => s.quote);
  const chart = data.activity.map((p: any, i: number, arr: any[]) => {
    const win = arr.slice(Math.max(0, i - 6), i + 1);
    return { day: p.day, value: p.value, avg: i >= 6 ? win.reduce((t: number, x: any) => t + x.value, 0) / win.length : null };
  });
  const tone = sc.activity_pct <= -0.08 ? "#E5534B" : "#1E3A5F";

  return (
    <div className="reveal">
      <Link to={`/${clientId}/week`} className="mb-4 inline-flex items-center gap-1 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft size={15} /> My week
      </Link>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[1.65rem] font-bold tracking-tight">{a.name}</h1>
          <RiskPill band={sc.band} score={sc.score} />
        </div>
        <p className="num mt-1.5 text-sm text-ink-2">
          {v.renewal} on {shortDate(c.renewal_date)}, in {sc.days_to_renewal} days. {euro(c.annual_value)} a year, {c.capacity} {v.capacity.toLowerCase()}.{" "}
          {a.segment}. Contact: {a.contact_name}, {a.contact_role}.
        </p>
        <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-3">
          <Link2 size={13} /> Billing record “{c.billing_name}” matched to this {v.account.toLowerCase()} ({Math.round(c.match_confidence * 100)}% name match)
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_370px]">
        <div className="space-y-5">
          <Panel title="Renewal brief" aside={<span className="text-xs text-ink-3">{data.brief_source === "llm" ? "Written by AI from the evidence below" : "Written from the evidence below"}</span>}>
            <div className="max-w-[68ch] space-y-2.5 text-[1.02rem] leading-relaxed">
              {brief.sentences.map((s: any, i: number) => (
                <p key={i}>
                  {s.text}
                  {s.evidence.map((id: string) => <Cite key={id} id={id} onClick={() => jump(id)} />)}
                </p>
              ))}
            </div>
            <div className="mt-4 rounded-lg bg-act-soft px-4 py-3 text-[0.97rem]">
              <span className="font-semibold text-act">Next step: </span>
              {brief.next_step.text}
              {brief.next_step.evidence.map((id: string) => <Cite key={id} id={id} onClick={() => jump(id)} />)}
            </div>
          </Panel>

          <CustomerData s={data.sources} vocab={v} account={a.name} />

          <Panel title="Evidence" aside={<span className="text-xs text-ink-3">Confirm or dismiss each flag; dismissed flags stop counting toward the score</span>}>
            <ol className="space-y-3">
              {brief.evidence.map((e: any) => {
                const sig = e.signal_id ? signalById[e.signal_id] : null;
                return (
                  <li
                    key={e.id}
                    id={`ev-${e.id}`}
                    className={`scroll-mt-24 rounded-xl border p-4 transition-colors ${flash === e.id ? "border-act bg-act-soft" : "border-line"}`}
                  >
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <span className="flex items-center gap-2 text-sm font-semibold">
                        <span className="rounded bg-act px-1.5 text-[0.68rem] font-bold leading-[1.15rem] text-white">{e.id}</span>
                        {e.kind === "signal" ? e.label : e.kind === "activity" ? v.activity : e.kind === "capacity" ? v.capacity : v.renewal}
                      </span>
                      {sig && (
                        <span className="flex items-center gap-1">
                          {sig.feedback === "confirmed" ? (
                            <FeedbackTag label="Confirmed" onUndo={() => feedback(sig.id, "open")} />
                          ) : (
                            <>
                              <button onClick={() => feedback(sig.id, "confirmed")} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-low hover:bg-low-soft">
                                <Check size={13} /> Correct
                              </button>
                              <button onClick={() => feedback(sig.id, "dismissed")} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-ink-3 hover:bg-paper hover:text-ink">
                                <X size={13} /> Not a risk
                              </button>
                            </>
                          )}
                        </span>
                      )}
                    </div>
                    {e.kind === "signal" ? (
                      <Quote text={e.quote} speaker={e.speaker} meta={`${e.title}, ${e.date}`} />
                    ) : (
                      <p className="text-sm text-ink-2">{e.text}</p>
                    )}
                  </li>
                );
              })}
            </ol>
            {data.signals.some((s: any) => s.feedback === "dismissed") && (
              <p className="mt-3 text-xs text-ink-3">
                Dismissed:{" "}
                {data.signals.filter((s: any) => s.feedback === "dismissed").map((s: any) => (
                  <button key={s.id} className="mr-2 underline" onClick={() => feedback(s.id, "open")}>
                    {client.pack.signals[s.signal_type].label} (restore)
                  </button>
                ))}
              </p>
            )}
          </Panel>

          <Panel title={`Conversations (${data.conversations.length})`}>
            <ul className="divide-y divide-line">
              {data.conversations.map((cv: any) => (
                <li key={cv.id} className="py-2">
                  <button className="flex w-full items-center justify-between text-left text-sm" onClick={() => setOpenConv(openConv === cv.id ? null : cv.id)} aria-expanded={openConv === cv.id}>
                    <span className="flex items-center gap-2 font-medium"><Phone size={14} className="text-ink-3" /> {cv.title}</span>
                    <span className="num text-xs text-ink-3">{cv.date}</span>
                  </button>
                  {openConv === cv.id && <Transcript text={cv.transcript} quotes={quotes} />}
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <div className="space-y-5">
          <Panel title="Drafted next steps">
            <div className="space-y-2.5">
              {data.actions.length === 0 && <p className="text-sm text-ink-3">No steps drafted. This {v.account.toLowerCase()} looks healthy.</p>}
              {data.actions.map((ac: any) => <ActionCard key={ac.id} action={ac} compact />)}
            </div>
          </Panel>

          <Panel title="Why this score" aside={<span className="num text-sm font-semibold">{sc.score} / 100</span>}>
            <ul className="space-y-3">
              {sc.components.map((p: any) => (
                <li key={p.label}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-ink-2">{p.label}</span>
                    <span className="num font-semibold">{p.points} <span className="font-normal text-ink-3">of {p.max}</span></span>
                  </div>
                  <div className="h-1.5 rounded-full bg-line">
                    <div className="h-full rounded-full bg-act" style={{ width: `${(p.points / p.max) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title={v.activity} aside={<span className="num text-sm font-semibold" style={{ color: tone }}>{pct(sc.activity_pct)}</span>}>
            <div className="h-36">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chart} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                  <XAxis dataKey="day" tickFormatter={(d) => shortDate(d)} tick={{ fontSize: 11, fill: "#8A92A0" }} interval={29} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#8A92A0" }} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(val: any) => Math.round(val * 10) / 10} labelFormatter={(d) => shortDate(d)} />
                  <Area dataKey="value" stroke="none" fill={tone} fillOpacity={0.08} isAnimationActive={false} />
                  <Area dataKey="avg" stroke={tone} strokeWidth={2} fill="none" isAnimationActive={false} connectNulls />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-xs text-ink-3">Line: 7-day average. Change compares the last 14 days with the earlier baseline.</p>
          </Panel>

          <Panel title="Timeline">
            <ol className="relative space-y-3 border-l border-line pl-4">
              {data.timeline.map((t: any, i: number) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[1.42rem] top-1 grid size-3 place-items-center rounded-full border border-line bg-panel">
                    {t.kind === "renewal" ? <CalendarClock size={9} /> : t.kind === "capacity" ? <Minus size={9} /> : null}
                  </span>
                  <p className="num text-xs text-ink-3">{shortDate(t.date)}</p>
                  <p className="text-sm font-medium">{t.title}</p>
                  {t.signals?.length > 0 && <p className="text-xs text-high">{t.signals.join(", ")}</p>}
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function FeedbackTag({ label, onUndo }: { label: string; onUndo: () => void }) {
  return (
    <span className="flex items-center gap-2 rounded-md bg-low-soft px-2 py-1 text-xs font-medium text-low">
      <Check size={13} /> {label}
      <button className="underline" onClick={onUndo}>Undo</button>
    </span>
  );
}

export function Transcript({ text, quotes }: { text: string; quotes: string[] }) {
  return (
    <div className="mt-3 space-y-1.5 rounded-lg bg-paper p-3 text-sm leading-relaxed">
      {text.split("\n").filter(Boolean).map((line, i) => {
        const m = line.match(/^(.+?) \((.+?)\):\s*(.*)$/);
        const speaker = m ? m[1] : "";
        const body = m ? m[3] : line;
        const q = quotes.find((x) => body.includes(x));
        const staff = m ? /CSM|Account manager/.test(m[2]) : false;
        return (
          <p key={i} className={staff ? "text-ink-3" : "text-ink"}>
            {speaker && <span className="font-semibold">{speaker}: </span>}
            {q ? (
              <>
                {body.slice(0, body.indexOf(q))}
                <span className="mark">{q}</span>
                {body.slice(body.indexOf(q) + q.length)}
              </>
            ) : body}
          </p>
        );
      })}
    </div>
  );
}
