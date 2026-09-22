import React from "react";
import { ApiError, auth, setToken } from "../lib/api";
import { Button, Card, ErrorBox } from "../lib/ui";

type Step = "login" | "enroll" | "code";

export function Login({ onAuthed }: { onAuthed: () => void }) {
  const [step, setStep] = React.useState<Step>("login");
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [stepToken, setStepToken] = React.useState("");
  const [enroll, setEnroll] = React.useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const input =
    "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand";

  async function doLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const r = await auth.login(username, password);
      setStepToken(r.token);
      if (r.enroll_required) {
        const en = await auth.enroll(r.token);
        setEnroll(en);
        setStep("enroll");
      } else {
        setStep("code");
      }
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : String(e2));
    } finally {
      setBusy(false);
    }
  }

  async function doVerify(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const r = await auth.verify(stepToken, code.trim());
      setToken(r.token);
      onAuthed();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : String(e2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-5">
          <div className="font-mono text-sm font-semibold text-brand">PRITUNL</div>
          <div className="font-mono text-xl font-semibold text-slate-100">FLEET</div>
          <div className="mt-1 text-xs text-slate-500">multi-site control plane · sign in</div>
        </div>

        {err && <div className="mb-3"><ErrorBox message={err} /></div>}

        {step === "login" && (
          <form onSubmit={doLogin} className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-slate-400">Username</label>
              <input className={input} value={username} autoFocus onChange={(e) => setUsername(e.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Password</label>
              <input className={input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <Button type="submit" disabled={busy}>{busy ? "Signing in…" : "Continue"}</Button>
          </form>
        )}

        {step === "enroll" && enroll && (
          <div className="space-y-3">
            <p className="text-sm text-slate-300">
              MFA is required. Add this secret to your authenticator app (TOTP), then enter the 6-digit code.
            </p>
            <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
              <div className="text-[11px] uppercase text-slate-500">Secret key</div>
              <div className="break-all font-mono text-sm text-brand-muted">{enroll.secret}</div>
              <div className="mt-2 text-[11px] uppercase text-slate-500">otpauth URI</div>
              <div className="break-all font-mono text-[11px] text-slate-400">{enroll.otpauth_uri}</div>
            </div>
            <form onSubmit={doVerify} className="space-y-3">
              <input className={input} inputMode="numeric" placeholder="123456" value={code}
                onChange={(e) => setCode(e.target.value)} autoFocus required />
              <Button type="submit" disabled={busy}>{busy ? "Verifying…" : "Verify & finish"}</Button>
            </form>
          </div>
        )}

        {step === "code" && (
          <form onSubmit={doVerify} className="space-y-3">
            <p className="text-sm text-slate-300">Enter the 6-digit code from your authenticator.</p>
            <input className={input} inputMode="numeric" placeholder="123456" value={code}
              onChange={(e) => setCode(e.target.value)} autoFocus required />
            <Button type="submit" disabled={busy}>{busy ? "Verifying…" : "Verify"}</Button>
          </form>
        )}
      </Card>
    </div>
  );
}
