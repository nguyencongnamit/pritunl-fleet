import React from "react";
import { api, ApiError, type AdapterType, type Node } from "../lib/api";
import { Badge, Button, Card, ErrorBox, Spinner, StatusBadge, Table, Td, useAsync } from "../lib/ui";

export function Nodes() {
  const { data, error, loading, refetch } = useAsync<Node[]>(() => api.get("/nodes"), []);
  const [showAdd, setShowAdd] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [actionErr, setActionErr] = React.useState<string | null>(null);

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    setActionErr(null);
    try {
      await fn();
      refetch();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Node registry</h2>
        <Button onClick={() => setShowAdd((s) => !s)}>{showAdd ? "Close" : "+ Add node"}</Button>
      </div>

      {actionErr && <ErrorBox message={actionErr} />}
      {showAdd && <AddNodeForm onDone={() => { setShowAdd(false); refetch(); }} />}

      <Card className="p-4">
        {loading && !data ? (
          <Spinner />
        ) : error ? (
          <ErrorBox message={error} />
        ) : (
          <Table head={["Region", "Name", "Adapter", "Endpoint", "Status", "Enabled", "Actions"]}>
            {(data ?? []).map((n) => (
              <tr key={n.id} className="text-slate-300">
                <Td className="text-slate-400">{n.region}</Td>
                <Td className="font-medium text-slate-100">{n.name}</Td>
                <Td><Badge tone="blue">{n.adapter_type}</Badge></Td>
                <Td className="font-mono text-xs text-slate-400">{n.endpoint}</Td>
                <Td title={n.last_error ?? ""}><StatusBadge status={n.status} /></Td>
                <Td>{n.enabled ? <Badge tone="blue">on</Badge> : <Badge tone="slate">off</Badge>}</Td>
                <Td>
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="ghost" disabled={busy === n.id}
                      onClick={() => run(n.id, () => api.post(`/nodes/${n.id}/check`))}>
                      Check
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy === n.id}
                      onClick={() => run(n.id, () => api.patch(`/nodes/${n.id}`, { enabled: !n.enabled }))}>
                      {n.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button size="sm" variant="danger" disabled={busy === n.id}
                      onClick={() => {
                        if (confirm(`Remove node ${n.name}?`)) run(n.id, () => api.del(`/nodes/${n.id}`));
                      }}>
                      Remove
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

function AddNodeForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = React.useState("");
  const [region, setRegion] = React.useState("");
  const [endpoint, setEndpoint] = React.useState("http://");
  const [adapter, setAdapter] = React.useState<AdapterType>("shim");
  const [verifyTls, setVerifyTls] = React.useState(false);
  const [token, setToken] = React.useState("");
  const [secret, setSecret] = React.useState("");
  const [credsJson, setCredsJson] = React.useState("{}");
  const [err, setErr] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    let credentials: Record<string, unknown>;
    try {
      credentials = adapter === "shim" ? { token, secret } : JSON.parse(credsJson);
    } catch {
      setErr("credentials must be valid JSON");
      return;
    }
    setSaving(true);
    try {
      await api.post("/nodes", { name, region, endpoint, adapter_type: adapter, verify_tls: verifyTls, credentials });
      onDone();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : String(e2));
    } finally {
      setSaving(false);
    }
  }

  const input = "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-brand";
  return (
    <Card className="p-4">
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Name"><input className={input} value={name} onChange={(e) => setName(e.target.value)} required /></Field>
        <Field label="Region"><input className={input} placeholder="SG" value={region} onChange={(e) => setRegion(e.target.value)} required /></Field>
        <Field label="Endpoint"><input className={input} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} required /></Field>
        <Field label="Adapter">
          <select className={input} value={adapter} onChange={(e) => setAdapter(e.target.value as AdapterType)}>
            <option value="shim">shim (default)</option>
            <option value="mongo">mongo (read-only)</option>
            <option value="ssh">ssh (break-glass)</option>
          </select>
        </Field>
        {adapter === "shim" ? (
          <>
            <Field label="Auth token"><input className={input} value={token} onChange={(e) => setToken(e.target.value)} /></Field>
            <Field label="HMAC secret"><input className={input} type="password" value={secret} onChange={(e) => setSecret(e.target.value)} /></Field>
          </>
        ) : (
          <Field label="Credentials (JSON)" wide>
            <textarea className={input} rows={3} value={credsJson} onChange={(e) => setCredsJson(e.target.value)} />
          </Field>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={verifyTls} onChange={(e) => setVerifyTls(e.target.checked)} /> Verify node TLS
        </label>
        <div className="sm:col-span-2">
          {err && <div className="mb-2"><ErrorBox message={err} /></div>}
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Register node"}</Button>
        </div>
      </form>
    </Card>
  );
}

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <label className="mb-1 block text-xs text-slate-400">{label}</label>
      {children}
    </div>
  );
}
