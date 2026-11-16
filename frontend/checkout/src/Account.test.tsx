import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Account, { pageFromPath, tokenFromHash } from "./Account";

const ME = { id: "cus_x", full_name: "Jane Tan", email: "jane@example.com", idle_minutes: 15 };
const ROW = {
  reference: "SP-7QK2-91XD", merchant_name: "Demo Shop", amount: 8990, currency: "SGD",
  status: "captured", status_label: "Captured", created_at: "2026-11-02T06:52:00Z",
};
const TOKEN = "t".repeat(43);

type Reply = () => Response;
function mockFetch(replies: Record<string, Reply | Reply[]>) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = Object.keys(replies).find((k) => url.endsWith(k));
    if (!key) throw new Error(`unexpected ${url}`);
    const r = replies[key];
    return Array.isArray(r) ? r.shift()!() : r();
  }));
  return calls;
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
const signedOut = () => json({ error: { code: "sign_in_required", message: "x" } }, 401);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("account helpers", () => {
  it("maps paths to pages", () => {
    expect(pageFromPath("/account")).toBe("sign-in");
    expect(pageFromPath("/account/payments")).toBe("payments");
    expect(pageFromPath("/account/reset/")).toBe("reset");
    expect(pageFromPath("/account/whatever")).toBe("sign-in");
  });

  it("reads only a well-formed token from the fragment", () => {
    expect(tokenFromHash(`#token=${TOKEN}`)).toBe(TOKEN);
    expect(tokenFromHash("#token=<script>")).toBeNull();
    expect(tokenFromHash("")).toBeNull();
  });
});

describe("sign in and register (C10)", () => {
  it("shows the generic error when the password is wrong", async () => {
    const calls = mockFetch({
      "/me": signedOut,
      "/sign-in": () => json({ error: { code: "invalid_credentials", message: "Email or password is incorrect. After 5 failed attempts, sign-in is locked for 15 minutes." } }, 401),
    });
    render(<Account path="/account/sign-in" hash="" />);
    fireEvent.change(await screen.findByLabelText("Email", { selector: "#signin-email" }), { target: { value: "jane@example.com" } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "#signin-password" }), { target: { value: "not it at all" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Email or password is incorrect")).toBeTruthy();
    expect(screen.getByText(/After 5 failed attempts/)).toBeTruthy();
    expect(calls[1].body).toEqual({ email: "jane@example.com", password: "not it at all", remember: false });
  });

  it("checks the password length and match before registering", async () => {
    const calls = mockFetch({ "/me": signedOut });
    render(<Account path="/account/sign-in" hash="" />);
    fireEvent.change(await screen.findByLabelText("Full name"), { target: { value: "Jane Tan" } });
    fireEvent.change(screen.getByLabelText("Email", { selector: "#reg-email" }), { target: { value: "jane@example.com" } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "#reg-password" }), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 12 characters.", { selector: ".error" })).toBeTruthy();
    expect(calls).toHaveLength(1);
  });

  it("shows the already-registered error under the email field", async () => {
    mockFetch({
      "/me": signedOut,
      "/register": () => json({ error: { code: "email_taken", param: "email", message: "This email is already registered. Sign in or reset your password." } }, 409),
    });
    render(<Account path="/account/sign-in" hash="" />);
    fireEvent.change(await screen.findByLabelText("Full name"), { target: { value: "Jane Tan" } });
    fireEvent.change(screen.getByLabelText("Email", { selector: "#reg-email" }), { target: { value: "jane@example.com" } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "#reg-password" }), { target: { value: "correct horse battery 7" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "correct horse battery 7" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/already registered/)).toBeTruthy();
  });
});

describe("payment history (C11)", () => {
  it("lists payments and opens one with its timeline", async () => {
    mockFetch({
      "/me": () => json(ME),
      "/payments": () => json({ data: [ROW], has_more: false }),
      [`/payments/${ROW.reference}`]: () => json({
        ...ROW, order_reference: "#1042", card: { brand: "visa", last4: "3456" }, refunded_amount: 0,
        timeline: [{ at: ROW.created_at, label: "Payment started" }, { at: ROW.created_at, label: "Charged" }],
      }),
    });
    render(<Account path="/account/payments" hash="" />);
    expect(await screen.findByRole("heading", { name: "Payment history" })).toBeTruthy();
    expect(screen.getByText(/Jane Tan ·/)).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: `Show payment ${ROW.reference}` }));
    expect(await screen.findByText("Visa •••• 3456")).toBeTruthy();
    expect(screen.getByText("#1042")).toBeTruthy();
    expect(screen.getByText("Refunds: none")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    mockFetch({ "/me": () => json(ME), "/payments": () => json({ data: [], has_more: false }) });
    render(<Account path="/account/payments" hash="" />);
    expect(await screen.findByText("You have not made any payments")).toBeTruthy();
  });

  it("sends a signed-out visitor to the sign-in page", async () => {
    mockFetch({ "/me": signedOut });
    render(<Account path="/account/payments" hash="" />);
    expect(await screen.findByRole("button", { name: "Create account" })).toBeTruthy();
  });
});

describe("account recovery (C12)", () => {
  it("gives the same message after asking for a link", async () => {
    const message = "If an account exists for this email, a reset link is on its way. The link works once, for 30 minutes.";
    mockFetch({ "/me": signedOut, "/password-reset/request": () => json({ message }, 202) });
    render(<Account path="/account/reset" hash="" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "jane@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/a reset link is on its way/)).toBeTruthy();
  });

  it("sets a new password from the emailed link", async () => {
    const calls = mockFetch({
      "/me": signedOut,
      "/password-reset/check": () => json({ email: "jane@example.com" }),
      "/password-reset/confirm": () => json({ email: "jane@example.com", message: "Your password has been changed. Sign in with the new password." }),
    });
    render(<Account path="/account/reset" hash={`#token=${TOKEN}`} />);
    expect(await screen.findByText(/For jane@example.com/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a brand new passphrase" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "a brand new passphrase" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByText(/Your password has been changed/)).toBeTruthy();
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/confirm"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/confirm"))!.body).toEqual({ token: TOKEN, password: "a brand new passphrase" });
  });

  it("shows the used-or-expired state for a dead link", async () => {
    mockFetch({
      "/me": signedOut,
      "/password-reset/check": () => json({ error: { code: "link_invalid", message: "x" } }, 400),
    });
    render(<Account path="/account/reset" hash={`#token=${TOKEN}`} />);
    expect(await screen.findByText("This reset link can no longer be used")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Request a new link" }));
    expect(await screen.findByRole("button", { name: "Send reset link" })).toBeTruthy();
  });
});
