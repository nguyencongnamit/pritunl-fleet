import React from "react";
import {
  api,
  ApiError,
  downloadIdentityBundle,
  type LogicalUser,
  type Node,
  type NodeSyncReport,
  type Placement,
} from "../lib/api";
import { Badge, Button, Card, ErrorBox, Spinner, Table, Td, useAsync } from "../lib/ui";

const PLACEMENT_TONE: Record<Placement["status"], "blue" | "amber" | "red" | "slate"> = {
  active: "blue",
  pending: "slate",
  failed: "red",
  revoked: "amber",
  missing: "red",
};

export function Provisioning() {
  const nodes = useAsync<Node[]>(() => api.get("/nodes"), []);
  const identities = useAsync<LogicalUser[]>(() => api.get("/identities"), []);
  const [reports, setReports] = React.useState<NodeSyncReport[] | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  async function syncNow() {
    setBusy(true);
    setErr(null);
    try {
      setReports(await api.post<NodeSyncReport[]>("/sync"));
      identities.refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deprovision(id: string, hard: boolean) {
    if (!confirm(hard ? "Delete this identity on ALL sites?" : "Revoke this identity on ALL sites?")) return;
    setErr(null);
    try {
      await api.post(`/identities/${id}/deprovision`, { hard });
      identities.refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-6">
      {err && <ErrorBox message={err} />}

      <ProvisionForm nodes={nodes.data ?? []} onDone={() => identities.refetch()} />

      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Logical identities</h2>
          <Button variant="ghost" onClick={syncNow} disabled={busy}>
            {busy ? "Syncing…" : "Sync now"}
          </Button>
        </div>
        {identities.loading && !identities.data ? (
          <Spinner />
        ) : identities.error ? (
          <ErrorBox message={identities.error} />
        ) : (
          <Table head={["User", "Email", "Sites (placements)", "Actions"]}>
            {(identities.data ?? []).map((lu) => (
              <tr key={lu.id} className="text-slate-300">
                <Td className="font-medium text-slate-100">{lu.username}</Td>
                <Td className="text-slate-400">{lu.email ?? "—"}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1.5">
                    {lu.placements.map((p) => {
                      const node = (nodes.data ?? []).find((n) => n.id === p.node_id);
                      return (
                        <span key={p.id} title={p.last_error ?? ""}>
                          <Badge tone={PLACEMENT_TONE[p.status]}>
                            {node?.name ?? p.node_id.slice(0, 8)}: {p.status}
                          </Badge>
                        </span>
                      );
                    })}
                    {lu.placements.length === 0 && <span className="text-xs text-slate-500">none</span>}
                  </div>
                </Td>
                <Td>
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="ghost"
                      onClick={() => downloadIdentityBundle(lu.id, lu.username).catch((e) => setErr(String(e)))}>
                      Profiles
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => deprovision(lu.id, false)}>Revoke all</Button>
                    <Button size="sm" variant="danger" onClick={() => deprovision(lu.id, true)}>Delete all</Button>
                  </div>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {reports && (
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Last sync — drift report</h2>
          <Table head={["Site", "Reachable", "Tracked", "Present", "Missing", "Untracked", "In sync"]}>
            {reports.map((r) => (
              <tr key={r.node_id} className="text-slate-300">
                <Td className="font-medium text-slate-100">{r.node_name}</Td>
                <Td>{r.reachable ? <Badge tone="blue">yes</Badge> : <Badge tone="red">no</Badge>}</Td>
                <Td className="font-mono">{r.tracked}</Td>
                <Td className="font-mono">{r.present}</Td>
                <Td className="font-mono text-red-400">{r.missing.length}</Td>
                <Td className="font-mono text-amber-400">{r.untracked.length}</Td>
                <Td>{r.in_sync ? <Badge tone="blue">in sync</Badge> : <Badge tone="amber">drift</Badge>}</Td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </div>
  );
}

function ProvisionForm({ nodes, onDone }: { nodes: Node[]; onDone: () => void }) {
  const [username, setUsername] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [selected, setSelected] = React.useState<Record<string, string>>({}); // node_id -> org_id
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  function toggle(nodeId: string) {
    setSelected((s) => {
      const next = { ...s };
      if (nodeId in next) delete next[nodeId];
      else next[nodeId] = "org-1";
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const targets = Object.entries(selected).map(([node_id, org_id]) => ({ node_id, org_id }));
    if (targets.length === 0) {
      setErr("select at least one site");
      return;
    }
    setSaving(true);
    try {
      await api.post("/provision", { username, email: email || null, targets });
      setUsername("");
      setEmail("");
      setSelected({});
      onDone();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : String(e2));
    } finally {
      setSaving(false);
    }
  }

  const input =
    "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-brand";

  return (
    <Card className="p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Provision one identity to multiple sites</h2>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-slate-400">Username</label>
            <input className={input} value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Email (optional)</label>
            <input className={input} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Target sites</label>
          <div className="flex flex-wrap gap-2">
            {nodes.map((n) => {
              const on = n.id in selected;
              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => toggle(n.id)}
                  className={
                    "rounded-lg border px-3 py-1.5 text-sm transition " +
                    (on
                      ? "border-brand bg-brand/15 text-brand-muted"
                      : "border-slate-700 text-slate-300 hover:bg-slate-800")
                  }
                >
                  {n.name} · {n.region}
                </button>
              );
            })}
            {nodes.length === 0 && <span className="text-xs text-slate-500">no nodes registered</span>}
          </div>
        </div>
        {err && <ErrorBox message={err} />}
        <Button type="submit" disabled={saving}>{saving ? "Provisioning…" : "Provision"}</Button>
      </form>
    </Card>
  );
}
