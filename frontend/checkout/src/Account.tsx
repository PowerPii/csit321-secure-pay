// Customer account pages, wireframes C10 to C12 (FR-ACC-01 to FR-ACC-04, FR-ACC-07, FR-ACC-08):
//   /account/sign-in   C10 sign in or create an account
//   /account/payments  C11 payment history (only payments made while signed in)
//   /account/profile   name, email, sign out on every device
//   /account/password  change password (signs out every other device)
//   /account/reset     C12 forgot password: request a link, then set a new password
// Served from the checkout build (Caddy), same CSP. An account is optional: guests still pay
// and check a payment with the emailed code (/guest/status).
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Field, Row } from "./App";
import {
  AccountApiError,
  changePassword,
  checkReset,
  confirmReset,
  getMe,
  getPayment,
  getPayments,
  register,
  requestReset,
  signIn,
  signOut,
  signOutEverywhere,
  type Customer,
  type HistoryRow,
  type PaymentDetail,
} from "./accountApi";
import { brandName, formatDate, money } from "./format";

export type Page = "sign-in" | "payments" | "profile" | "password" | "reset";
const PAGES: Page[] = ["sign-in", "payments", "profile", "password", "reset"];
const MIN_PASSWORD = 12;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function pageFromPath(path: string): Page {
  const name = path.replace(/^\/account\/?/, "").replace(/\/$/, "");
  return (PAGES as string[]).includes(name) ? (name as Page) : "sign-in";
}

/** The reset token from `#token=...`; the fragment never reaches a server. */
export function tokenFromHash(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return token && /^[\w-]{20,100}$/.test(token) ? token : null;
}

const asError = (err: unknown) =>
  err instanceof AccountApiError ? err : new AccountApiError(0, "unknown_error", "Something went wrong.", null, null);

const ENDED_NOTICE = "Your session has ended. Sign in again to see your account.";

export default function Account({ path = window.location.pathname, hash = window.location.hash }: { path?: string; hash?: string }) {
  const [page, setPage] = useState<Page>(pageFromPath(path));
  const [me, setMe] = useState<Customer | null | undefined>(undefined); // undefined: loading
  const [notice, setNotice] = useState<string>();
  const [resetToken] = useState(() => tokenFromHash(hash));

  useEffect(() => {
    // Keep the token out of the address bar and the browser history.
    if (resetToken && typeof window !== "undefined" && window.history?.replaceState) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [resetToken]);

  const go = useCallback((next: Page, message?: string) => {
    setNotice(message);
    setPage(next);
    if (typeof window !== "undefined" && window.history?.pushState) window.history.pushState(null, "", `/account/${next}`);
  }, []);

  useEffect(() => {
    const onPop = () => setPage(pageFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  const ended = useCallback(() => {
    setMe(null);
    go("sign-in", ENDED_NOTICE);
  }, [go]);

  const signedInPage = page === "payments" || page === "profile" || page === "password";
  useEffect(() => {
    if (me === undefined) return;
    if (signedInPage && me === null) go("sign-in", notice);
    if (page === "sign-in" && me) go("payments");
  }, [me, page, signedInPage, go, notice]);

  async function onSignOut() {
    await signOut().catch(() => undefined);
    setMe(null);
    go("sign-in", "You have signed out.");
  }

  let right: ReactNode = "My account";
  if (page === "reset") right = "Account recovery";
  else if (me) right = (
    <>
      {me.full_name} · <button className="link inverse" type="button" onClick={onSignOut}>Sign out</button>
    </>
  );

  let body: ReactNode;
  if (me === undefined && page !== "reset") body = <p className="muted center">Loading…</p>;
  else if (page === "reset") body = <ResetPage token={resetToken} onSignIn={(m) => go("sign-in", m)} />;
  else if (!me) body = <SignInPage notice={notice} onSignedIn={(c) => { setMe(c); go("payments"); }} onForgot={() => go("reset")} />;
  else
    body = (
      <div className="account-grid">
        <nav className="side-nav" aria-label="Account">
          {(["payments", "profile", "password"] as Page[]).map((p) => (
            <button key={p} type="button" className={`nav-item${page === p ? " active" : ""}`}
              aria-current={page === p ? "page" : undefined} onClick={() => go(p)}>
              {{ payments: "Payment history", profile: "Profile", password: "Password" }[p as "payments"]}
            </button>
          ))}
          <button type="button" className="nav-item" onClick={onSignOut}>Sign out</button>
        </nav>
        <section className="account-main">
          {notice && <p className="muted small" role="status">{notice}</p>}
          {page === "payments" && <History onEnded={ended} />}
          {page === "profile" && <Profile me={me} onSignedOut={() => { setMe(null); go("sign-in", "You have signed out on every device."); }} onEnded={ended} />}
          {page === "password" && <PasswordPage onEnded={ended} onDone={(m) => setNotice(m)} />}
        </section>
      </div>
    );

  return (
    <>
      <header className="topbar">
        <span className="brand">SecurePay</span>
        <span className="topbar-status">{right}</span>
      </header>
      <main className="account-page">{body}</main>
    </>
  );
}

// --- C10: sign in or create an account --------------------------------------------------

function SignInPage({ notice, onSignedIn, onForgot }: { notice?: string; onSignedIn: (c: Customer) => void; onForgot: () => void }) {
  const [tab, setTab] = useState<"sign-in" | "register">("sign-in");
  return (
    <div className="signin-layout">
      <aside className="signin-intro">
        <h1>Your SecurePay account</h1>
        <p className="muted small">An account is optional. Guests can still pay and check a payment with the one-time code on their receipt.</p>
        <ul className="ticks small">
          <li>See all your payments in one place</li>
          <li>Check the status of a refund</li>
          <li>Sign out on every device at once</li>
        </ul>
        <p className="muted tiny">Signed-in sessions end after 15 minutes without activity, and you are brought back to this page.</p>
      </aside>
      <div className="signin-cards">
        {notice && <p className="muted small full" role="status">{notice}</p>}
        <div className="tabs" role="tablist">
          <button role="tab" type="button" aria-selected={tab === "sign-in"} onClick={() => setTab("sign-in")}>Sign in</button>
          <button role="tab" type="button" aria-selected={tab === "register"} onClick={() => setTab("register")}>Register</button>
        </div>
        <div className={`card-box${tab === "sign-in" ? " shown" : ""}`}>
          <SignInForm onSignedIn={onSignedIn} onForgot={onForgot} />
        </div>
        <div className={`card-box${tab === "register" ? " shown" : ""}`}>
          <RegisterForm onSignedIn={onSignedIn} />
        </div>
      </div>
    </div>
  );
}

function SignInForm({ onSignedIn, onForgot }: { onSignedIn: (c: Customer) => void; onForgot: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<{ title: string; message: string }>();
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (!email.trim()) e.email = "Enter your email address.";
    if (!password) e.password = "Enter your password.";
    setErrors(e);
    if (Object.keys(e).length || busy) return;
    setBusy(true);
    setFailure(undefined);
    try {
      onSignedIn(await signIn(email.trim(), password, remember));
    } catch (err) {
      const x = asError(err);
      setPassword("");
      if (x.code === "invalid_credentials") setFailure({ title: "Email or password is incorrect", message: x.message.replace(/^Email or password is incorrect\.\s*/, "") });
      else if (x.code === "account_locked") setFailure({ title: "Sign-in is locked", message: x.message });
      else if (x.param) setErrors({ [x.param]: x.message });
      else setFailure({ title: "Could not sign in", message: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <h2 className="card-title">Sign in</h2>
      <p className="muted small">Use the email you registered with.</p>
      <Field label="Email" error={errors.email} id="signin-email">
        <input id="signin-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Password" error={errors.password} id="signin-password">
        <input id="signin-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <div className="row-between small">
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Keep me signed in on this device
        </label>
        <button className="link" type="button" onClick={onForgot}>Forgot password?</button>
      </div>
      <button className="btn primary" type="submit" disabled={busy}>Sign in</button>
      {failure && (
        <div className="box grey" role="alert">
          <strong>{failure.title}</strong>
          <p className="muted small">{failure.message}</p>
        </div>
      )}
    </form>
  );
}

function RegisterForm({ onSignedIn }: { onSignedIn: (c: Customer) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (!name.trim()) e.full_name = "Enter your full name.";
    if (!EMAIL_RE.test(email.trim())) e.email = "Enter a valid email address.";
    if (password.length < MIN_PASSWORD) e.password = `Use at least ${MIN_PASSWORD} characters.`;
    else if (confirm !== password) e.confirm = "The passwords do not match.";
    setErrors(e);
    if (Object.keys(e).length || busy) return;
    setBusy(true);
    try {
      onSignedIn(await register(name.trim(), email.trim(), password));
    } catch (err) {
      const x = asError(err);
      setErrors({ [x.param ?? "form"]: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <h2 className="card-title">Create an account</h2>
      <p className="muted small">Keep your payments with this gateway in one history.</p>
      {errors.form && <p className="alert" role="alert">{errors.form}</p>}
      <Field label="Full name" error={errors.full_name} id="reg-name">
        <input id="reg-name" autoComplete="name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Email" error={errors.email} id="reg-email">
        <input id="reg-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Password" error={errors.password} id="reg-password">
        <input id="reg-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      {!errors.password && <p className="muted tiny hint">Use at least {MIN_PASSWORD} characters.</p>}
      <Field label="Confirm password" error={errors.confirm} id="reg-confirm">
        <input id="reg-confirm" type="password" autoComplete="new-password" placeholder="Repeat password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      <button className="btn primary" type="submit" disabled={busy}>Create account</button>
    </form>
  );
}

// --- C11: payment history -----------------------------------------------------------------

function History({ onEnded }: { onEnded: () => void }) {
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [error, setError] = useState<string>();
  const [selected, setSelected] = useState<PaymentDetail | null>(null);
  const [selecting, setSelecting] = useState<string>();

  useEffect(() => {
    getPayments()
      .then((r) => setRows(r.data))
      .catch((err) => (asError(err).status === 401 ? onEnded() : setError(asError(err).message)));
  }, [onEnded]);

  async function open(reference: string) {
    setSelecting(reference);
    try {
      setSelected(await getPayment(reference));
    } catch (err) {
      if (asError(err).status === 401) onEnded();
      else setError(asError(err).message);
    } finally {
      setSelecting(undefined);
    }
  }

  return (
    <>
      <h1>Payment history</h1>
      <p className="muted small">Only payments made while signed in to this account are listed.</p>
      {error && <p className="alert" role="alert">{error}</p>}
      {rows === null && !error && <p className="muted">Loading…</p>}
      {rows && rows.length === 0 && (
        <div className="box grey">
          <strong>You have not made any payments</strong>
          <p className="muted small">Payments you make while signed in will appear here. Another person's payment is never shown, even with its reference.</p>
        </div>
      )}
      {rows && rows.length > 0 && (
        <div className="history">
          <div>
            <table className="history-table">
              <thead>
                <tr><th>Date</th><th>Merchant</th><th>Reference</th><th>Amount</th><th>Status</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.reference} className={selected?.reference === r.reference ? "selected" : undefined}>
                    <td>{formatDay(r.created_at)}</td>
                    <td>{r.merchant_name}</td>
                    <td>
                      <button className="link" type="button" onClick={() => open(r.reference)} disabled={selecting === r.reference}
                        aria-label={`Show payment ${r.reference}`}>{r.reference}</button>
                    </td>
                    <td>{money(r.amount)}</td>
                    <td><StatusBadge label={r.status_label} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="history-cards">
              {rows.map((r) => (
                <li key={r.reference}>
                  <button type="button" className="history-card" onClick={() => open(r.reference)}>
                    <span className="row-between"><strong>{money(r.amount)}</strong><StatusBadge label={r.status_label} /></span>
                    <span className="muted small">{r.merchant_name} · {r.reference} · {formatDay(r.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="muted small">Showing {rows.length} of {rows.length}</p>
          </div>
          {selected && <Detail payment={selected} />}
        </div>
      )}
    </>
  );
}

function Detail({ payment }: { payment: PaymentDetail }) {
  return (
    <aside className="box detail" aria-label={`Payment ${payment.reference}`}>
      <div className="view-head">
        <h2 className="small-heading">{money(payment.amount)} to {payment.merchant_name}</h2>
        <StatusBadge label={payment.status_label} />
      </div>
      {payment.status === "unresolved" && (
        <p className="alert" role="status">We are still confirming this payment with the bank. Please don't pay again.</p>
      )}
      <dl className="box">
        <Row label="Reference">{payment.reference}</Row>
        <Row label="Order">{payment.order_reference}</Row>
        {payment.card && <Row label="Card">{brandName(payment.card.brand)} •••• {payment.card.last4}</Row>}
        <Row label="Date">{formatDate(payment.created_at)}</Row>
        {payment.refunded_amount ? <Row label="Refunded">{money(payment.refunded_amount)}</Row> : null}
      </dl>
      <h3 className="small-heading">Timeline</h3>
      <ol className="timeline">
        {payment.timeline.map((t, i) => (
          <li key={i}><span>{t.label}</span><span className="muted small">{formatDate(t.at)}</span></li>
        ))}
        {!payment.refunded_amount && <li className="hollow"><span>Refunds: none</span><span className="muted small">—</span></li>}
      </ol>
    </aside>
  );
}

const DARK = new Set(["Captured", "Authorised"]);
function StatusBadge({ label }: { label: string }) {
  return <span className={`badge${DARK.has(label) ? " dark" : ""}`}>{label}</span>;
}

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString("en-SG", { day: "numeric", month: "short", year: "numeric" });
}

// --- profile and password -------------------------------------------------------------------

function Profile({ me, onSignedOut, onEnded }: { me: Customer; onSignedOut: () => void; onEnded: () => void }) {
  const [error, setError] = useState<string>();
  async function everywhere() {
    try {
      await signOutEverywhere();
      onSignedOut();
    } catch (err) {
      if (asError(err).status === 401) onEnded();
      else setError(asError(err).message);
    }
  }
  return (
    <div className="form">
      <h1>Profile</h1>
      <dl className="box">
        <Row label="Full name">{me.full_name}</Row>
        <Row label="Email">{me.email}</Row>
      </dl>
      {error && <p className="alert" role="alert">{error}</p>}
      <p className="muted small">Lost a device, or signed in on a shared computer? This ends every signed-in session of your account, including this one.</p>
      <button className="btn secondary" type="button" onClick={everywhere}>Sign out on every device</button>
    </div>
  );
}

function PasswordPage({ onEnded, onDone }: { onEnded: () => void; onDone: (message: string) => void }) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (!current) e.current_password = "Enter your current password.";
    if (password.length < MIN_PASSWORD) e.password = `Use at least ${MIN_PASSWORD} characters.`;
    else if (confirm !== password) e.confirm = "The passwords do not match.";
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

function NewPasswordFields({ password, confirm, errors, onPassword, onConfirm }: {
  password: string; confirm: string; errors: Record<string, string>;
  onPassword: (v: string) => void; onConfirm: (v: string) => void;
}) {
  return (
    <>
      <Field label="New password" error={errors.password} id="pw-new">
        <input id="pw-new" type="password" autoComplete="new-password" value={password} onChange={(e) => onPassword(e.target.value)} />
      </Field>
      <Field label="Confirm new password" error={errors.confirm} id="pw-confirm">
        <input id="pw-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => onConfirm(e.target.value)} />
      </Field>
      <p className="muted tiny">At least {MIN_PASSWORD} characters. Saving signs you out on every other device.</p>
    </>
  );
}

// --- C12: account recovery --------------------------------------------------------------------

type ResetStep = { kind: "request" } | { kind: "checking" } | { kind: "set"; email: string } | { kind: "invalid" };

function ResetPage({ token, onSignIn }: { token: string | null; onSignIn: (message?: string) => void }) {
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
    if (password.length < MIN_PASSWORD) e.password = `Use at least ${MIN_PASSWORD} characters.`;
    else if (confirm !== password) e.confirm = "The passwords do not match.";
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
