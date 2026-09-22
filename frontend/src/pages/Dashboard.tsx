import React from "react";
import { api, type Dashboard as DashboardData } from "../lib/api";
import { Card, ErrorBox, Spinner, StatTile, StatusBadge, Table, Td, useAsync } from "../lib/ui";

export function Dashboard() {
  const { data, error, loading, refetch } = useAsync<DashboardData>(
    () => api.get("/dashboard"),
    [],
  );

  React.useEffect(() => {
    const id = setInterval(refetch, 15000);
    return () => clearInterval(id);
  }, [refetch]);

  if (loading && !data) return <Spinner label="Loading dashboard…" />;
  if (error && !data) return <ErrorBox message={error} />;
  if (!data) return null;

  const t = data.totals;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Sites" value={`${t.sites_reachable}/${t.sites}`} sub="reachable" />
        <StatTile label="Servers" value={`${t.servers_online}/${t.servers_total}`} sub="online" />
        <StatTile label="Users" value={t.users_total} sub="across all sites" />
        <StatTile label="Sessions" value={t.active_sessions} sub="active now" />
        <StatTile label="Clients" value={t.online_clients} sub="connected (load)" />
      </div>

      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Sites</h2>
          <span className="text-xs text-slate-500">
            updated {new Date(data.generated_at).toLocaleTimeString()}
          </span>
        </div>
        <Table head={["Region", "Site", "Status", "Servers", "Users", "Sessions", "Latency", "Note"]}>
          {data.sites.map((s) => (
            <tr key={s.node_id} className="text-slate-300">
              <Td className="text-slate-400">{s.region}</Td>
              <Td className="font-medium text-slate-100">{s.name}</Td>
              <Td>
                <StatusBadge status={s.status} />
              </Td>
              <Td className="font-mono">
                {s.servers_online}/{s.servers_total}
              </Td>
              <Td className="font-mono">
                {s.users_total}
                {s.users_disabled > 0 && (
                  <span className="ml-1 text-xs text-amber-400">({s.users_disabled} off)</span>
                )}
              </Td>
              <Td className="font-mono">{s.active_sessions}</Td>
              <Td className="font-mono text-slate-400">
                {s.last_latency_ms != null ? `${s.last_latency_ms}ms` : "—"}
              </Td>
              <Td className="max-w-[220px] truncate text-xs text-red-400" >{s.error ?? ""}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
