import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Field } from "../ui";
import { checkReset, confirmReset, requestReset } from "../accountApi";
import { asError, EMAIL_RE, newPasswordProblems, NewPasswordFields } from "./forms";

type ResetStep = { kind: "request" } | { kind: "checking" } | { kind: "set"; email: string } | { kind: "invalid" };

export function ResetPage({ token, onSignIn }: { token: string | null; onSignIn: (message?: string) => void }) {
  const [step, setStep] = useState<ResetStep>(token ? { kind: "checking" } : { kind: "request" });

  useEffect(() => {
    if (!token) return;
    checkReset(token)
      .then((r) => setStep({ kind: "set", email: r.email }))
      .catch(() => setStep({ kind: "invalid" }));
  }, [token]);

  let body: ReactNode;
  if (step.kind === "checking") body = <p className="muted">Checking your link…</p>;
  else if (step.kind === "request") body = <RequestLink onSignIn={() => onSignIn()} />;
  else if (step.kind === "invalid")
    body = (
      <div className="form">
        <div className="box grey" role="alert">
          <strong>This reset link can no longer be used</strong>
          <p className="muted small">Reset links work once and expire. Request a new link to try again.</p>
        </div>
        <button className="btn secondary" type="button" onClick={() => setStep({ kind: "request" })}>Request a new link</button>
      </div>
    );
  else body = <SetPassword token={token!} email={step.email} onInvalid={() => setStep({ kind: "invalid" })} onDone={(m) => onSignIn(m)} />;

  return (
    <div className="reset-page">
      <h1>Recover your account</h1>
      {body}
    </div>
  );
}

function RequestLink({ onSignIn }: { onSignIn: () => void }) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string>();
  const [sent, setSent] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!EMAIL_RE.test(email.trim())) {
      setError("Enter your email address.");
      return;
    }
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      setSent((await requestReset(email.trim())).message);
    } catch (err) {
      setError(asError(err).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form box step" onSubmit={onSubmit} noValidate>
      <p className="step-label">STEP 1 · REQUEST A LINK</p>
      <h2 className="card-title">Forgot your password?</h2>
      <p className="muted small">Enter your email and we will send a reset link.</p>
      <Field label="Email" error={error} id="reset-email">
        <input id="reset-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <button className="btn primary" type="submit" disabled={busy}>Send reset link</button>
      {sent && <p className="muted small" role="status">✓ {sent} The same message is shown either way.</p>}
      <button className="link small" type="button" onClick={onSignIn}>Back to sign in</button>
    </form>
  );
}

function SetPassword({ token, email, onInvalid, onDone }: { token: string; email: string; onInvalid: () => void; onDone: (message: string) => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    Object.assign(e, newPasswordProblems(password, confirm));
    setErrors(e);
    if (Object.keys(e).length || busy) return;
    setBusy(true);
    try {
      onDone((await confirmReset(token, password)).message);
    } catch (err) {
      const x = asError(err);
      if (x.code === "link_invalid") onInvalid();
      else setErrors({ [x.param ?? "form"]: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form box step" onSubmit={onSubmit} noValidate>
      <p className="step-label">STEP 2 · FROM THE EMAILED LINK</p>
      <h2 className="card-title">Set a new password</h2>
      <p className="muted small">For {email}. The link works once and expires after a short time.</p>
      {errors.form && <p className="alert" role="alert">{errors.form}</p>}
      <NewPasswordFields password={password} confirm={confirm} errors={errors} onPassword={setPassword} onConfirm={setConfirm} />
      <button className="btn primary" type="submit" disabled={busy}>Save new password</button>
    </form>
  );
}
