// Webhook delivery log and Resend (extends FR-TXN-07).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { expectAccessible } from "./a11y.testutil";

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function mockFetch(routes: Record<string, () => Response>) {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method });
    const key = `${method} ${url.replace(/^\/internal/, "").split("?")[0]}`;
    const reply = routes[key];
    if (!reply) throw new Error(`unexpected ${key}`);
    return reply();
  }));
  return calls;
}

const operator = {
  id: "stf_1", email: "aisha@newshop.sg", name: "Aisha Rahman", role: "merchant_operator",
  role_label: "Merchant operator", merchant: { id: "mer_1", name: "New Shop", status: "active" },
};
const admin = { id: "stf_9", email: "admin@securepay.sg", name: "Admin", role: "administrator",
  role_label: "Administrator", merchant: null };
const analyst = { id: "stf_5", email: "an@securepay.sg", name: "Analyst", role: "fraud_analyst",
  role_label: "Fraud analyst", merchant: null };

const row = {
  id: "evt_1", type: "payment.authorised", sequence: 2, status: "undelivered", attempts: 14,
  payment_id: "pay_1", merchant_id: "mer_1", merchant_name: "New Shop", resends: 0,
  last_http_status: 500, last_error: null, last_attempt_at: "2026-11-18T04:00:00Z",
  next_attempt_at: null, created_at: "2026-11-15T04:00:00Z", delivered_at: null,
};
const list = {
  object: "list", count: 1, page: 1, page_size: 25,
  counts: { pending: 0, delivered: 3, undelivered: 1 },
  endpoint: { url: "https://newshop.sg/webhooks", approved: true },
  event_types: ["payment.authorised", "payment.captured"], data: [row],
};
const detail = {
  ...row, endpoint: "https://newshop.sg/webhooks", endpoint_approved: true,
  payload: { id: "evt_1", type: "payment.authorised" }, can_resend: true, max_resends: 5,
  attempt_log: [
    { number: 14, at: "2026-11-18T04:00:00Z", http_status: 500, error: null, duration_ms: 132,
      succeeded: false, response_excerpt: "Internal Server Error", manual: false },
    { number: 1, at: "2026-11-15T04:00:01Z", http_status: null, error: "timeout", duration_ms: 10002,
      succeeded: false, response_excerpt: null, manual: false },
  ],
};

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

describe("Webhook log", () => {
  it("lists events, opens the attempts and resends after confirming", async () => {
    let resent = false;
    const calls = mockFetch({
      "GET /me": () => json(operator),
      "GET /webhooks": () => json(list),
      "GET /webhooks/evt_1": () => json(resent ? { ...detail, status: "pending", can_resend: false, resends: 1 } : detail),
      "POST /webhooks/evt_1/resend": () => {
        resent = true;
        return json({ ...detail, status: "pending", can_resend: false, resends: 1, next_attempt_at: "2026-11-18T06:00:00Z" }, 202);
      },
    });
    at("/webhooks");
    expect(await screen.findByRole("heading", { name: "Webhooks" })).toBeTruthy();
    expect(await screen.findByText("https://newshop.sg/webhooks")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Webhook events" });
    expect(within(table).getByText("HTTP 500")).toBeTruthy();
    expect(within(table).queryByText("New Shop")).toBeNull(); // no merchant column for operators
    await expectAccessible();

    fireEvent.click(within(table).getByRole("button", { name: "Open payment.authorised evt_1" }));
    const dialog = await screen.findByRole("dialog", { name: "Webhook payment.authorised" });
    const attempts = await within(dialog).findByRole("table", { name: "Delivery attempts" });
    expect(within(attempts).getByText("Internal Server Error")).toBeTruthy();
    expect(within(attempts).getByText(/No reply within 10 s/)).toBeTruthy();
    expect(within(attempts).getByText("132 ms")).toBeTruthy();
    await expectAccessible();

    fireEvent.click(within(dialog).getByRole("button", { name: "Resend" }));
    expect(within(dialog).getByText(/ignore the repeat by its event ID/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm resend" }));
    expect(await within(dialog).findByText(/Queued again with the same event ID/)).toBeTruthy();
    expect(calls.filter((c) => c.method === "POST").map((c) => c.url)).toEqual(["/internal/webhooks/evt_1/resend"]);
    await waitFor(() => expect(within(dialog).queryByRole("button", { name: "Resend" })).toBeNull());
  });

  it("filters by status and search", async () => {
    const calls = mockFetch({
      "GET /me": () => json(operator),
      "GET /webhooks": () => json(list),
    });
    at("/webhooks");
    fireEvent.click(await screen.findByRole("button", { name: "Failed (1)" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("status=undelivered"))).toBe(true));
    fireEvent.change(screen.getByLabelText("Event or payment ID"), { target: { value: "pay_1" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("q=pay_1") && c.url.includes("status=undelivered"))).toBe(true));
  });

  it("shows administrators the merchant column and no endpoint card", async () => {
    mockFetch({
      "GET /me": () => json(admin),
      "GET /webhooks": () => json({ ...list, endpoint: null }),
    });
    at("/webhooks");
    const table = await screen.findByRole("table", { name: "Webhook events" });
    expect(await within(table).findByText("New Shop")).toBeTruthy();
    expect(screen.queryByText("Your webhook address")).toBeNull();
  });

  it("explains why an event that is still retrying cannot be resent", async () => {
    mockFetch({
      "GET /me": () => json(operator),
      "GET /webhooks": () => json(list),
      "GET /webhooks/evt_1": () => json({ ...detail, status: "pending", can_resend: false }),
    });
    at("/webhooks");
    fireEvent.click(await screen.findByRole("button", { name: "Open payment.authorised evt_1" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/still being retried automatically/)).toBeTruthy();
    expect(within(dialog).queryByRole("button", { name: "Resend" })).toBeNull();
  });

  it("is not offered to fraud analysts", async () => {
    mockFetch({
      "GET /me": () => json(analyst),
      "GET /payments": () => json({ count: 0, page: 1, page_size: 25, data: [],
        summary: { awaiting_capture: 0, unresolved: 0, blocked_today: 0 } }),
    });
    at("/webhooks");
    await waitFor(() => expect(window.location.pathname.endsWith("/payments")).toBe(true));
  });
});
