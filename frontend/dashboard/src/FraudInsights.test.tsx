// Fraud insights charts page (extends FR-FRD-10).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { niceTicks } from "./components/InsightCharts";
import { scoreAxisMax } from "./routes/FraudInsights";

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function mockFetch(routes: Record<string, () => Response>) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(url);
    const key = `${init?.method ?? "GET"} ${url.replace(/^\/internal/, "").split("?")[0]}`;
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

const bins = Array.from({ length: 50 }, (_, i) => ({ low: i * 0.02, high: (i + 1) * 0.02, allowed: 0, verify: 0, blocked: 0 }));
bins[1].allowed = 30;
bins[6].verify = 2;
bins[45].blocked = 1;

const insights = {
  generated_at: "2026-11-18T06:00:00Z", range: "7d", interval: "day",
  from: "2026-11-11T16:00:00Z", to: "2026-11-18T16:00:00Z", time_zone: "Asia/Singapore",
  merchant: null, merchants: [{ id: "mer_1", name: "Volt & Co." }],
  totals: { screened: 40, allowed: 30, verify: 6, blocked: 4, not_screened: 0 },
  outcomes: [{ start: "2026-11-17", allowed: 10, verify: 2, blocked: 1, not_screened: 0 },
    { start: "2026-11-18", allowed: 20, verify: 4, blocked: 3, not_screened: 0 }],
  decided_by: { rules: 8, model: 2, allowed: 30, unavailable: 0 },
  top_rules: [{ reason: "card_attempt_burst", blocked: 3, verify: 0, total: 3 },
    { reason: "high_amount", blocked: 0, verify: 4, total: 4 }],
  scores: {
    scored: 33, points_limit: 500, model_versions: ["hgb-fs02-2026-11-13"],
    points: [{ at: "2026-11-18T02:00:00Z", score: 0.03, outcome: "allowed", case_id: null },
      { at: "2026-11-18T03:00:00Z", score: 0.91, outcome: "blocked", case_id: "scr_9" }],
    histogram: bins,
  },
  thresholds: { model_version: "hgb-fs02-2026-11-13", policy_version: "policy-hgb-fs02-2026-11-13", stub_model: false,
    verify: 0.1136, block: 0.2222, verify_note: "Set so that 2% of genuine payments are asked for a code (false-positive rate)",
    block_note: "Set so that 0.1% of genuine payments are blocked (false-positive rate)" },
};

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

describe("fraud insights", () => {
  it("draws the outcome, rule and score charts with the policy lines", async () => {
    const calls = mockFetch({
      "GET /me": () => json(analyst),
      "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
      "GET /insights/fraud": () => json(insights),
      "GET /reviews/scr_9": () => json({ error: { code: "not_found", message: "Not found." } }, 404),
    });
    at("/insights");
    expect(await screen.findByText("4 · 10.0%")).toBeTruthy();
    expect(screen.getByRole("img", { name: /per day; 30 allowed, 6 step-up, 4 blocked/ })).toBeTruthy();
    expect(screen.getByRole("img", { name: /Top rules hit: Burst of attempts/ })).toBeTruthy();
    expect(screen.getByText("Block line: score 0.2222")).toBeTruthy();
    expect(screen.getByText(/0.1% of genuine payments are blocked/)).toBeTruthy();
    expect(calls.find((u) => u.startsWith("/internal/insights/fraud"))).toBe("/internal/insights/fraud?range=7d");

    // The same numbers as a table.
    fireEvent.click(screen.getAllByRole("button", { name: "Show table" })[1]);
    expect(screen.getByRole("table", { name: "Top rules hit" }).textContent).toContain("Amount over S$ 500");

    // A blocked dot opens its case.
    const dot = document.querySelectorAll("circle")[1];
    fireEvent.click(dot);
    await waitFor(() => expect(window.location.pathname).toMatch(/\/reviews\/scr_9$/));
  });

  it("changes the range", async () => {
    const calls = mockFetch({
      "GET /me": () => json(analyst),
      "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
      "GET /insights/fraud": () => json(insights),
    });
    at("/insights");
    fireEvent.click(await screen.findByRole("button", { name: "Last 24 hours" }));
    await waitFor(() => expect(calls).toContain("/internal/insights/fraud?range=24h"));
  });

  it("is not offered to a merchant operator", async () => {
    mockFetch({
      "GET /me": () => json(operator),
      "GET /payments": () => json({ count: 0, page: 1, page_size: 20, data: [],
        summary: { awaiting_capture: 0, unresolved: 0, blocked_today: 0, refunded_this_month: 0, escalated: null } }),
    });
    at("/insights");
    await waitFor(() => expect(window.location.pathname).toMatch(/\/payments$/));
    expect(screen.queryByText("Fraud insights")).toBeNull();
  });

  it("picks round ticks and a score axis with room above the block line", () => {
    expect(niceTicks(27)).toEqual([0, 10, 20, 30]);
    expect(scoreAxisMax([0.1136, 0.2222], [0.05])).toBe(0.3);
    expect(scoreAxisMax([0.5, 0.9], [0])).toBe(1);
    expect(scoreAxisMax([0.1136, 0.2222], [0.47])).toBe(0.5);
  });
});
