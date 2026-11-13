import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Session } from "./api";

const SID = "cs_" + "A".repeat(24);

function session(over: Partial<Session> = {}): Session {
  return {
    session_id: SID, status: "created", result: "open", merchant: { name: "Demo Shop" },
    amount: 8990, currency: "SGD", order_reference: "ORD-1042", description: "Wireless mouse × 1",
    reference: null, email_required: false, customer_email_masked: "a•••@example.com", card: null,
    expires_at: new Date(Date.now() + 3600_000).toISOString(), submitted_at: null, authorised_at: null,
    return_url: "https://shop.localhost/orders/1042/return?payment_id=pay_x", ...over,
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

  it("handles an unknown link", async () => {
    mockFetch({ [SID]: () => json({ error: { code: "resource_not_found" } }, 404) });
    render(<App path={`/pay/${SID}`} />);
    await waitFor(() => expect(screen.getByText("This checkout link isn't valid")).toBeTruthy());
  });
});
