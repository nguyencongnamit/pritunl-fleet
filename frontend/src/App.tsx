import React from "react";
import { auth, getToken, setToken, type Me } from "./lib/api";
import { Badge, cn, Spinner } from "./lib/ui";
import { Audit } from "./pages/Audit";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Nodes } from "./pages/Nodes";
import { Orgs } from "./pages/Orgs";
import { Principals } from "./pages/Principals";
import { Provisioning } from "./pages/Provisioning";
import { Servers } from "./pages/Servers";
import { Users } from "./pages/Users";

type Route = { path: string; label: string; el: React.ReactNode; adminOnly?: boolean };

const ROUTES: Route[] = [
  { path: "#/", label: "Dashboard", el: <Dashboard /> },
  { path: "#/nodes", label: "Nodes", el: <Nodes /> },
  { path: "#/servers", label: "Servers", el: <Servers /> },
  { path: "#/orgs", label: "Orgs", el: <Orgs /> },
  { path: "#/users", label: "Users", el: <Users /> },
  { path: "#/provision", label: "Provisioning", el: <Provisioning /> },
  { path: "#/audit", label: "Audit", el: <Audit /> },
  { path: "#/principals", label: "Principals", el: <Principals />, adminOnly: true },
];

function useHashRoute() {
  const [hash, setHash] = React.useState(location.hash || "#/");
  React.useEffect(() => {
    const on = () => setHash(location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export function App() {
  const hash = useHashRoute();
  const [me, setMe] = React.useState<Me | null | undefined>(undefined);

  const loadMe = React.useCallback(() => {
    if (!getToken()) {
      setMe(null);
      return;
    }
    auth
      .me()
      .then(setMe)
      .catch(() => {
        setToken(null);
        setMe(null);
      });
  }, []);

  React.useEffect(() => {
    loadMe();
  }, [loadMe]);

  if (me === undefined) {
    return <div className="flex min-h-full items-center justify-center"><Spinner label="Loading…" /></div>;
  }
  if (me === null || hash === "#/login") {
    return <Login onAuthed={() => { location.hash = "#/"; loadMe(); }} />;
  }

  const visible = ROUTES.filter((r) => !r.adminOnly || me.global_role === "admin");
  const active = visible.find((r) => r.path === hash) ?? visible[0];

  function logout() {
    setToken(null);
    setMe(null);
    location.hash = "#/login";
  }

  return (
    <div className="flex min-h-full">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-900/40 p-4 sm:flex">
        <div className="mb-6 px-2">
          <div className="font-mono text-sm font-semibold text-brand">PRITUNL</div>
          <div className="font-mono text-lg font-semibold text-slate-100">FLEET</div>
          <div className="mt-0.5 text-[11px] text-slate-500">multi-site control plane</div>
        </div>
        <nav className="flex flex-col gap-1">
          {visible.map((r) => (
            <a key={r.path} href={r.path}
              className={cn("rounded-lg px-3 py-2 text-sm transition",
                r.path === active.path ? "bg-brand/15 text-brand-muted" : "text-slate-300 hover:bg-slate-800/60")}>
              {r.label}
            </a>
          ))}
        </nav>
        <div className="mt-auto px-2 text-[11px] text-slate-600">Pritunl OSS · shim adapter</div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-800 px-6 py-3">
          <div className="text-sm font-medium text-slate-300">{active.label}</div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">{me.username}</span>
            <Badge tone="blue">{me.global_role}</Badge>
            <button onClick={logout} className="text-xs text-slate-400 hover:text-slate-200">Sign out</button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-6">{active.el}</main>
      </div>
    </div>
  );
}
