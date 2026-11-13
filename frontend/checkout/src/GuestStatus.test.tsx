import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GuestStatus, { referenceFromSearch } from "./GuestStatus";
import type { GuestPayment } from "./guestApi";

const CHALLENGE = "gsc_" + "A".repeat(24);
const MESSAGE = "If the details match a payment, we have emailed a 6-digit code to that address. It is valid for 10 minutes.";

const payment: GuestPayment = {
  reference: "SP-7KQ4-M2XD", merchant_name: "Demo Shop", amount: 4590, currency: "SGD",
  status: "captured", status_label: "Paid", card: { brand: "visa", last4: "4242" }, refunded_amount: 0,
  created_at: "2026-11-13T04:30:00Z",
  timeline: [
    { at: "2026-11-13T04:30:00Z", label: "Payment started" },
    { at: "2026-11-13T04:31:12Z", label: "Approved by the bank" },
    { at: "2026-11-14T02:00:01Z", label: "Charged" },
  ],
};

type Reply = () => Response;
function mockFetch(replies: Record<string, Reply | Reply[]>) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = Object.keys(replies).find((k) => url.endsWith(k))!;
    const r = replies[key];
    return Array.isArray(r) ? r.shift()!() : r();
  }));
  return calls;
}

const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...headers } });
const noSession = () => json({ error: { code: "status_session_missing", message: "x" } }, 401);
const codeSent = () => json({ challenge_id: CHALLENGE, message: MESSAGE, expires_in_seconds: 600 }, 202);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("guest status page (C9)", () => {
  it("fills the reference from the receipt link only", () => {
    expect(referenceFromSearch("?ref=sp-7kq4-m2xd")).toBe("SP-7KQ4-M2XD");
    expect(referenceFromSearch("?ref=<script>")).toBe("");
    expect(referenceFromSearch("")).toBe("");
  });

  it("asks for a code, then shows the payment after the right code", async () => {
    const calls = mockFetch({ "/payment": noSession, "/code": codeSent, "/verify": () => json(payment) });
    render(<GuestStatus search="?ref=SP-7KQ4-M2XD" />);
    const ref = (await screen.findByLabelText("Payment reference")) as HTMLInputElement;
    expect(ref.value).toBe("SP-7KQ4-M2XD");
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "alex@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Email me a code" }));
    expect(await screen.findByText(/Step 2/)).toBeTruthy();
    expect(screen.getByText(new RegExp(MESSAGE.slice(0, 30)))).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Code from the email"), { target: { value: "481072" } });
    fireEvent.click(screen.getByRole("button", { name: "View payment status" }));
    expect(await screen.findByText("S$ 45.90 to Demo Shop")).toBeTruthy();
    expect(screen.getByText("Paid")).toBeTruthy();
    expect(screen.getByText("Charged")).toBeTruthy();
    expect(screen.getByText("Visa •••• 4242")).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/code"))!.body).toEqual({ reference: "SP-7KQ4-M2XD", email: "alex@example.com" });
    expect(calls.find((c) => c.url.endsWith("/verify"))!.body).toEqual({ challenge_id: CHALLENGE, code: "481072" });
  });

  it("shows tries left after a wrong code, and the lock after the third", async () => {
    mockFetch({
      "/payment": noSession,
      "/code": codeSent,
      "/verify": [
        () => json({ error: { code: "code_incorrect", message: "That code is not right. You have 2 tries left.", param: "code" }, attempts_remaining: 2 }, 400),
        () => json({ error: { code: "status_check_locked", message: "Too many wrong codes. Try again after 15:47." } }, 429, { "Retry-After": "900" }),
      ],
    });
    render(<GuestStatus search="?ref=SP-7KQ4-M2XD" />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "alex@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Email me a code" }));
    const code = await screen.findByLabelText("Code from the email");
    fireEvent.change(code, { target: { value: "111111" } });
    fireEvent.click(screen.getByRole("button", { name: "View payment status" }));
    expect(await screen.findByText("That code is not right. You have 2 tries left.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Code from the email"), { target: { value: "222222" } });
    fireEvent.click(screen.getByRole("button", { name: "View payment status" }));
    expect(await screen.findByText("Status check locked for 15 minutes")).toBeTruthy();
    expect(screen.getByText(/Try again after 15:47/)).toBeTruthy();
  });

  it("opens straight to the payment while the 15-minute view lasts, and Done ends it", async () => {
    const calls = mockFetch({ "/payment": () => json(payment), "/sign-out": () => new Response(null, { status: 204 }) });
    render(<GuestStatus search="" />);
    expect(await screen.findByText("S$ 45.90 to Demo Shop")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText(/left the payment view/)).toBeTruthy();
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/sign-out"))).toBe(true));
  });

  it("warns not to pay again while the bank's answer is unknown", async () => {
    mockFetch({ "/payment": () => json({ ...payment, status: "unresolved", status_label: "Being checked - do not pay again" }) });
    render(<GuestStatus search="" />);
    expect(await screen.findByText(/Please don't pay again/)).toBeTruthy();
  });

  it("checks the form before calling the API", async () => {
    const calls = mockFetch({ "/payment": noSession });
    render(<GuestStatus search="" />);
    fireEvent.click(await screen.findByRole("button", { name: "Email me a code" }));
    expect(screen.getByText("Enter the payment reference from your receipt.")).toBeTruthy();
    expect(screen.getByText("Enter the email address you paid with.")).toBeTruthy();
    expect(calls.filter((c) => c.url.endsWith("/code"))).toHaveLength(0);
  });
});
