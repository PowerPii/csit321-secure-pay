// Fraud alerts (FR-FRD-08) and fraud reports (FR-FRD-10) pages.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { sgDate } from "./routes/Fraud";
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

const analyst = { id: "stf_2", email: "priya@securepay.test", name: "Priya Nair", role: "fraud_analyst",
  role_label: "Fraud analyst", merchant: null };
const operator = { ...analyst, id: "stf_1", role: "merchant_operator", role_label: "Merchant operator",
  merchant: { id: "mer_1", name: "Demo Shop" } };

const caseRow = {
  id: "scr_9", payment: { id: "pay_9", reference: "SP-5LKD-2ZZ8", amount: 98000, currency: "SGD", status: "blocked" },
  merchant: { id: "mer_1", name: "Demo Shop" }, score: 0.93, outcome: "block", decision: "blocked",
  reasons: ["blocklisted_card"], occurred_at: "2026-11-02T04:47:00Z",
  review: { status: "open", assigned_to: null, finding: null, notes: "", reviewed_by: null, reviewed_at: null },
};

const report = {
  generated_at: "2026-11-16T06:00:00Z",
  period: { from: "2026-10-18", to: "2026-11-16", interval: "day", time_zone: "Asia/Singapore" },
  merchant: null, merchants: [{ id: "mer_1", name: "Demo Shop" }],
  totals: { screened: 40, allowed: 30, flagged: 10, blocked: 4, verify: 6, not_screened: 0,
    flagged_amount: 500000, blocked_amount: 200000, flag_rate: 0.25 },
  decisions: { blocked: 4, verify_failed: 1, verify_passed: 4, verify_pending: 1 },
  risk_levels: [{ level: "high", label: "High (0.90 and above)", count: 4 }, { level: "low", label: "Low (below 0.50)", count: 6 }],
  findings: { confirmed_fraud: 3, false_positive: 2, inconclusive: 0, unreviewed: 5 },
  top_reasons: [{ reason: "blocklisted_card", count: 4 }],
  trend: [{ start: "2026-11-15", screened: 10, flagged: 2, blocked: 1, confirmed_fraud: 0 },
    { start: "2026-11-16", screened: 30, flagged: 8, blocked: 3, confirmed_fraud: 3 }],
};

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

describe("fraud alerts and reports", () => {
  it("shows the unread count in the sidebar and opens the case from an alert", async () => {
    const calls = mockFetch({
      "GET /me": () => json(analyst),
      "GET /alerts/unread": () => json({ unread: 3, latest_at: "2026-11-02T04:47:00Z" }),
      "GET /alerts": () => json({ count: 1, page: 1, page_size: 25, unread: 1,
        data: [{ id: "fal_1", created_at: "2026-11-02T04:47:01Z", read: false, case: caseRow }] }),
      "POST /alerts/fal_1/read": () => json({ id: "fal_1", read: true }),
      "GET /reviews/scr_9": () => json({ error: { code: "not_found", message: "Not found." } }, 404),
    });
    at("/alerts");
    expect(await screen.findByText("SP-5LKD-2ZZ8")).toBeTruthy();
    await expectAccessible();
    expect(screen.getByRole("link", { name: "3 unread fraud alerts" })).toBeTruthy();
    // Screen readers hear the count from a live region that is always on the page.
    expect(screen.getByRole("status").textContent).toBe("3 unread fraud alerts");
    expect(screen.getByText("Card on blocklist")).toBeTruthy();
    expect(screen.getByText("Unread (1)")).toBeTruthy();
    fireEvent.click(screen.getByRole("row", { name: /Unread: SP-5LKD-2ZZ8/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/internal/alerts/fal_1/read")).toBe(true));
    await waitFor(() => expect(window.location.pathname).toMatch(/\/reviews\/scr_9$/));
  });

  it("does not show alerts or reports to a merchant operator", async () => {
    mockFetch({
      "GET /me": () => json(operator),
      "GET /payments": () => json({ count: 0, page: 1, page_size: 20, data: [],
        summary: { awaiting_capture: 0, unresolved: 0, blocked_today: 0, refunded_this_month: 0, escalated: null } }),
    });
    at("/alerts");
    await waitFor(() => expect(window.location.pathname).toMatch(/\/payments$/));
    expect(screen.queryByText("Fraud alerts")).toBeNull();
    expect(screen.queryByText("Fraud reports")).toBeNull();
  });

  it("shows a report with counts, trend and a CSV link", async () => {
    const calls = mockFetch({
      "GET /me": () => json(analyst),
      "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
      "GET /reports/fraud": () => json(report),
    });
    at("/reports");
    expect(await screen.findByText("10 · 25.0%")).toBeTruthy();
    await expectAccessible();
    expect(screen.getByText("High (0.90 and above)")).toBeTruthy();
    expect(screen.getByText("Not reviewed yet")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Screened and flagged payments per day" })).toBeTruthy();
    const link = screen.getByRole("link", { name: "Export CSV" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/internal/reports/fraud/export?from=${sgDate(29)}&to=${sgDate(0)}`);
    expect(calls.find((c) => c.url.startsWith("/internal/reports/fraud"))!.url).toContain(`from=${sgDate(29)}`);
  });

  it("asks for a valid date range instead of requesting a report", async () => {
    const calls = mockFetch({
      "GET /me": () => json(analyst),
      "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
      "GET /reports/fraud": () => json(report),
    });
    at("/reports?from=2026-11-10&to=2026-11-01");
    expect(await screen.findByText(/Choose a valid date range/)).toBeTruthy();
    expect(calls.some((c) => c.url.startsWith("/internal/reports/fraud"))).toBe(false);
  });

  it("formats Singapore dates for the period presets", () => {
    expect(sgDate(0, new Date("2026-11-15T17:30:00Z"))).toBe("2026-11-16");
    expect(sgDate(29, new Date("2026-11-16T03:00:00Z"))).toBe("2026-10-18");
  });
});
