import { useParams } from "react-router-dom";
import { api } from "../api";
import { useAsync, useClient } from "../context";
import { Outlook } from "../components/Outlook";
import { ErrorNote, Loading, PageHead } from "../components/ui";

export function Retention() {
  const { clientId = "" } = useParams();
  const client = useClient(clientId);
  const { data, error } = useAsync(() => api.overview(clientId), [clientId]);
  if (error) return <ErrorNote error={error} />;
  if (!data || !client) return <Loading />;
  return (
    <div className="reveal">
      <PageHead title="Retention outlook" sub={`${data.client.user_name} · ${data.kpis.renewals} renewals in the next 90 days`} />
      <Outlook o={data.outlook} />
    </div>
  );
}
