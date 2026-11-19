// NFR-USE-02 (accessibility pass, 18 Nov 2026): every customer page is scanned with axe-core
// (the engine of the axe DevTools extension) against WCAG 2.2 A and AA, and the keyboard and
// screen-reader behaviour the pass added is checked. jsdom draws nothing, so colour contrast
// and phone width are checked in a real browser instead (docs/test-report/ACCESSIBILITY.md).
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import Account from "./Account";
import App from "./App";
import GuestStatus from "./GuestStatus";
import type { Session } from "./api";
import { focusFirstErrorOnSubmit } from "./ui";

const SID = "cs_" + "B".repeat(24);
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function session(over: Partial<Session> = {}): Session {
  return {
    session_id: SID, status: "created", result: "open", merchant: { name: "Volt & Co." },
    amount: 239900, currency: "SGD", order_reference: "ORD-1018", description: null,
    line_items: [{ name: "Laptop 14", quantity: 1, unit_amount: 239900 }],
    reference: "SP-AAAA-BBBB", email_required: true, customer_email_masked: null, card: { brand: "visa", last4: "4242" },
    expires_at: new Date(Date.now() + 3600_000).toISOString(), submitted_at: null, authorised_at: "2026-11-18T03:00:00Z",
    return_url: "https://shop.localhost/orders/1018/return", verification: null, ...over,
  };
}

function serve(replies: Record<string, () => Response>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const key = Object.keys(replies).find((k) => url.endsWith(k));
    return key ? replies[key]() : json({ error: { code: "sign_in_required", message: "Sign in." } }, 401);
  }));
}

/** axe-core over the rendered page; returns "rule: target" lines for any violation. */
async function violations(): Promise<string[]> {
  const result = await axe.run(document.body, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false } }, // needs a real renderer; see ACCESSIBILITY.md
  });
  return result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")}`));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("axe scan of the customer pages (NFR-USE-02)", () => {
  it("finds no WCAG A or AA issue on the card form, code, approved, declined and being-checked pages", async () => {
    const pages: [Session, string][] = [
      [session(), "Pay S$ 2,399.00"],
      [session({ result: "verification_required", verification: {
        sent_to: "a•••@example.com", code_expires_at: new Date(Date.now() + 600_000).toISOString(),
        attempts_remaining: 3, resend_available_at: null } }), "Check your email"],
      [session({ result: "approved", status: "authorised" }), "Payment successful"],
      [session({ result: "declined", status: "declined" }), "Payment declined"],
      [session({ result: "pending", status: "unresolved" }), "We're checking your payment"],
    ];
    for (const [s, text] of pages) {
      serve({ [SID]: () => json(s) });
      const view = render(<App path={`/pay/${SID}`} />);
      await screen.findAllByText(text);
      expect({ page: text, issues: await violations() }).toEqual({ page: text, issues: [] });
      view.unmount();
    }
  });

  it("finds no issue on the guest status check and the account sign-in page", async () => {
    serve({});
    const guest = render(<GuestStatus search="" />);
    await screen.findByRole("heading", { name: "Check a payment" });
    expect(await violations()).toEqual([]);
    guest.unmount();
    render(<Account path="/account/sign-in" hash="" />);
    await screen.findByRole("heading", { name: "Sign in" });
    expect(await violations()).toEqual([]);
  });
});

describe("keyboard and screen-reader behaviour", () => {
  it("links each error to its field, moves focus to the first one and stays clean under axe", async () => {
    focusFirstErrorOnSubmit();
    serve({ [SID]: () => json(session()) });
    render(<App path={`/pay/${SID}`} />);
    fireEvent.click(await screen.findByRole("button", { name: /Pay S\$/ }));
    const email = screen.getByLabelText("Email (for your receipt)");
    expect(email.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(email.getAttribute("aria-describedby")!)?.textContent).toBe("Enter a valid email address.");
    const number = screen.getByLabelText("Card number");
    expect(number.getAttribute("aria-describedby")).toBe("card-brands number-error");
    expect(screen.getByLabelText(/I agree that SecurePay/).getAttribute("aria-invalid")).toBe("true");
    await waitFor(() => expect(document.activeElement).toBe(email));
    expect(await violations()).toEqual([]);
  });

  it("names the card form with a heading for screen readers", async () => {
    serve({ [SID]: () => json(session()) });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Pay S$ 2,399.00 to Volt & Co. by card" })).toBeTruthy();
  });

  it("lets the customer stop the automatic return after a successful payment (WCAG 2.2.1)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    serve({ [SID]: () => json(session({ result: "approved", status: "authorised" })) });
    render(<App path={`/pay/${SID}`} />);
    fireEvent.click(await screen.findByRole("button", { name: "Stay on this page" }));
    await act(() => vi.advanceTimersByTimeAsync(8000));
    expect(assign).not.toHaveBeenCalled();
    expect(screen.getByText("You can stay here as long as you like.")).toBeTruthy();
  });

  it("does not re-announce the countdown: the step panel is no longer a live region", async () => {
    serve({ [SID]: () => json(session()) });
    const { container } = render(<App path={`/pay/${SID}`} />);
    await screen.findByRole("button", { name: /Pay S\$/ });
    expect(container.querySelector("[aria-live]")).toBeNull();
  });

  it("moves arrow-key focus between the sign-in and register tabs", async () => {
    serve({});
    render(<Account path="/account/sign-in" hash="" />);
    const signIn = await screen.findByRole("tab", { name: "Sign in" });
    signIn.focus();
    fireEvent.keyDown(signIn, { key: "ArrowRight" });
    const register = screen.getByRole("tab", { name: "Register" });
    expect(register.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(register);
    expect(register.getAttribute("aria-controls")).toBe("panel-register");
  });
});
