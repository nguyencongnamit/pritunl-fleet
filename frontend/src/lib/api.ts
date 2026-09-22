// Tiny typed fetch client. Same-origin in production (FastAPI serves this SPA);
// Vite proxies /api during `npm run dev`. Auth token support is wired now and
// used from Phase 5 (login + MFA); until then requests are unauthenticated.

const TOKEN_KEY = "fleet.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    setToken(null);
    if (!location.hash.startsWith("#/login")) location.hash = "#/login";
    throw new ApiError(401, "authentication required");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = (j.detail ?? j.error ?? detail) as string;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? await res.json() : await res.text()) as T;
}

export const api = {
  get: <T>(p: string) => req<T>("GET", p),
  post: <T>(p: string, b?: unknown) => req<T>("POST", p, b ?? {}),
  put: <T>(p: string, b?: unknown) => req<T>("PUT", p, b ?? {}),
  patch: <T>(p: string, b?: unknown) => req<T>("PATCH", p, b ?? {}),
  del: <T>(p: string) => req<T>("DELETE", p),
};

// --- Auth (does not use req()'s 401->redirect behavior) ---
export type Role = "viewer" | "operator" | "admin";

export interface Me {
  id: string;
  username: string;
  email: string | null;
  global_role: Role;
  mfa_enabled: boolean;
  bindings: { node_id: string; role: Role }[];
}

async function authReq<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api/v1${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export interface LoginResult {
  token: string;
  scope: string;
  mfa_required: boolean;
  enroll_required: boolean;
}

export const auth = {
  login: (username: string, password: string) =>
    authReq<LoginResult>("/auth/login", { username, password }),
  enroll: (stepToken: string) =>
    authReq<{ secret: string; otpauth_uri: string }>("/auth/mfa/enroll", {}, stepToken),
  verify: (stepToken: string, code: string) =>
    authReq<{ token: string; scope: string }>("/auth/mfa/verify", { code }, stepToken),
  me: () => api.get<Me>("/auth/me"),
};

// --- Shared response types (mirror the backend schemas) ---
export type HealthStatus = "unknown" | "reachable" | "degraded" | "down";
export type AdapterType = "shim" | "mongo" | "ssh";

export interface SiteSummary {
  node_id: string;
  name: string;
  region: string;
  adapter_type: AdapterType;
  status: HealthStatus;
  servers_total: number;
  servers_online: number;
  orgs: number;
  users_total: number;
  users_disabled: number;
  active_sessions: number;
  online_clients: number;
  last_checked_at: string | null;
  last_synced_at: string | null;
  last_latency_ms: number | null;
  error: string | null;
}

export interface Dashboard {
  generated_at: string;
  totals: {
    sites: number;
    sites_reachable: number;
    servers_total: number;
    servers_online: number;
    users_total: number;
    active_sessions: number;
    online_clients: number;
  };
  sites: SiteSummary[];
}

export interface Node {
  id: string;
  name: string;
  region: string;
  endpoint: string;
  adapter_type: AdapterType;
  verify_tls: boolean;
  enabled: boolean;
  admin_url: string | null;
  status: HealthStatus;
  last_checked_at: string | null;
  last_latency_ms: number | null;
  last_error: string | null;
}

export interface ScopedUser {
  id: string;
  name: string;
  org_id: string;
  org_name: string | null;
  disabled: boolean;
  revoked: boolean;
  email: string | null;
  node_id: string;
  node_name: string;
  region: string;
}

export interface ScopedServer {
  id: string;
  name: string;
  status: string;
  protocol: string;
  port: number | null;
  online_clients: number;
  org_ids: string[];
  node_id: string;
  node_name: string;
  region: string;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  actor: string;
  action: string;
  node_id: string | null;
  node_name: string | null;
  target_type: string | null;
  target_id: string | null;
  result: string;
  detail: string | null;
  entry_hash: string;
  prev_hash: string;
}

export interface ChainStatus {
  ok: boolean;
  count: number;
  broken_at: number | null;
  detail: string | null;
}

export interface Placement {
  id: string;
  node_id: string;
  org_id: string;
  remote_user_id: string | null;
  status: "pending" | "active" | "failed" | "revoked" | "missing";
  last_error: string | null;
  last_synced_at: string | null;
}

export interface LogicalUser {
  id: string;
  username: string;
  email: string | null;
  created_at: string;
  placements: Placement[];
}

export interface DriftItem {
  kind: string;
  remote_user_id: string | null;
  username: string | null;
}

export interface NodeSyncReport {
  node_id: string;
  node_name: string;
  reachable: boolean;
  tracked: number;
  present: number;
  missing: DriftItem[];
  untracked: DriftItem[];
  in_sync: boolean;
  error: string | null;
}

// Download a client profile (.ovpn) and trigger a browser save.
export async function downloadProfile(
  nodeId: string,
  userId: string,
  orgId: string,
  fmt = "ovpn",
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api/v1/nodes/${nodeId}/users/${userId}/profile`, {
    method: "POST",
    headers,
    body: JSON.stringify({ org_id: orgId, fmt }),
  });
  if (!res.ok) throw new ApiError(res.status, `profile download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${userId}.${fmt}`;
  a.click();
  URL.revokeObjectURL(url);
}
