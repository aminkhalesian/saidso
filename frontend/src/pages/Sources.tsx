import { useParams } from "react-router-dom";
import { Activity, LifeBuoy, Phone, Receipt } from "lucide-react";
import { api } from "../api";
import { useAsync, useClient } from "../context";
import { Chip, ErrorNote, Loading, PageHead, Panel } from "../components/ui";

const ICON: Record<string, any> = { usage: Activity, conversations: Phone, support: LifeBuoy, commercial: Receipt };

export function Sources() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error } = useAsync(() => api.sources(clientId), [clientId]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;

  return (
    <div className="reveal">
      <PageHead title="Data sources" sub={<>What saidso reads from {client.name === "Brightdesk" ? "a SaaS company's" : "an agency's"} systems, and how each one connects.</>} />
      <p className="-mt-2 mb-5 max-w-3xl text-sm text-ink-2">
        saidso only reads. It never writes to your tools. Every next step is a draft that a person approves. Today it reads files you export;
        live connectors come after the pilot.
      </p>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 md:grid-cols-2">
        {data.sources.map((s: any) => {
          const Icon = ICON[s.key];
          return (
            <Panel key={s.key}>
              <div className="mb-3 flex items-start justify-between gap-3">
                <h2 className="flex items-center gap-2.5 text-base font-bold tracking-tight">
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-act-soft text-act"><Icon size={17} strokeWidth={1.9} /></span>
                  {s.title}
                </h2>
                <Chip tone={data.demo ? "med" : "low"}>{s.status}</Chip>
              </div>
              <div className="mb-4 flex flex-wrap gap-1.5">
                {s.provides.map((p: string) => <Chip key={p}>{p}</Chip>)}
              </div>
              <dl className="space-y-2.5 text-sm">
                <Line k="Typical systems" v={s.systems} />
                <Line k="Today" v={s.today} />
                <Line k="Next" v={s.next} />
                <Line k="In this workspace" v={s.counts.join(" · ")} />
              </dl>
            </Panel>
          );
        })}
      </div>

      <Panel title="The pilot data pack" className="mt-5" aside={<span className="text-xs text-ink-3">Eight files. Anything missing just stays empty.</span>}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-[0.08em] text-ink-3">
                <th className="py-2 font-medium">File</th>
                <th className="py-2 font-medium">What it holds</th>
                <th className="py-2 font-medium">Columns</th>
              </tr>
            </thead>
            <tbody>
              {data.files.map((f: any) => (
                <tr key={f.file} className="border-b border-line align-top last:border-0">
                  <td className="num py-2.5 pr-4 font-medium">{f.file}</td>
                  <td className="py-2.5 pr-4 text-ink-2">{f.holds}</td>
                  <td className="py-2.5 text-xs text-ink-3">{f.columns}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 max-w-3xl text-sm text-ink-2">
          Customers are matched across files by name, even when billing names are messy ("WEISSDORN INSURANCE GMBH" and "Weißdorn Insurance" become one
          customer). Real customer data is only used with the customer's permission and a data processing agreement. This demo runs on synthetic data only.
        </p>
      </Panel>
    </div>
  );
}

function Line({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3">
      <dt className="text-ink-3">{k}</dt>
      <dd className="min-w-0">{v}</dd>
    </div>
  );
}
