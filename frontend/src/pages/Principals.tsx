import React from "react";
import { api, ApiError, type Node, type Role } from "../lib/api";
import { Badge, Button, Card, ErrorBox, Spinner, Table, Td, useAsync } from "../lib/ui";

interface Principal {
  id: string;
  username: string;
  email: string | null;
  global_role: Role;
  disabled: boolean;
  mfa_enabled: boolean;
  bindings: { node_id: string; role: Role }[];
}

const ROLES: Role[] = ["viewer", "operator", "admin"];

export function Principals() {
  const principals = useAsync<Principal[]>(() => api.get("/principals"), []);
  const nodes = useAsync<Node[]>(() => api.get("/nodes"), []);
  const [err, setErr] = React.useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      principals.refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  const nodeName = (id: string) => nodes.data?.find((n) => n.id === id)?.name ?? id.slice(0, 8);

  return (
    <div className="space-y-4">
      {err && <ErrorBox message={err} />}
      <CreateForm onDone={() => principals.refetch()} />

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">Principals</h2>
        {principals.loading && !principals.data ? (
          <Spinner />
        ) : principals.error ? (
          <ErrorBox message={principals.error} />
        ) : (
          <Table head={["User", "Global role", "MFA", "State", "Site bindings", "Actions"]}>
            {(principals.data ?? []).map((p) => (
              <tr key={p.id} className="text-slate-300 align-top">
                <Td>
                  <div className="font-medium text-slate-100">{p.username}</div>
                  <div className="text-xs text-slate-500">{p.email ?? "—"}</div>
                </Td>
                <Td>
                  <select
                    value={p.global_role}
                    onChange={(e) => run(() => api.patch(`/principals/${p.id}`, { global_role: e.target.value }))}
                    className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </Td>
                <Td>{p.mfa_enabled ? <Badge tone="blue">on</Badge> : <Badge tone="amber">not set</Badge>}</Td>
                <Td>{p.disabled ? <Badge tone="red">disabled</Badge> : <Badge tone="blue">active</Badge>}</Td>
                <Td>
                  <div className="space-y-1">
                    {p.bindings.map((b) => (
                      <div key={b.node_id} className="flex items-center gap-1 text-xs">
                        <Badge tone="slate">{nodeName(b.node_id)}: {b.role}</Badge>
                        <button className="text-slate-500 hover:text-red-400"
                          onClick={() => run(() => api.del(`/principals/${p.id}/bindings/${b.node_id}`))}>✕</button>
                      </div>
                    ))}
                    <AddBinding
                      onAdd={(node_id, role) => run(() => api.put(`/principals/${p.id}/bindings`, { node_id, role }))}
                      nodes={nodes.data ?? []}
                    />
                  </div>
                </Td>
                <Td>
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="ghost"
                      onClick={() => run(() => api.patch(`/principals/${p.id}`, { disabled: !p.disabled }))}>
                      {p.disabled ? "Enable" : "Disable"}
                    </Button>
                    <Button size="sm" variant="danger"
                      onClick={() => { if (confirm(`Delete ${p.username}?`)) run(() => api.del(`/principals/${p.id}`)); }}>
                      Delete
                    </Button>
                  </div>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function AddBinding({ nodes, onAdd }: { nodes: Node[]; onAdd: (nodeId: string, role: Role) => void }) {
  const [nodeId, setNodeId] = React.useState("");
  const [role, setRole] = React.useState<Role>("operator");

  return (
    <div className="flex items-center gap-1 pt-1">
      <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}
        className="rounded-md border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-xs text-slate-100">
        <option value="">+ site…</option>
        {nodes.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
      </select>
      <select value={role} onChange={(e) => setRole(e.target.value as Role)}
        className="rounded-md border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-xs text-slate-100">
        <option value="viewer">viewer</option>
        <option value="operator">operator</option>
        <option value="admin">admin</option>
      </select>
      <button
        onClick={() => { if (nodeId) onAdd(nodeId, role); }}
        className="rounded-md bg-brand px-2 py-0.5 text-xs text-white"
      >
        add
      </button>
    </div>
  );
}

function CreateForm({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState<Role>("viewer");
  const [err, setErr] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const input = "rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-brand";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.post("/principals", { username, email: email || null, password, global_role: role });
      setUsername(""); setEmail(""); setPassword(""); setRole("viewer");
      onDone();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : String(e2));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Create principal</h2>
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <input className={input} placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <input className={input} placeholder="email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className={input} type="password" placeholder="password (min 8)" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <select className={input} value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <Button type="submit" disabled={saving}>{saving ? "Creating…" : "Create"}</Button>
      </form>
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
    </Card>
  );
}
