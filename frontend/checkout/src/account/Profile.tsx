import { useEffect, useState, type FormEvent } from "react";
import { Field, Row } from "../ui";
import { getProfile, signOutEverywhere, updateProfile, type PersonalData } from "../accountApi";
import { formatDate } from "../format";
import { asError, EMAIL_RE } from "./forms";

export function Profile({ onChanged, onSignedOut, onEnded }: {
  onChanged: (d: PersonalData) => void;
  onSignedOut: () => void;
  onEnded: () => void;
}) {
  const [data, setData] = useState<PersonalData | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();

  useEffect(() => {
    getProfile().then(setData).catch((err) => (asError(err).status === 401 ? onEnded() : setError(asError(err).message)));
  }, [onEnded]);

  async function everywhere() {
    try {
      await signOutEverywhere();
      onSignedOut();
    } catch (err) {
      if (asError(err).status === 401) onEnded();
      else setError(asError(err).message);
    }
  }

  if (!data) return error ? <p className="alert" role="alert">{error}</p> : <p className="muted">Loading…</p>;
  const when = (iso: string | null) => (iso ? formatDate(iso) : "—");
  return (
    <div className="form">
      <h1>Profile</h1>
      <p className="muted small">Everything SecurePay keeps about you as a person. Your payments are in Payment history.</p>
      {notice && <p className="muted small" role="status">{notice}</p>}
      {editing ? (
        <EditDetails data={data} onEnded={onEnded} onCancel={() => setEditing(false)}
          onSaved={(d) => {
            setData(d);
            setEditing(false);
            setNotice("Your details have been updated.");
            onChanged(d);
          }} />
      ) : (
        <>
          <dl className="box">
            <Row label="Full name">{data.full_name}</Row>
            <Row label="Email">{data.email}</Row>
            <Row label="Account created">{when(data.created_at)}</Row>
            <Row label="Last sign-in">{when(data.last_sign_in_at)}</Row>
            <Row label="Password changed">{when(data.password_changed_at)}</Row>
            <Row label="Details corrected">{when(data.details_changed_at)}</Row>
            <Row label="Privacy notice agreed">
              {data.privacy_notice_version ? `Version ${data.privacy_notice_version}, ${when(data.privacy_consent_at)}` : "—"}
            </Row>
            <Row label="Payments in history">{data.payments}</Row>
            <Row label="Signed-in devices">{data.active_sessions}</Row>
          </dl>
          <button className="btn secondary" type="button" onClick={() => { setNotice(undefined); setEditing(true); }}>
            Correct my details
          </button>
        </>
      )}
      {error && <p className="alert" role="alert">{error}</p>}
      <p className="muted small">Lost a device, or signed in on a shared computer? This ends every signed-in session of your account, including this one.</p>
      <button className="btn secondary" type="button" onClick={everywhere}>Sign out on every device</button>
    </div>
  );
}

function EditDetails({ data, onSaved, onCancel, onEnded }: {
  data: PersonalData;
  onSaved: (d: PersonalData) => void;
  onCancel: () => void;
  onEnded: () => void;
}) {
  const [name, setName] = useState(data.full_name);
  const [email, setEmail] = useState(data.email);
  const [current, setCurrent] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (!name.trim()) e.full_name = "Enter your full name.";
    if (!EMAIL_RE.test(email.trim())) e.email = "Enter a valid email address.";
    if (!current) e.current_password = "Enter your current password to confirm it's you.";
    setErrors(e);
    if (Object.keys(e).length || busy) return;
    setBusy(true);
    try {
      onSaved(await updateProfile(current, name.trim(), email.trim()));
    } catch (err) {
      const x = asError(err);
      if (x.status === 401) onEnded();
      else setErrors({ [x.param ?? "form"]: x.message });
      setCurrent("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form box step" onSubmit={onSubmit} noValidate>
      {errors.form && <p className="alert" role="alert">{errors.form}</p>}
      <Field label="Full name" error={errors.full_name} id="pd-name">
        <input id="pd-name" autoComplete="name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Email" error={errors.email} id="pd-email">
        <input id="pd-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <p className="muted tiny">If you change your email, we tell both the old and the new address.</p>
      <Field label="Current password" error={errors.current_password} id="pd-current">
        <input id="pd-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <div className="btn-row">
        <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
        <button className="btn primary" type="submit" disabled={busy}>Save details</button>
      </div>
    </form>
  );
}
