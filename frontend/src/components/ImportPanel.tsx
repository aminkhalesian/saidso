import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileUp, Trash2, Upload } from "lucide-react";
import { api } from "../api";
import { Button, Chip, Panel, RiskPill } from "./ui";

const STATUS: Record<string, { label: string; tone?: "high" | "low" }> = {
  added: { label: "Added", tone: "low" },
  updated: { label: "Flags added" },
  skipped: { label: "Skipped", tone: "high" },
};

export function ImportPanel({ clientId, customers }: { clientId: string; customers: string }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState("");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [removed, setRemoved] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function template() {
    const { csv } = await api.importTemplate(clientId);
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "saidso-import-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function pick(f?: File) {
    if (!f) return;
    setText(await f.text());
    setFile(f.name);
    setResult(null);
    setErr(null);
    setRemoved(null);
  }

  async function run() {
    if (!text.trim()) return setErr("Choose a CSV file or paste its contents first.");
    setBusy(true);
    setErr(null);
    setRemoved(null);
    try {
      setResult(await api.importCsv(clientId, text));
    } catch (e: any) {
      setResult(null);
      setErr(e.message.replace(/^\d+:\s*/, "").replace(/^\{"detail":"(.*)"\}$/, "$1"));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    const r = await api.undoImport(clientId);
    setResult(null);
    setRemoved(`Removed ${r.customers_removed} ${customers} and ${r.calls_removed} imported calls.`);
  }

  const s = result?.summary;
  return (
    <Panel
      title="Import customers from a CSV"
      aside={<Button variant="ghost" onClick={template}><Download size={15} /> Download a template</Button>}
      className="mt-5"
    >
      <p className="mb-3 max-w-[70ch] text-[13px] leading-relaxed text-ink-2">
        One row per {customers.replace(/s$/, "")}. Only the name is required. Put what the customer said on a call in <b>call_notes</b>, and the AI flags risks only where it can quote them word for word.
        Dates, numbers and column names are tidied up, and every fix is listed below. Rows that match an existing {customers.replace(/s$/, "")} add flags to it.
      </p>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div>
          <input ref={input} type="file" accept=".csv,text/csv,text/plain" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => input.current?.click()}><FileUp size={15} /> Choose CSV file</Button>
            {file && <span className="truncate text-xs text-ink-3">{file}</span>}
          </div>
          <textarea
            value={text}
            onChange={(e) => { setText(e.target.value); setFile(""); setErr(null); }}
            placeholder="…or paste the CSV here, for example from another AI tool"
            className="h-40 w-full rounded-[10px] border border-line-2 bg-panel p-3 font-mono text-xs leading-relaxed"
            aria-label="CSV contents"
          />
          {err && <p className="mt-2 text-sm text-high" role="alert">{err}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button onClick={run} disabled={busy}><Upload size={15} /> {busy ? "Reading the file…" : "Import and score"}</Button>
            <Button variant="ghost" onClick={undo}><Trash2 size={15} /> Remove imported</Button>
          </div>
          {busy && <p className="mt-2 text-sm text-ink-2" role="status">The AI is reading each customer's call notes and writing a brief. With a real AI key this can take one to two minutes for a dozen customers. Keep this page open.</p>}
          {removed && <p className="mt-2 text-sm text-low">{removed}</p>}
        </div>

        <div className="min-w-0">
          {!result ? (
            <p className="text-sm text-ink-3">The result appears here: who was added, which flags were found, and where each {customers.replace(/s$/, "")} lands.</p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                <Chip tone="low">{s.added} added</Chip>
                {s.updated > 0 && <Chip>{s.updated} updated</Chip>}
                {s.skipped > 0 && <Chip tone="high">{s.skipped} skipped</Chip>}
                <Chip>{s.flags} flags</Chip>
                <span className="mx-1 text-ink-3">See them in</span>
                <Link className="font-semibold text-act hover:underline" to={`/${clientId}/week`}>Dashboard</Link>
                <Link className="font-semibold text-act hover:underline" to={`/${clientId}/renewals`}>All renewals</Link>
              </div>
              {result.notes.length > 0 && <p className="mb-2 text-xs text-ink-2">File: {result.notes.join("; ")}.</p>}
              <ul className="divide-y divide-line rounded-[10px] border border-line">
                {result.rows.map((r: any) => (
                  <li key={r.row} className="px-3.5 py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{r.customer || `Row ${r.row}`}</span>
                      <Chip tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Chip>
                      {r.band && <RiskPill band={r.band} score={r.score} />}
                      {r.days_to_renewal != null && r.status !== "skipped" && <span className="text-xs text-ink-3">renews in {r.days_to_renewal} days</span>}
                    </div>
                    {r.status !== "skipped" && (
                      <p className="mt-1 text-[13px] text-ink-2">
                        {r.signals?.length ? <>Flags: {r.signals.join(", ")}{r.found_by ? ` (found by ${r.found_by})` : ""}.</> : "No flags found."}{" "}
                        {r.in_renewals === false ? "Renews outside the 90-day view, so it is not listed. " : r.on_dashboard ? "On the Dashboard. " : r.in_renewals ? "In All renewals. " : ""}
                      </p>
                    )}
                    {r.reason && <p className="mt-1 text-[13px] text-high">{r.reason}.</p>}
                    {r.fixes?.length > 0 && <p className="mt-1 text-xs text-ink-3">{r.fixes.join(" · ")}</p>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}
