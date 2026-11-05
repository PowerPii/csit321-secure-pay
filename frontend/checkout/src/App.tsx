// Hosted checkout. Served by the gateway under a strict CSP: no third-party scripts,
// and the browser never decides merchant, amount or currency. Screens follow the Figma
// page "Customer & merchant flows" (C3 to C7, C9). No UI library, to keep the bundle small.
import { useState } from "react";

type Step = "card" | "checking" | "verify" | "approved" | "not_approved";

const screens: Record<Step, { id: string; title: string; todo: string }> = {
  card: { id: "C3", title: "Pay SecurePay Demo Shop", todo: "order summary from GET /checkout/{session}; card form posts once to /card" },
  checking: { id: "C4", title: "Checking your payment", todo: "POST /submit; poll result" },
  verify: { id: "C5", title: "Enter verification code", todo: "code emailed via Mailpit; valid 10 minutes" },
  approved: { id: "C6", title: "Payment approved", todo: "reference + return to shop" },
  not_approved: { id: "C7", title: "Payment not completed", todo: "declined / blocked / screening unavailable, plain words, retry" },
};

export function sessionIdFromPath(path: string): string | null {
  return path.match(/^\/checkout\/([^/]+)/)?.[1] ?? null;
}

export default function App() {
  const [step, setStep] = useState<Step>("card");
  const s = screens[step];
  const sessionId = sessionIdFromPath(window.location.pathname);
  return (
    <main style={{ maxWidth: 420, margin: "0 auto", padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <small>{s.id} · session {sessionId ?? "none"}</small>
      <h1>{s.title}</h1>
      <p>TODO: {s.todo}</p>
      <nav aria-label="dev step switcher">
        {(Object.keys(screens) as Step[]).map((k) => (
          <button key={k} onClick={() => setStep(k)} disabled={k === step}>{screens[k].id}</button>
        ))}
      </nav>
    </main>
  );
}
