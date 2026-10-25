import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { CalendarCheck, Rows3, PieChart, ShieldCheck, AudioLines, Radar } from "lucide-react";
import { useApp, useClient } from "../context";

const NAV = [
  { to: "week", label: "My week", icon: CalendarCheck },
  { to: "renewals", label: "All renewals", icon: Rows3 },
  { to: "portfolio", label: "Portfolio", icon: PieChart },
  { to: "trust", label: "Accuracy", icon: ShieldCheck },
  { to: "analyze", label: "Analyze a call", icon: AudioLines },
];

export function Shell() {
  const { clientId } = useParams();
  const { clients, health } = useApp();
  const client = useClient(clientId);
  const nav = useNavigate();

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col gap-6 border-b border-line bg-panel px-4 py-5 md:sticky md:top-0 md:h-screen md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-2">
          <span className="grid size-8 place-items-center rounded-lg bg-ink text-mark">
            <Radar size={18} />
          </span>
          <span className="text-[1.05rem] font-bold tracking-tight">Renewal Radar</span>
        </div>

        <label className="block px-2">
          <span className="text-xs text-ink-3">Workspace</span>
          <select
            className="mt-1 w-full rounded-lg border border-line bg-paper px-2.5 py-2 text-sm font-medium"
            value={clientId}
            onChange={(e) => nav(`/${e.target.value}/week`)}
          >
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {client && <span className="mt-1 block text-xs text-ink-3">{client.pack.name} pack</span>}
        </label>

        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={`/${clientId}/${to}`}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium ${isActive ? "bg-ink text-white" : "text-ink-2 hover:bg-paper hover:text-ink"}`
              }
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto hidden space-y-1 px-2 text-xs text-ink-3 md:block">
          {client && (
            <p>
              Signed in as <span className="font-medium text-ink-2">{client.user_name}</span>, {client.pack.vocabulary.owner_role}
            </p>
          )}
          <p>
            AI: <span className="font-medium text-ink-2">{health?.model ?? "…"}</span>
          </p>
          <p>Synthetic demo data. Every company and person is fictional.</p>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
        <div className="mx-auto max-w-[1180px]">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
