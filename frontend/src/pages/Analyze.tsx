import { useState } from "react";
import { useParams } from "react-router-dom";
import { FileText, Sparkles } from "lucide-react";
import { api } from "../api";
import { useClient } from "../context";
import { Button, PageHead, Panel, Quote } from "../components/ui";
import { Transcript } from "./Account";

export function Analyze() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const [text, setText] = useState("");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!client) return null;
  const v = client.pack.vocabulary;

  async function run() {
    if (!text.trim()) {
      setErr("Paste a transcript or load the sample call first.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      setResult(await api.analyze(clientId, text));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sample() {
    const s = await api.sample(clientId);
    setText(s.transcript);
    setResult(null);
    setErr(null);
  }

  return (
    <div className="reveal">
      <PageHead
        title="Analyze a call"
        sub={`Paste a conversation with a ${v.account.toLowerCase()}. The AI flags renewal risks and shows the exact sentence behind each one. Anything it can't quote word for word gets thrown out.`}
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Transcript" aside={<Button variant="ghost" onClick={sample}><FileText size={15} /> Load a sample call</Button>}>
          <textarea
            value={text}
            onChange={(e) => { setText(e.target.value); setErr(null); }}
            placeholder={`One turn per line, for example:\nPriya Raman (Operations Lead, Northwind): We're reviewing our tools next quarter.`}
            className="h-80 w-full rounded-[10px] border border-line-2 bg-panel p-3 font-[inherit] text-sm leading-relaxed"
            aria-label="Transcript"
          />
          {err && <p className="mt-2 text-sm text-high">{err}</p>}
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={run} disabled={busy}>
              <Sparkles size={15} /> {busy ? "Finding risk signals" : "Find risk signals"}
            </Button>
            <span className="text-xs text-ink-3">Uses the {client.pack.name.toLowerCase()} pack</span>
          </div>
        </Panel>

        <Panel title="What it found" aside={result && <span className="text-xs text-ink-3">{result.source === "llm" ? "Found by AI" : "Offline keyword baseline"}</span>}>
          {!result ? (
            <p className="text-sm text-ink-3">Results appear here. Try the sample call: it contains two real risks and one decoy.</p>
          ) : result.signals.length === 0 ? (
            <p className="text-sm text-ink-2">No renewal risks in this conversation.</p>
          ) : (
            <ul className="space-y-4">
              {result.signals.map((s: any, i: number) => (
                <li key={i} className="rounded-xl border border-line bg-paper p-4">
                  <p className="mb-2 flex items-center justify-between text-sm font-semibold">
                    {s.label}
                    <span className="num text-xs font-normal text-ink-3">confidence {Math.round(s.confidence * 100)}%</span>
                  </p>
                  <Quote text={s.quote} speaker={s.speaker} />
                  <p className="mt-2.5 text-xs text-ink-2">Suggested step: {s.playbook}</p>
                </li>
              ))}
            </ul>
          )}
          {result && <Transcript text={text} quotes={result.signals.map((s: any) => s.quote)} />}
        </Panel>
      </div>
    </div>
  );
}
