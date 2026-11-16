import { useState, type FormEvent } from "react";
import { Field } from "../ui";
import { changePassword } from "../accountApi";
import { asError, newPasswordProblems, NewPasswordFields } from "./forms";

export function PasswordPage({ onEnded, onDone }: { onEnded: () => void; onDone: (message: string) => void }) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (!current) e.current_password = "Enter your current password.";
    Object.assign(e, newPasswordProblems(password, confirm));
    setErrors(e);
    if (Object.keys(e).length || busy) return;
    setBusy(true);
    try {
      const r = await changePassword(current, password);
      setCurrent(""); setPassword(""); setConfirm("");
      onDone(r.message);
    } catch (err) {
      const x = asError(err);
      if (x.status === 401) onEnded();
      else setErrors({ [x.param ?? "form"]: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <h1>Password</h1>
      {errors.form && <p className="alert" role="alert">{errors.form}</p>}
      <Field label="Current password" error={errors.current_password} id="pw-current">
        <input id="pw-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <NewPasswordFields password={password} confirm={confirm} errors={errors} onPassword={setPassword} onConfirm={setConfirm} />
      <button className="btn primary" type="submit" disabled={busy}>Save new password</button>
    </form>
  );
}
