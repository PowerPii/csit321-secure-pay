// Hosted checkout. Served by the gateway under a strict CSP: no third-party scripts, and
// the browser never decides merchant, amount or currency. Screens follow the Figma page
// "Customer & merchant flows": C3 card entry, C4 checking, C6 approved, C7 not completed.
// C5 (verification code) arrives with screening in sprint 4. No UI library, to keep the
// bundle small and auditable.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { addCard, ApiError, getSession, submit, type Session } from "./api";
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

export { sessionIdFromPath };

const AUTO_RETURN_SECONDS = 5;

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

function Shell({ status, children }: { status: string; children: ReactNode }) {
  return (
    <>
      <header className="topbar">
        <span className="brand">SecurePay</span>
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
          {session.description && (
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

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
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

function Field({ label, error, id, children }: { label: string; error?: string; id: string; children: ReactNode }) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <span className="error" role="alert">{error}</span>}
    </div>
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
    text: (m) => `We didn't hear back from the bank in time. Please don't pay again: ${m} will confirm the result once we know it.`,
    button: (m) => `Return to ${m}`,
    badge: "Awaiting bank confirmation",
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

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const svg = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, "aria-hidden": true } as const;
const LockIcon = () => <svg {...svg} width={14} height={14}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>;
const CheckIcon = () => <svg {...svg} width={56} height={56} className="big-icon"><circle cx="12" cy="12" r="10" /><path d="m8 12 3 3 5-6" /></svg>;
const CrossIcon = () => <svg {...svg}><circle cx="12" cy="12" r="10" /><path d="m9 9 6 6m0-6-6 6" /></svg>;
const WarnIcon = () => <svg {...svg}><path d="M12 3 2 21h20L12 3z" /><path d="M12 10v5m0 3v.01" /></svg>;
const ClockIcon = () => <svg {...svg}><circle cx="12" cy="12" r="10" /><path d="M12 7v5l3 2" /></svg>;
