import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Session } from "./api";

const SID = "cs_" + "A".repeat(24);

function session(over: Partial<Session> = {}): Session {
  return {
    session_id: SID, status: "created", result: "open", merchant: { name: "Demo Shop" },
    amount: 8990, currency: "SGD", order_reference: "ORD-1042", description: "Wireless mouse × 1", line_items: null,
    reference: null, email_required: false, customer_email_masked: "a•••@example.com", card: null,
    expires_at: new Date(Date.now() + 3600_000).toISOString(), submitted_at: null, authorised_at: null,
    return_url: "https://shop.localhost/orders/1042/return?payment_id=pay_x", verification: null, ...over,
  };
}

function mockFetch(replies: Record<string, () => Response>) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = Object.keys(replies).find((k) => url.endsWith(k))!;
    return replies[key]();
  }));
  return calls;
}

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("checkout page", () => {
  it("shows the order the merchant created (C3)", async () => {
    mockFetch({ [SID]: () => json(session()) });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByText("Paying Demo Shop")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pay S$ 89.90" })).toBeTruthy();
    expect(screen.getByText("Receipt to a•••@example.com")).toBeTruthy();
    expect(screen.getByText("Wireless mouse × 1")).toBeTruthy();
  });

  it("lists the line items with their amounts when the shop sent them", async () => {
    mockFetch({ [SID]: () => json(session({ line_items: [
      { name: "Wireless mouse", quantity: 1, unit_amount: 2990 },
      { name: "USB-C hub", quantity: 2, unit_amount: 3000 },
    ] })) });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByText("USB-C hub × 2")).toBeTruthy();
    expect(screen.getByText("S$ 60.00")).toBeTruthy();
  });

  it("checks the card locally before sending anything", async () => {
    const calls = mockFetch({ [SID]: () => json(session()) });
    render(<App path={`/pay/${SID}`} />);
    fireEvent.click(await screen.findByRole("button", { name: "Pay S$ 89.90" }));
    expect(await screen.findByText("Enter a valid card number.")).toBeTruthy();
    expect(calls).toHaveLength(1); // only the initial GET
  });

  it("sends the card, pays, and shows the approval (C6)", async () => {
    const approved = session({ status: "authorised", result: "approved", reference: "SP-7Q2K-91XD",
      card: { brand: "visa", last4: "4242" }, authorised_at: "2026-11-13T05:00:00Z" });
    const calls = mockFetch({
      "/card": () => json(session({ card: { brand: "visa", last4: "4242" } })),
      "/submit": () => json(approved),
      [SID]: () => json(session()),
    });
    render(<App path={`/pay/${SID}`} />);
    fireEvent.change(await screen.findByLabelText("Card number"), { target: { value: "4242 4242 4242 4242" } });
    fireEvent.change(screen.getByLabelText("Expiry"), { target: { value: "1230" } });
    fireEvent.change(screen.getByLabelText("CVV"), { target: { value: "123" } });
    fireEvent.change(screen.getByLabelText("Name on card"), { target: { value: "Tan Wei Ming" } });
    fireEvent.click(screen.getByRole("button", { name: "Pay S$ 89.90" }));
    expect(await screen.findByText("Payment successful")).toBeTruthy();
    expect(screen.getByText("SP-7Q2K-91XD")).toBeTruthy();
    const cardCall = calls.find((c) => c.url.endsWith("/card"))!;
    expect(cardCall.body).toEqual({ number: "4242424242424242", expiry_month: 12, expiry_year: 2030, cvc: "123" });
  });

  it("explains a decline in plain words (C7)", async () => {
    mockFetch({ [SID]: () => json(session({ status: "declined", result: "declined", reference: "SP-AAAA-BBBB" })) });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByText("Payment declined")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Try another card" }).getAttribute("href")).toContain("payment_id=");
  });

  it("asks the customer not to pay again when the bank did not answer", async () => {
    mockFetch({ [SID]: () => json(session({ status: "unresolved", result: "pending", reference: "SP-AAAA-BBBB" })) });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByText("We're confirming your payment")).toBeTruthy();
  });

  it("shows the result once reconciliation settles a pending payment", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let checks = 0;
      mockFetch({
        [SID]: () => {
          checks += 1;
          return checks < 2
            ? json(session({ status: "unresolved", result: "pending", reference: "SP-AAAA-BBBB" }))
            : json(session({ status: "authorised", result: "approved", reference: "SP-AAAA-BBBB",
                card: { brand: "visa", last4: "0119" }, authorised_at: new Date().toISOString() }));
        },
      });
      render(<App path={`/pay/${SID}`} />);
      expect(await screen.findByText("We're confirming your payment")).toBeTruthy();
      await vi.advanceTimersByTimeAsync(10_000);
      expect(await screen.findByText("Payment successful")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("asks for the emailed code, shows a wrong code, then pays (C5)", async () => {
    const waiting = (attempts: number) => session({
      status: "verification_required", result: "verification_required", reference: "SP-AAAA-BBBB",
      card: { brand: "visa", last4: "4242" },
      verification: { sent_to: "a•••@example.com", code_expires_at: new Date(Date.now() + 600_000).toISOString(),
        attempts_remaining: attempts, resend_available_at: new Date(Date.now() + 30_000).toISOString() },
    });
    let verifyReplies = 0;
    let attempts = 3;
    const calls = mockFetch({
      "/verify": () => {
        verifyReplies += 1;
        if (verifyReplies === 1) {
          attempts = 2;
          return json({ error: { code: "code_incorrect", message: "That code isn't right. 2 attempts left.", param: "code" } }, 400);
        }
        return json(session({ status: "authorised", result: "approved", reference: "SP-AAAA-BBBB", authorised_at: "2026-11-13T05:00:00Z" }));
      },
      [SID]: () => json(waiting(attempts)),
    });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByText("Check your email")).toBeTruthy();
    expect(screen.getByText(/sent to a•••@example.com/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Send a new code in/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: "12a3" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and pay S$ 89.90" }));
    expect(await screen.findByText("Enter the 6-digit code from the email.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: "111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and pay S$ 89.90" }));
    expect(await screen.findByText("That code isn't right. 2 attempts left.")).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/2 attempts left$/)).toBeTruthy());

    fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and pay S$ 89.90" }));
    expect(await screen.findByText("Payment successful")).toBeTruthy();
    expect(calls.filter((c) => c.url.endsWith("/verify")).map((c) => c.body)).toEqual([{ code: "111111" }, { code: "123456" }]);
  });

  it("tells the customer to try later when screening was unavailable", async () => {
    mockFetch({ [SID]: () => json(session({ status: "blocked", result: "unavailable", reference: "SP-AAAA-BBBB" })) });
    render(<App path={`/pay/${SID}`} />);
    expect(await screen.findByText("We couldn't check this payment right now")).toBeTruthy();
    expect(screen.queryByText(/fraud/i)).toBeNull();
  });

  it("handles an unknown link", async () => {
    mockFetch({ [SID]: () => json({ error: { code: "resource_not_found" } }, 404) });
    render(<App path={`/pay/${SID}`} />);
    await waitFor(() => expect(screen.getByText("This checkout link isn't valid")).toBeTruthy());
  });
});
