// Spending insights on the customer account (/account/spending): totals, a chart per section
// with a table alternative, the empty state, and an axe scan (as in the 18 Nov 2026 pass).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import Account from "./Account";
import { monthLabel, niceScale } from "./account/Spending";

const ME = { id: "cus_x", full_name: "Jane Tan", email: "jane@example.com", idle_minutes: 15, idle_warning_minutes: 13 };
const months = Array.from({ length: 12 }, (_, i) => {
  const m = ((11 + i) % 12) + 1; // Dec 2025 .. Nov 2026
  const y = m === 12 ? 2025 : 2026;
  return { month: `${y}-${String(m).padStart(2, "0")}`, spent: 0, refunded: 0, net: 0, payments: 0 };
});
months[10] = { ...months[10], spent: 12900, refunded: 0, net: 12900, payments: 1 }; // Oct
months[11] = { ...months[11], spent: 248890, refunded: 1500, net: 247390, payments: 2 }; // Nov
const INSIGHTS = {
  currency: "SGD", time_zone: "Asia/Singapore", from: "2025-12", to: "2026-11",
  totals: { spent: 261790, refunded: 1500, net: 260290, payments: 3, merchants: 2, on_hold: 4500, on_hold_payments: 1 },
  by_month: months,
  by_merchant: [
    { merchant_name: "Volt & Co.", spent: 248890, refunded: 1500, net: 247390, payments: 2 },
    { merchant_name: "Demo Shop", spent: 12900, refunded: 0, net: 12900, payments: 1 },
  ],
};
const EMPTY = { ...INSIGHTS, totals: { ...INSIGHTS.totals, spent: 0, refunded: 0, net: 0, payments: 0, merchants: 0, on_hold: 0, on_hold_payments: 0 },
  by_month: months.map((m) => ({ ...m, spent: 0, refunded: 0, net: 0, payments: 0 })), by_merchant: [] };

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function serve(insights: () => Response) {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url);
    if (url.endsWith("/me")) return json(ME);
    if (url.endsWith("/insights")) return insights();
    throw new Error(`unexpected ${url}`);
  }));
  return urls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("spending helpers", () => {
  it("labels months and picks round axis steps", () => {
    expect(monthLabel("2026-11")).toBe("Nov");
    expect(monthLabel("2025-12", "long")).toBe("December 2025");
    expect(niceScale(247390)).toEqual({ top: 300000, step: 100000 });
    expect(niceScale(9000)).toEqual({ top: 10000, step: 2500 });
    expect(niceScale(0)).toEqual({ top: 10000, step: 2500 });
    const { top, step } = niceScale(12345);
    expect(top).toBeGreaterThanOrEqual(12345);
    expect(top % step).toBe(0);
  });
});

describe("spending insights page", () => {
  it("shows the totals, both charts with summaries, and the on-hold note", async () => {
    const urls = serve(() => json(INSIGHTS));
    render(<Account path="/account/spending" hash="" />);
    expect(await screen.findByRole("heading", { name: "Spending" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Spending" }).getAttribute("aria-current")).toBe("page");
    expect(urls.some((u) => u.endsWith("/customer/insights"))).toBe(true);
    expect((await screen.findByText("Spent after refunds")).nextElementSibling?.textContent).toBe("S$ 2,602.90");
    expect(screen.getByText(/S\$ 45.00 in 1 payment is on hold/)).toBeTruthy();
    expect(screen.getByText(/December 2025 to November 2026/)).toBeTruthy();
    const charts = screen.getAllByRole("img");
    expect(charts).toHaveLength(2);
    expect(charts[0].getAttribute("aria-label")).toContain("Highest: November 2026, S$ 2,473.90");
    expect(charts[1].getAttribute("aria-label")).toContain("Volt & Co.: S$ 2,473.90; Demo Shop: S$ 129.00");
    // A bar per month with spending, each with a tooltip title.
    expect(charts[0].querySelectorAll("rect")).toHaveLength(2);
    expect(charts[0].querySelector("title")?.textContent).toBe("October 2026: S$ 129.00 (1 payment)");
  });

  it("swaps each chart for a table with the same numbers", async () => {
    serve(() => json(INSIGHTS));
    render(<Account path="/account/spending" hash="" />);
    const [monthToggle] = await screen.findAllByRole("button", { name: "Show table" });
    expect(monthToggle.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(monthToggle);
    expect(monthToggle.getAttribute("aria-pressed")).toBe("true");
    expect(monthToggle.textContent).toBe("Show chart");
    const table = screen.getByRole("table", { name: "Spending by month" });
    expect(within(table).getAllByRole("row")).toHaveLength(13); // header + 12 months
    const nov = within(table).getByRole("rowheader", { name: "November 2026" }).closest("tr")!;
    expect(within(nov).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2", "S$ 2,488.90", "S$ 15.00", "S$ 2,473.90"]);
    fireEvent.click(screen.getByRole("button", { name: "Show table" }));
    const shops = screen.getByRole("table", { name: "Spending by shop" });
    expect(within(shops).getByRole("rowheader", { name: "Volt & Co." })).toBeTruthy();
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });

  it("shows the empty state when nothing was charged", async () => {
    serve(() => json(EMPTY));
    render(<Account path="/account/spending" hash="" />);
    expect(await screen.findByText("Nothing spent yet")).toBeTruthy();
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });

  it("sends the customer to sign in when the session has ended", async () => {
    serve(() => json({ error: { code: "sign_in_required", message: "Sign in." } }, 401));
    render(<Account path="/account/spending" hash="" />);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeTruthy();
  });

  it("finds no WCAG A or AA issue in chart view or table view (NFR-USE-02)", async () => {
    serve(() => json(INSIGHTS));
    render(<Account path="/account/spending" hash="" />);
    await screen.findByRole("heading", { name: "By month" });
    const scan = async () => {
      const result = await axe.run(document.body, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
        rules: { "color-contrast": { enabled: false } },
      });
      return result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")}`));
    };
    expect(await scan()).toEqual([]);
    for (const b of screen.getAllByRole("button", { name: "Show table" })) fireEvent.click(b);
    expect(await scan()).toEqual([]);
  });
});
