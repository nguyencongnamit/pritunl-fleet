import React from "react";
import { api, ApiError, type ScopedServer } from "../lib/api";
import { Badge, Button, Card, ErrorBox, Spinner, Table, Td, useAsync } from "../lib/ui";

export function Servers() {
  const { data, error, loading, refetch } = useAsync<ScopedServer[]>(() => api.get("/servers"), []);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  async function act(node_id: string, server_id: string, action: string) {
    const key = `${node_id}:${server_id}`;
    setBusy(key);
    setErr(null);
    try {
      await api.post(`/nodes/${node_id}/servers/${server_id}/action`, { action });
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-slate-200">Servers across all sites</h2>
      {err && <ErrorBox message={err} />}
      <Card className="p-4">
        {loading && !data ? (
          <Spinner />
        ) : error ? (
          <ErrorBox message={error} />
        ) : (
          <Table head={["Site", "Server", "Proto", "Port", "Status", "Clients", "Actions"]}>
            {(data ?? []).map((s) => {
              const key = `${s.node_id}:${s.id}`;
              const b = busy === key;
              const online = s.status === "online";
              return (
                <tr key={key} className="text-slate-300">
                  <Td>{s.node_name} <span className="text-slate-500">· {s.region}</span></Td>
                  <Td className="font-medium text-slate-100">{s.name}</Td>
                  <Td className="uppercase text-slate-400">{s.protocol}</Td>
                  <Td className="font-mono text-slate-400">{s.port ?? "—"}</Td>
                  <Td>{online ? <Badge tone="blue">online</Badge> : <Badge tone="red">offline</Badge>}</Td>
                  <Td className="font-mono">{s.online_clients}</Td>
                  <Td>
                    <div className="flex gap-1.5">
                      <Button size="sm" variant="ghost" disabled={b || online} onClick={() => act(s.node_id, s.id, "start")}>Start</Button>
                      <Button size="sm" variant="ghost" disabled={b || !online} onClick={() => act(s.node_id, s.id, "stop")}>Stop</Button>
                      <Button size="sm" variant="ghost" disabled={b} onClick={() => act(s.node_id, s.id, "restart")}>Restart</Button>
                    </div>
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>
    </div>
  );
}
