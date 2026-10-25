import { useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

export type SortKey = "score" | "days";
type Dir = "asc" | "desc";
const DEFAULT_DIR: Record<SortKey, Dir> = { score: "desc", days: "asc" };   // highest risk first, soonest renewal first

/** Sort state for lists of customers. Clicking the active column flips the direction; a new column starts at its natural order. */
export function useSort(initial: SortKey = "score") {
  const [sort, setSort] = useState<{ key: SortKey; dir: Dir }>({ key: initial, dir: DEFAULT_DIR[initial] });
  const toggle = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: DEFAULT_DIR[key] }));
  const apply = <T extends { score: number; days_to_renewal: number }>(rows: T[]): T[] => {
    const sign = sort.dir === "asc" ? 1 : -1;
    const val = (r: T) => (sort.key === "score" ? r.score : r.days_to_renewal);
    const other = (r: T) => (sort.key === "score" ? r.days_to_renewal : -r.score);      // ties: the other measure decides
    return [...rows].sort((a, b) => sign * (val(a) - val(b)) || other(a) - other(b));
  };
  return { sort, toggle, apply };
}

export function SortHead({ label, k, sort, onToggle, className = "" }: {
  label: string; k: SortKey; sort: { key: SortKey; dir: Dir }; onToggle: (k: SortKey) => void; className?: string;
}) {
  const active = sort.key === k;
  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <span role="columnheader" aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"} className={className}>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggle(k); }}
        className={`inline-flex items-center gap-1 uppercase tracking-[inherit] hover:text-ink ${active ? "text-ink" : ""}`}
        title={`Sort by ${label.toLowerCase()}`}
      >
        {label}
        <Icon size={12} aria-hidden />
      </button>
    </span>
  );
}
