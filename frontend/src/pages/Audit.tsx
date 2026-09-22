import React from "react";
import { api, type AuditEntry, type ChainStatus } from "../lib/api";
import { Badge, Card, ErrorBox, Spinner, Table, Td, useAsync } from "../lib/ui";

export function Audit() {
  const entries = useAsync<AuditEntry[]>(() => api.get("/audit?limit=200"), []);
  const chain = useAsync<ChainStatus>(() => api.get("/audit/verify"), []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Audit log</h2>
        {chain.data && (
          <div className="text-sm">
            {chain.data.ok ? (
              <Badge tone="blue">chain verified · {chain.data.count} entries</Badge>
            ) : (
              <Badge tone="red">TAMPER DETECTED at seq {chain.data.broken_at}</Badge>
            )}
          </div>
        )}
      </div>

      <Card className="p-4">
        {entries.loading && !entries.data ? (
          <Spinner />
        ) : entries.error ? (
          <ErrorBox message={entries.error} />
        ) : (
          <Table head={["Seq", "Time", "Actor", "Action", "Site", "Target", "Result", "Hash"]}>
            {(entries.data ?? []).map((e) => (
              <tr key={e.seq} className="text-slate-300">
                <Td className="font-mono text-slate-500">{e.seq}</Td>
                <Td className="text-slate-400">{new Date(e.ts).toLocaleString()}</Td>
                <Td>{e.actor}</Td>
                <Td className="font-medium text-slate-100">{e.action}</Td>
                <Td className="text-slate-400">{e.node_name ?? "—"}</Td>
                <Td className="font-mono text-xs">{e.target_id ?? "—"}</Td>
                <Td>
                  {e.result === "success" ? (
                    <Badge tone="blue">ok</Badge>
                  ) : (
                    <Badge tone="red">fail</Badge>
                  )}
                </Td>
                <Td className="font-mono text-[10px] text-slate-600" title={e.entry_hash}>
                  {e.entry_hash.slice(0, 10)}…
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
