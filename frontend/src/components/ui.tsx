import { ReactNode } from "react";
import { Band } from "../api";

const BAND_STYLE: Record<Band, string> = {
  high: "bg-high-soft text-high",
  medium: "bg-med-soft text-med",
  low: "bg-low-soft text-low",
};
const BAND_LABEL: Record<Band, string> = { high: "High risk", medium: "Watch", low: "Healthy" };

export function RiskPill({ band, score }: { band: Band; score?: number }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${BAND_STYLE[band]}`}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {BAND_LABEL[band]}
      {score !== undefined && <span className="num opacity-80">{score}</span>}
    </span>
  );
}

export function RiskBar({ score, band }: { score: number; band: Band }) {
  const color = band === "high" ? "bg-high" : band === "medium" ? "bg-med" : "bg-low";
  return (
    <div className="flex items-center gap-2" aria-label={`Risk score ${score} of 100`}>
      <div className="h-1.5 w-20 rounded-full bg-line">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="num w-6 text-right text-sm font-semibold">{score}</span>
    </div>
  );
}

export function Quote({ text, speaker, meta, size = "md" }: { text: string; speaker?: string; meta?: string; size?: "md" | "lg" }) {
  return (
    <figure>
      <blockquote className={`quote leading-snug text-ink ${size === "lg" ? "text-[1.35rem]" : "text-[1.08rem]"}`}>
        <span className="mark">“{text}”</span>
      </blockquote>
      {(speaker || meta) && (
        <figcaption className="mt-1.5 text-xs text-ink-3">
          {speaker && <span className="font-medium text-ink-2">{speaker}</span>}
          {speaker && meta && ", "}
          {meta}
        </figcaption>
      )}
    </figure>
  );
}

export function Cite({ id, onClick }: { id: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="ml-1 inline-flex -translate-y-px items-center rounded bg-act px-1.5 text-[0.68rem] font-bold leading-[1.15rem] text-white hover:bg-ink"
      title={`Show evidence ${id}`}
    >
      {id}
    </button>
  );
}

export function Panel({ title, children, aside, className = "" }: { title?: string; children: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-line bg-panel p-5 ${className}`}>
      {(title || aside) && (
        <div className="mb-4 flex items-baseline justify-between gap-4">
          {title && <h2 className="text-[0.95rem] font-semibold">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function Button({ children, variant = "primary", ...p }: any) {
  const styles: Record<string, string> = {
    primary: "bg-act text-white hover:bg-ink",
    ghost: "text-ink-2 hover:bg-paper hover:text-ink",
    outline: "border border-line bg-panel text-ink hover:border-ink-3",
  };
  return (
    <button
      {...p}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${styles[variant]} ${p.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="py-20 text-center text-sm text-ink-3">{label}…</div>;
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-high/30 bg-high-soft px-4 py-3 text-sm text-high">
      Couldn't load this view: {error}. Check that the backend is running on port 8000.
    </div>
  );
}
