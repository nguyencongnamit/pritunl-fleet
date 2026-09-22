import React from "react";
import { api, ApiError, downloadProfile, type ScopedUser } from "../lib/api";
import { Badge, Button, Card, ErrorBox, Spinner, Table, Td, useAsync } from "../lib/ui";

export function Users() {
  const [q, setQ] = React.useState("");
  const [applied, setApplied] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const { data, error, loading, refetch } = useAsync<ScopedUser[]>(
    () => api.get(`/users${applied ? `?q=${encodeURIComponent(applied)}` : ""}`),
    [applied],
  );

  async function run(key: string, fn: () => Promise<unknown>, quiet = false) {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      if (!quiet) refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const input =
    "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-brand";

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setApplied(q); }} className="flex gap-2">
        <input className={input} placeholder="Search users across all sites by name or email…"
          value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit">Search</Button>
      </form>

      {err && <ErrorBox message={err} />}

      <Card className="p-4">
        {loading && !data ? (
          <Spinner />
        ) : error ? (
          <ErrorBox message={error} />
        ) : (
          <Table head={["User", "Email", "Org", "Site", "State", "Actions"]}>
            {(data ?? []).map((u) => {
              const key = `${u.node_id}:${u.id}`;
              const b = busy === key;
              return (
                <tr key={key} className="text-slate-300">
                  <Td className="font-medium text-slate-100">{u.name}</Td>
                  <Td className="text-slate-400">{u.email ?? "—"}</Td>
                  <Td>{u.org_name ?? u.org_id}</Td>
                  <Td>
                    {u.node_name} <span className="text-slate-500">· {u.region}</span>
                  </Td>
                  <Td>
                    {u.revoked ? <Badge tone="red">revoked</Badge>
                      : u.disabled ? <Badge tone="amber">disabled</Badge>
                      : <Badge tone="blue">active</Badge>}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1.5">
                      <Button size="sm" variant="ghost" disabled={b || u.revoked}
                        onClick={() => run(key, () => downloadProfile(u.node_id, u.id, u.org_id), true)}>
                        Profile
                      </Button>
                      <Button size="sm" variant="ghost" disabled={b}
                        onClick={() => run(key, () => api.post(`/nodes/${u.node_id}/users/${u.id}/disable`, { org_id: u.org_id, disabled: !u.disabled }))}>
                        {u.disabled ? "Enable" : "Disable"}
                      </Button>
                      <Button size="sm" variant="ghost" disabled={b}
                        onClick={() => {
                          const pin = prompt(`Set PIN for ${u.name} (blank = leave unchanged):`, "");
                          const otp = confirm("Require OTP/2FA on this user's VPN connection?\nOK = enable, Cancel = disable");
                          const policy: Record<string, unknown> = { org_id: u.org_id, otp_auth: otp };
                          if (pin) policy.pin = pin;
                          run(key, () => api.patch(`/nodes/${u.node_id}/users/${u.id}/policy`, policy));
                        }}>
                        Policy
                      </Button>
                      <Button size="sm" variant="ghost" disabled={b || u.revoked}
                        onClick={() => { if (confirm(`Revoke all profiles for ${u.name}?`)) run(key, () => api.post(`/nodes/${u.node_id}/users/${u.id}/revoke`, { org_id: u.org_id })); }}>
                        Revoke
                      </Button>
                      <Button size="sm" variant="danger" disabled={b}
                        onClick={() => { if (confirm(`Delete ${u.name} from ${u.node_name}?`)) run(key, () => api.del(`/nodes/${u.node_id}/users/${u.id}?org_id=${encodeURIComponent(u.org_id)}`)); }}>
                        Delete
                      </Button>
                    </div>
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}
        {data && data.length === 0 && (
          <div className="py-6 text-center text-sm text-slate-500">No users found.</div>
        )}
      </Card>
    </div>
  );
}
