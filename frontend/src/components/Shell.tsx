import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { CalendarCheck, Rows3, PieChart, ShieldCheck, AudioLines, Database, Gauge } from "lucide-react";
import { useApp, useClient } from "../context";

const NAV = [
  { to: "week", label: "Dashboard", icon: CalendarCheck },
  { to: "renewals", label: "All renewals", icon: Rows3 },
  { to: "retention", label: "Retention outlook", icon: Gauge },
  { to: "portfolio", label: "Portfolio", icon: PieChart },
  { to: "sources", label: "Data sources", icon: Database },
  { to: "trust", label: "Accuracy", icon: ShieldCheck },
  { to: "analyze", label: "Analyze a call", icon: AudioLines },
];

function Mark() {
  return (
    <svg width="30" height="30" viewBox="322 215 380 380" role="img" aria-label="saidso">
      <path d="M322 595V405A190 190 0 0 1 512 215A190 190 0 0 1 702 405A190 190 0 0 1 512 595Z" fill="#1E3A5F" />
      <circle cx="512" cy="405" r="46" fill="#F3F4F6" />
    </svg>
  );
}

export function Shell() {
  const { clientId } = useParams();
  const { clients, health } = useApp();
  const client = useClient(clientId);
  const nav = useNavigate();
  const initials = (client?.user_name ?? "").split(" ").map((w: string) => w[0]).slice(0, 2).join("");

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <aside className="flex shrink-0 items-center gap-1.5 overflow-x-auto border-b border-line bg-paper px-3 py-2.5 md:sticky md:top-0 md:h-screen md:w-[76px] md:flex-col md:justify-start md:overflow-visible md:border-b-0 md:border-r md:px-0 md:py-5">
        <span className="mr-2 md:mb-5 md:mr-0">
          <Mark />
        </span>
        <nav className="flex gap-1.5 md:flex-col" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={`/${clientId}/${to}`}
              aria-label={label}
              className={({ isActive }) =>
                `group relative grid size-11 shrink-0 place-items-center rounded-xl ${isActive ? "bg-act text-white" : "text-ink-2 hover:bg-paper-2 hover:text-ink"}`
              }
            >
              <Icon size={20} strokeWidth={1.8} />
              <span className="pointer-events-none absolute left-[54px] z-20 hidden whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs text-paper opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 md:block">
                {label}
              </span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1360px] px-4 pb-14 pt-5 md:px-10 md:pt-7">
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 rounded-full border border-line bg-panel py-1.5 pl-3.5 pr-2 text-[13px] text-ink-2">
              Workspace
              <select
                className="rounded-full bg-transparent py-0.5 pr-1 text-[13px] font-semibold text-ink"
                value={clientId}
                onChange={(e) => nav(`/${e.target.value}/week`)}
              >
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            {client && <span className="hidden text-[13px] text-ink-3 sm:inline">{client.pack.name}</span>}
            <span className="flex-1" />
            <span className="hidden text-xs text-ink-3 lg:inline">AI: {health?.model ?? "…"} · Synthetic demo data, every company and person is fictional</span>
            <span
              className="grid size-[38px] place-items-center rounded-full border border-line-2 bg-paper-2 text-[13px] font-semibold text-act"
              title={client ? `${client.user_name}, ${client.pack.vocabulary.owner_role}` : ""}
            >
              {initials}
            </span>
          </div>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
