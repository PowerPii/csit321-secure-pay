import { Field, Row } from "./ui";
// Hosted checkout. Served by the gateway under a strict CSP: no third-party scripts, and
// the browser never decides merchant, amount or currency. Screens follow the Figma page
// "Customer & merchant flows": C3 card entry, C4 checking, C5 verification code, C6 approved,
// C7 not completed. No UI library, to keep the bundle small and auditable.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { getMe, type Customer } from "./accountApi";
import { ConsentBox } from "./Privacy";
import { addCard, ApiError, getSession, resendCode, submit, verify, type Session } from "./api";
import {
  brandName,
  countdown,
  digitsOnly,
  formatCardNumber,
  formatDate,
  formatExpiry,
  luhnOk,
  money,
  parseExpiry,
  sessionIdFromPath,
} from "./format";
import { Brand } from "./Brand";

export { sessionIdFromPath };

const AUTO_RETURN_SECONDS = 5;
// While the bank's answer is unknown the gateway checks with it (30 s, then 1, 2, 5 ... min);
// the page asks the gateway again on this interval so it shows the result once it is known.
const PENDING_POLL_MS = 10_000;

type View =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "session"; session: Session; checking: boolean; error?: string };

export default function App({ path = window.location.pathname }: { path?: string }) {
  const sessionId = sessionIdFromPath(path);
  const [view, setView] = useState<View>(sessionId ? { kind: "loading" } : { kind: "missing" });

  useEffect(() => {
    if (!sessionId) return;
    getSession(sessionId)
      .then((session) => setView({ kind: "session", session, checking: false }))
      .catch(() => setView({ kind: "missing" }));
  }, [sessionId]);

  const pending = view.kind === "session" && view.session.result === "pending";
  useEffect(() => {
    if (!sessionId || !pending) return;
    const t = window.setInterval(() => {
      getSession(sessionId)
        .then((s) => setView((v) => (v.kind === "session" ? { ...v, session: s } : v)))
        .catch(() => undefined);
    }, PENDING_POLL_MS);
    return () => window.clearInterval(t);
  }, [sessionId, pending]);

  if (view.kind === "loading") {
    return <Shell status="Secure checkout"><p className="muted center">Loading…</p></Shell>;
  }
  if (view.kind === "missing" || !sessionId) {
    return (
      <Shell status="Secure checkout">
        <div className="panel-right only">
          <div className="result">
            <h1>This checkout link isn't valid</h1>
            <p className="muted">Go back to the shop and start the payment again. No money was taken.</p>
          </div>
        </div>
      </Shell>
    );
  }

  const { session, checking, error } = view;
  const update = (s: Session, c = false, e?: string) =>
    setView({ kind: "session", session: s, checking: c, error: e });
  const inFlight = checking || session.result === "processing";

  let status = "Secure checkout";
  let body: ReactNode;
  if (inFlight) {
    body = <Checking session={session} />;
  } else if (session.result === "open") {
    body = <CardForm sessionId={sessionId} session={session} onUpdate={update} formError={error} />;
  } else if (session.result === "verification_required") {
    status = "Verify your payment";
    body = <VerifyCode sessionId={sessionId} session={session} onUpdate={update} />;
  } else if (session.result === "approved") {
    status = "Payment complete";
    body = <Approved session={session} />;
  } else {
    status = "Payment not completed";
    body = <NotCompleted session={session} />;
  }

  return (
    <Shell status={status}>
      <OrderSummary session={session} />
      <section className="panel-right" aria-live="polite">{body}</section>
    </Shell>
  );
}

export function Shell({ status, children }: { status: string; children: ReactNode }) {
  return (
    <>
      <header className="topbar">
        <Brand />
        <span className="topbar-status">{status}</span>
      </header>
      <main className="layout">{children}</main>
    </>
  );
}

function OrderSummary({ session }: { session: Session }) {
  return (
    <aside className="panel-left" aria-label="Order summary">
      <div>
        <p className="muted">Paying {session.merchant.name}</p>
        <p className="amount">{money(session.amount)}</p>
        <p className="muted small">
          Order {session.order_reference} · {session.currency}
        </p>
        <dl className="lines">
          {session.line_items
            ? session.line_items.map((item, i) => (
                <div className="row" key={i}>
                  <dt>{item.name} × {item.quantity}</dt>
                  <dd>{money(item.unit_amount * item.quantity)}</dd>
                </div>
              ))
            : session.description && (
                <div className="row">
                  <dt>{session.description}</dt>
                </div>
              )}
          <div className="row total">
            <dt>Total</dt>
            <dd>{money(session.amount)}</dd>
          </div>
        </dl>
      </div>
      <p className="muted small lock">
        <LockIcon /> Secured by SecurePay. Card details are encrypted and never shared with the shop.
      </p>
    </aside>
  );
}

function CardForm({
  sessionId,
  session,
  onUpdate,
  formError,
}: {
  sessionId: string;
  session: Session;
  onUpdate: (s: Session, checking?: boolean, error?: string) => void;
  formError?: string;
}) {
  const [email, setEmail] = useState("");
  const [number, setNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [name, setName] = useState(""); // shown as in the wireframe; not sent, the simulator does not need it
  const [errors, setErrors] = useState<Record<string, string>>(formError ? { form: formError } : {});
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [consent, setConsent] = useState(false);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    // Signed in to a SecurePay account on this browser (C10): the payment joins its history
    // (FR-ACC-04) and the receipt email is filled in. Signed out, nothing changes.
    let live = true;
    getMe()
      .then((c) => {
        if (!live) return;
        setCustomer(c);
        setEmail((e) => e || c.email);
      })
      .catch(() => undefined);
    return () => { live = false; };
  }, []);

  useEffect(() => {
    // The session ended while the page was open: reload it to show the expired state.
    if (Date.parse(session.expires_at) <= now) getSession(sessionId).then((s) => onUpdate(s)).catch(() => undefined);
  }, [now, session.expires_at, sessionId, onUpdate]);

  function check(): Record<string, string> {
    const e: Record<string, string> = {};
    if (session.email_required && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = "Enter a valid email address.";
    if (!luhnOk(digitsOnly(number))) e.number = "Enter a valid card number.";
    if (!parseExpiry(expiry)) e.expiry = "Enter the expiry date as MM / YY.";
    if (!/^\d{3,4}$/.test(cvc)) e.cvc = "Enter the 3 or 4 digit security code.";
    if (!name.trim()) e.name = "Enter the name shown on the card.";
    if (!consent) e.privacy_consent = "Agree to the privacy notice to pay.";
    return e;
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    const found = check();
    setErrors(found);
    if (Object.keys(found).length || busy) return;
    const exp = parseExpiry(expiry)!;
    setBusy(true);
    let current = session;
    try {
      current = await addCard(sessionId, {
        number: digitsOnly(number),
        expiry_month: exp.month,
        expiry_year: exp.year,
        cvc,
        privacy_consent: true,
        ...(session.email_required ? { email } : {}),
      });
    } catch (err) {
      const e = err instanceof ApiError ? err : new ApiError(0, "unknown_error", "Something went wrong.");
      if (e.status === 410 || e.status === 409) {
        getSession(sessionId).then((s) => onUpdate(s)).catch(() => undefined);
        return;
      }
      const field = { expiry_month: "expiry", expiry_year: "expiry" }[e.param ?? ""] ?? e.param ?? "form";
      setErrors({ [field]: e.message });
      setBusy(false);
      return;
    }
    // The card is in the vault; from here the form is replaced by "Checking your payment".
    onUpdate(current, true);
    try {
      onUpdate(await submit(sessionId));
    } catch (err) {
      const e = err instanceof ApiError ? err : new ApiError(0, "unknown_error", "Something went wrong.");
      // Reload: the payment may have gone ahead even if this reply was lost.
      getSession(sessionId)
        .then((s) => onUpdate(s, false, s.result === "open" ? e.message : undefined))
        .catch(() => onUpdate(current, false, e.message));
    }
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      {errors.form && <p className="alert" role="alert">{errors.form}</p>}
      {customer && (
        <p className="muted small" role="status">
          Signed in as {customer.full_name}. This payment will appear in your payment history.
        </p>
      )}
      {session.email_required ? (
        <Field label="Email (for your receipt)" error={errors.email} id="email">
          <input id="email" type="email" autoComplete="email" placeholder="you@example.com"
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
      ) : (
        session.customer_email_masked && (
          <p className="muted small">Receipt to {session.customer_email_masked}</p>
        )
      )}
      <Field label="Card number" error={errors.number} id="number">
        <input id="number" inputMode="numeric" autoComplete="cc-number" placeholder="1234 5678 9012 3456"
          value={number} onChange={(e) => setNumber(formatCardNumber(e.target.value))} />
      </Field>
      <div className="pair">
        <Field label="Expiry" error={errors.expiry} id="expiry">
          <input id="expiry" inputMode="numeric" autoComplete="cc-exp" placeholder="MM / YY"
            value={expiry} onChange={(e) => setExpiry(formatExpiry(e.target.value))} />
        </Field>
        <Field label="CVV" error={errors.cvc} id="cvc">
          <input id="cvc" inputMode="numeric" autoComplete="cc-csc" placeholder="123" maxLength={4}
            value={cvc} onChange={(e) => setCvc(digitsOnly(e.target.value))} />
        </Field>
      </div>
      <Field label="Name on card" error={errors.name} id="name">
        <input id="name" autoComplete="cc-name" placeholder="As shown on card"
          value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <ConsentBox checked={consent} onChange={setConsent} error={errors.privacy_consent}>
        I agree that SecurePay uses my details to process and protect this payment, as the privacy notice says.
      </ConsentBox>
      <button className="btn primary" type="submit" disabled={busy}>
        Pay {money(session.amount)}
      </button>
      <a className="btn secondary" href={session.return_url}>
        Cancel and return to {session.merchant.name}
      </a>
      <p className="muted tiny">
        Session expires in {countdown(session.expires_at, now)} · Card details are encrypted and never shared with the shop.
      </p>
    </form>
  );
}

function VerifyCode({
  sessionId,
  session,
  onUpdate,
}: {
  sessionId: string;
  session: Session;
  onUpdate: (s: Session, checking?: boolean, error?: string) => void;
}) {
  const v = session.verification;
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    // The checkout session ended while waiting: reload to show the result.
    if (Date.parse(session.expires_at) <= now) getSession(sessionId).then((s) => onUpdate(s)).catch(() => undefined);
  }, [now, session.expires_at, sessionId, onUpdate]);

  const fail = (err: unknown) => {
    const e = err instanceof ApiError ? err : new ApiError(0, "unknown_error", "Something went wrong.");
    setError(e.message);
    setNotice(undefined);
    // Refresh attempts left and the resend timer; the attempt may have ended too.
    getSession(sessionId).then((s) => onUpdate(s)).catch(() => undefined);
  };

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code from the email.");
      return;
    }
    if (busy) return;
    setBusy(true);
    setError(undefined);
    setVerifying(true); // "Checking your payment" while the bank answers
    try {
      onUpdate(await verify(sessionId, code));
    } catch (err) {
      setVerifying(false);
      setCode("");
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setBusy(true);
    try {
      const s = await resendCode(sessionId);
      setError(undefined);
      setCode("");
      setNotice(`We sent a new code to ${s.verification?.sent_to ?? "your email"}. Earlier codes no longer work.`);
      onUpdate(s);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  if (!v || verifying) return <Checking session={session} />;
  const codeLeft = Date.parse(v.code_expires_at) - now;
  const resendIn = v.resend_available_at ? Date.parse(v.resend_available_at) - now : null;

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <h1>Check your email</h1>
      <p className="muted">
        To protect your card, enter the 6-digit code we sent to {v.sent_to ?? "your email"}.
      </p>
      {notice && <p className="muted small" role="status">{notice}</p>}
      <Field label="Verification code" error={error} id="code">
        <input id="code" inputMode="numeric" autoComplete="one-time-code" placeholder="123456"
          maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
      </Field>
      <p className="muted tiny">
        {codeLeft > 0 ? `Code expires in ${countdown(v.code_expires_at, now)}` : "This code has expired. Ask for a new one."}
        {" · "}
        {v.attempts_remaining} attempt{v.attempts_remaining === 1 ? "" : "s"} left
      </p>
      <button className="btn primary" type="submit" disabled={busy}>
        Verify and pay {money(session.amount)}
      </button>
      {resendIn === null ? (
        <p className="muted tiny">No more codes can be sent for this payment.</p>
      ) : (
        <button className="btn secondary" type="button" onClick={onResend} disabled={busy || resendIn > 0}>
          {resendIn > 0 ? `Send a new code in ${Math.ceil(resendIn / 1000)} s` : "Send a new code"}
        </button>
      )}
      <a className="btn secondary" href={session.return_url}>
        Cancel and return to {session.merchant.name}
      </a>
    </form>
  );
}

function Checking({ session }: { session: Session }) {
  return (
    <div className="result">
      <span className="spinner" aria-hidden="true" />
      <h1>Checking your payment…</h1>
      <p className="muted">This usually takes a second. Please don't close this page.</p>
      <dl className="box grey">
        <Row label="Merchant">{session.merchant.name}</Row>
        <Row label="Amount">{money(session.amount)}</Row>
        {session.card && <Row label="Card">{brandName(session.card.brand)} •••• {session.card.last4}</Row>}
      </dl>
    </div>
  );
}

function Approved({ session }: { session: Session }) {
  const [left, setLeft] = useState(AUTO_RETURN_SECONDS);
  const returned = useRef(false);
  useEffect(() => {
    const t = window.setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(t);
  }, []);
  useEffect(() => {
    if (left === 0 && !returned.current) {
      returned.current = true;
      window.location.assign(session.return_url);
    }
  }, [left, session.return_url]);

  return (
    <div className="result">
      <CheckIcon />
      <h1>Payment successful</h1>
      <p className="muted">{money(session.amount)} paid to {session.merchant.name}</p>
      <dl className="box">
        <Row label="Reference">{session.reference}</Row>
        {session.authorised_at && <Row label="Date">{formatDate(session.authorised_at)}</Row>}
        {session.card && <Row label="Card">{brandName(session.card.brand)} •••• {session.card.last4}</Row>}
        <Row label="Status"><span className="badge dark">Authorised</span></Row>
      </dl>
      <a className="btn primary" href={session.return_url}>Return to {session.merchant.name}</a>
      <p className="muted tiny">Returning you automatically in {left} s</p>
    </div>
  );
}

const NOT_COMPLETED: Record<string, { icon: "cross" | "warn" | "clock"; title: string; text: (m: string) => string; button: (m: string) => string; badge: string }> = {
  declined: {
    icon: "cross",
    title: "Payment declined",
    text: () => "Your bank declined this payment. No money was taken. You can try a different card.",
    button: () => "Try another card",
    badge: "Declined by simulated bank",
  },
  not_completed: {
    icon: "warn",
    title: "We couldn't complete this payment",
    text: (m) => `No money was taken. If you need help, please contact ${m}.`,
    button: (m) => `Return to ${m}`,
    badge: "Not completed",
  },
  pending: {
    icon: "clock",
    title: "We're confirming your payment",
    text: (m) => `We didn't hear back from the bank in time. Please don't pay again. This page updates as soon as we know the result, and ${m} will confirm it too.`,
    button: (m) => `Return to ${m}`,
    badge: "Awaiting bank confirmation",
  },
  unavailable: {
    icon: "warn",
    title: "We couldn't check this payment right now",
    text: (m) => `No money was taken. Please try again in a few minutes, or return to ${m}.`,
    button: (m) => `Return to ${m}`,
    badge: "Not completed · try again later",
  },
  expired: {
    icon: "clock",
    title: "This checkout has ended",
    text: (m) => `No money was taken. Return to ${m} to start the payment again.`,
    button: (m) => `Return to ${m}`,
    badge: "Checkout expired",
  },
  cancelled: {
    icon: "warn",
    title: "This payment was cancelled",
    text: () => "No money was taken.",
    button: (m) => `Return to ${m}`,
    badge: "Cancelled",
  },
};

function NotCompleted({ session }: { session: Session }) {
  const v = NOT_COMPLETED[session.result] ?? NOT_COMPLETED.not_completed;
  const m = session.merchant.name;
  return (
    <div className="result card-result">
      <h1 className="with-icon">
        {v.icon === "cross" ? <CrossIcon /> : v.icon === "warn" ? <WarnIcon /> : <ClockIcon />}
        {v.title}
      </h1>
      <p className="muted">{v.text(m)}</p>
      {session.reference && <p className="muted small">Reference {session.reference}</p>}
      <a className={`btn ${session.result === "declined" ? "primary" : "secondary"}`} href={session.return_url}>
        {v.button(m)}
      </a>
      <span className="badge">{v.badge}</span>
    </div>
  );
}

const svg = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, "aria-hidden": true } as const;
const LockIcon = () => <svg {...svg} width={14} height={14}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>;
const CheckIcon = () => <svg {...svg} width={56} height={56} className="big-icon"><circle cx="12" cy="12" r="10" /><path d="m8 12 3 3 5-6" /></svg>;
const CrossIcon = () => <svg {...svg}><circle cx="12" cy="12" r="10" /><path d="m9 9 6 6m0-6-6 6" /></svg>;
const WarnIcon = () => <svg {...svg}><path d="M12 3 2 21h20L12 3z" /><path d="M12 10v5m0 3v.01" /></svg>;
const ClockIcon = () => <svg {...svg}><circle cx="12" cy="12" r="10" /><path d="M12 7v5l3 2" /></svg>;
