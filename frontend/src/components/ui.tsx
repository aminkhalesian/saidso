import { ReactNode } from "react";
import { Band } from "../api";

const BAND_STYLE: Record<Band, string> = {
  high: "bg-high-soft text-high",
  medium: "bg-med-soft text-med",
  low: "bg-low-soft text-low",
};
const BAND_LABEL: Record<Band, string> = { high: "High risk", medium: "Watch", low: "Healthy" };
export const BAND_FILL: Record<Band, string> = { high: "#E5534B", medium: "#F2B544", low: "#2FA67C" };

export function RiskPill({ band, score }: { band: Band; score?: number }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${BAND_STYLE[band]}`}>
      {BAND_LABEL[band]}
      {score !== undefined && <span className="num opacity-80">{score}</span>}
    </span>
  );
}

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "high" | "low" | "med" }) {
  const t = { neutral: "bg-paper-2 text-ink", high: "bg-high-soft text-high", low: "bg-low-soft text-low", med: "bg-med-soft text-med" }[tone];
  return <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${t}`}>{children}</span>;
}

/** Circular score: ring fill = score/100, colour = band */
export function ScoreRing({ score, band, size = 42 }: { score: number; band: Band; size?: number }) {
  const r = size / 2 - 3;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`Risk score ${score} of 100`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E8EAEE" strokeWidth="4" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={BAND_FILL[band]} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${(score / 100) * c} ${c}`} />
      </svg>
      <span className={`num absolute inset-0 grid place-items-center text-[13px] font-bold ${band === "high" ? "text-high" : band === "medium" ? "text-med" : "text-low"}`}>{score}</span>
    </div>
  );
}

export function RiskBar({ score, band }: { score: number; band: Band }) {
  return (
    <div className="flex items-center gap-2" aria-label={`Risk score ${score} of 100`}>
      <div className="h-1.5 w-20 rounded-full bg-paper-2">
        <div className="h-full rounded-full" style={{ width: `${score}%`, background: BAND_FILL[band] }} />
      </div>
      <span className="num w-6 text-right text-sm font-semibold">{score}</span>
    </div>
  );
}

export function Initials({ name, size = 38 }: { name: string; size?: number }) {
  const t = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <span className="grid shrink-0 place-items-center rounded-[10px] border border-line-2 bg-paper-2 text-xs font-bold text-act" style={{ width: size, height: size }}>
      {t}
    </span>
  );
}

export function Quote({ text, speaker, meta, size = "md" }: { text: string; speaker?: string; meta?: string; size?: "md" | "lg" }) {
  return (
    <figure>
      <blockquote className={`quote border-l-[3px] border-brass pl-3.5 leading-snug text-ink ${size === "lg" ? "text-[1.2rem]" : "text-[1.02rem]"}`}>
        “<span className="mark">{text}</span>”
      </blockquote>
      {(speaker || meta) && (
        <figcaption className="mt-1.5 pl-[17px] text-xs text-ink-2">
          {speaker && <span className="font-medium text-ink">{speaker}</span>}
          {speaker && meta && " · "}
          {meta}
        </figcaption>
      )}
    </figure>
  );
}

export function Cite({ id, onClick }: { id: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} className="ml-1 inline-flex -translate-y-px items-center rounded bg-act px-1.5 text-[0.68rem] font-bold leading-[1.15rem] text-white hover:bg-act-deep" title={`Show evidence ${id}`}>
      {id}
    </button>
  );
}

export function Panel({ title, children, aside, className = "" }: { title?: string; children: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <section className={`rounded-[14px] border border-line bg-panel p-5 shadow-card ${className}`}>
      {(title || aside) && (
        <div className="mb-4 flex items-baseline justify-between gap-4">
          {title && <h2 className="text-base font-bold tracking-tight">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ icon, label, value, chip, tone = "neutral" }: { icon: ReactNode; label: string; value: ReactNode; chip?: ReactNode; tone?: "neutral" | "high" | "low" }) {
  const t = { neutral: "bg-paper-2 text-act", high: "bg-high-soft text-high", low: "bg-low-soft text-low" }[tone];
  return (
    <div className="flex items-center gap-4 px-5 py-5">
      <span className={`grid size-11 shrink-0 place-items-center rounded-xl ${t}`}>{icon}</span>
      <div className="min-w-0">
        <p className="text-[13px] text-ink-2">{label}</p>
        <p className="num flex flex-wrap items-center gap-x-2 text-[1.6rem] font-bold leading-tight tracking-tight">
          {value}
          {chip}
        </p>
      </div>
    </div>
  );
}

export function KpiStrip({ children }: { children: ReactNode }) {
  return (
    <section className="mb-5 grid rounded-[14px] border border-line bg-panel shadow-card sm:grid-cols-2 lg:grid-cols-4 [&>*]:border-line max-lg:[&>*:nth-child(n+3)]:border-t max-sm:[&>*+*]:border-t lg:[&>*+*]:border-l sm:max-lg:[&>*:nth-child(even)]:border-l">
      {children}
    </section>
  );
}

export function PageHead({ title, sub, aside }: { title: string; sub?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[1.65rem] font-bold leading-tight tracking-tight">{title}</h1>
        {sub && <p className="mt-0.5 text-[13px] text-ink-2">{sub}</p>}
      </div>
      {aside}
    </header>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-full border border-line bg-panel p-[3px]" role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${o.value === value ? "bg-act text-white" : "text-ink-2 hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Button({ children, variant = "primary", ...p }: any) {
  const styles: Record<string, string> = {
    primary: "bg-act text-white hover:bg-act-deep",
    ghost: "text-ink-2 hover:bg-paper-2 hover:text-ink",
    outline: "border border-line-2 bg-panel text-ink hover:bg-paper",
  };
  return (
    <button {...p} className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-semibold transition-colors disabled:opacity-50 ${styles[variant]} ${p.className ?? ""}`}>
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
