import { useState } from "react";
import { Check, ListTodo, Mail, CalendarDays, Pencil, X, Undo2 } from "lucide-react";
import { api } from "../api";
import { Button } from "./ui";

const KIND = {
  email: { icon: Mail, label: "Email draft" },
  task: { icon: ListTodo, label: "Task" },
  meeting: { icon: CalendarDays, label: "Meeting" },
} as const;

export function ActionCard({ action, compact = false, onChange }: { action: any; compact?: boolean; onChange?: (a: any) => void }) {
  const [a, setA] = useState(action);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(action.body);
  const [open, setOpen] = useState(!compact);
  const [busy, setBusy] = useState(false);
  const kind = KIND[a.kind as keyof typeof KIND] ?? KIND.task;
  const Icon = kind.icon;

  async function decide(status: "approved" | "dismissed" | "draft") {
    setBusy(true);
    try {
      const updated = await api.decide(a.id, status, editing ? draft : undefined);
      setA(updated);
      setEditing(false);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  }

  if (a.status !== "draft") {
    return (
      <div className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm ${a.status === "approved" ? "bg-low-soft text-low" : "bg-paper text-ink-3"}`}>
        <span className="flex items-center gap-2">
          {a.status === "approved" ? <Check size={16} /> : <X size={16} />}
          {a.status === "approved" ? "Approved" : "Dismissed"}: {a.title}
        </span>
        <button className="flex items-center gap-1 text-xs font-medium hover:underline" onClick={() => decide("draft")} disabled={busy}>
          <Undo2 size={13} /> Undo
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-line bg-panel">
      <div className="flex items-start gap-3 px-3.5 pt-3">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-act-soft text-act" title={kind.label}>
          <Icon size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-snug">{a.title}</p>
          <p className="text-xs text-ink-3">
            {kind.label}
            {a.source === "llm" ? ", tailored by AI" : ""}
            {compact && (
              <button className="ml-2 font-medium text-act hover:underline" onClick={() => setOpen(!open)}>
                {open ? "Hide" : "Preview"}
              </button>
            )}
          </p>
        </div>
      </div>
      {open && (
        <div className="px-3.5 pt-2.5">
          {editing ? (
            <textarea
              className="h-40 w-full rounded-md border border-line bg-paper p-2.5 text-sm leading-relaxed"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label="Edit draft"
            />
          ) : (
            <p className="whitespace-pre-line rounded-md bg-paper p-2.5 text-sm leading-relaxed text-ink-2">{a.body}</p>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-1.5 px-3.5 py-3">
        <Button onClick={() => decide("approved")} disabled={busy}>
          <Check size={15} /> {editing ? "Save and approve" : "Approve"}
        </Button>
        {!editing && (
          <Button variant="outline" onClick={() => { setEditing(true); setOpen(true); }} disabled={busy}>
            <Pencil size={14} /> Edit
          </Button>
        )}
        <Button variant="ghost" onClick={() => decide("dismissed")} disabled={busy}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
