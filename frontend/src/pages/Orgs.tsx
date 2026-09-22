import React from "react";
import { api, ApiError, type Node } from "../lib/api";
import { Badge, Button, Card, ErrorBox, Spinner, Table, Td, useAsync } from "../lib/ui";

interface Org {
  id: string;
  name: string;
  user_count: number;
}

export function Orgs() {
  const nodes = useAsync<Node[]>(() => api.get("/nodes"), []);
  const [nodeId, setNodeId] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!nodeId && nodes.data && nodes.data.length) setNodeId(nodes.data[0].id);
  }, [nodes.data, nodeId]);

  const orgs = useAsync<Org[]>(
    () => (nodeId ? api.get(`/nodes/${nodeId}/orgs`) : Promise.resolve([])),
    [nodeId],
  );

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      orgs.refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const input =
    "rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-brand";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-400">Node</span>
        <select className={input} value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
          {(nodes.data ?? []).map((n) => (
            <option key={n.id} value={n.id}>{n.name} · {n.region}</option>
          ))}
        </select>
      </div>

      {err && <ErrorBox message={err} />}

      <CreateOrg nodeId={nodeId} disabled={!nodeId || busy} onDone={() => orgs.refetch()} setErr={setErr} />

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">Organizations</h2>
        {orgs.loading && !orgs.data ? (
          <Spinner />
        ) : orgs.error ? (
          <ErrorBox message={orgs.error} />
        ) : (
          <Table head={["Org", "Users", "Bulk add users", "Actions"]}>
            {(orgs.data ?? []).map((o) => (
              <tr key={o.id} className="text-slate-300 align-top">
                <Td className="font-medium text-slate-100">{o.name}</Td>
                <Td><Badge tone="blue">{o.user_count}</Badge></Td>
                <Td><BulkAdd nodeId={nodeId} orgId={o.id} onDone={() => orgs.refetch()} setErr={setErr} /></Td>
                <Td>
                  <Button size="sm" variant="danger" disabled={busy}
                    onClick={() => { if (confirm(`Delete org ${o.name} and its users?`)) run(() => api.del(`/nodes/${nodeId}/orgs/${o.id}`)); }}>
                    Delete
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        )}
        {orgs.data && orgs.data.length === 0 && (
          <div className="py-6 text-center text-sm text-slate-500">No orgs on this node.</div>
        )}
      </Card>
    </div>
  );
}

function CreateOrg({ nodeId, disabled, onDone, setErr }: {
  nodeId: string; disabled: boolean; onDone: () => void; setErr: (s: string | null) => void;
}) {
  const [name, setName] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const input = "rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-brand";
  return (
    <Card className="p-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true); setErr(null);
          try { await api.post(`/nodes/${nodeId}/orgs`, { name }); setName(""); onDone(); }
          catch (e2) { setErr(e2 instanceof ApiError ? e2.message : String(e2)); }
          finally { setSaving(false); }
        }}
        className="flex items-end gap-2"
      >
        <div>
          <label className="mb-1 block text-xs text-slate-400">New organization</label>
          <input className={input} placeholder="org name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <Button type="submit" disabled={disabled || saving || !name}>Create org</Button>
      </form>
    </Card>
  );
}

function BulkAdd({ nodeId, orgId, onDone, setErr }: {
  nodeId: string; orgId: string; onDone: () => void; setErr: (s: string | null) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [result, setResult] = React.useState<string | null>(null);

  async function submit() {
    const users = text
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((line) => {
        const [name, email] = line.split(/\s+/);
        return { name, email: email || null };
      });
    if (!users.length) return;
    setSaving(true); setErr(null); setResult(null);
    try {
      const r = await api.post<{ created: number; results: unknown[] }>(
        `/nodes/${nodeId}/users/bulk`, { org_id: orgId, users },
      );
      setResult(`created ${r.created}/${users.length}`);
      setText("");
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const input = "w-64 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100 outline-none focus:border-brand";
  if (!open) {
    return <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>+ Bulk add</Button>;
  }
  return (
    <div className="space-y-1">
      <textarea className={input} rows={3} placeholder="one per line: name [email]" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="flex items-center gap-2">
        <Button size="sm" disabled={saving} onClick={submit}>{saving ? "Adding…" : "Add"}</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Close</Button>
        {result && <span className="text-xs text-blue-300">{result}</span>}
      </div>
    </div>
  );
}
