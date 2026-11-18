// History search (FR-FRD-06), block list (FR-FRD-09) and fraud rules (FR-FRD-02, FR-FRD-03).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { expectAccessible } from "./a11y.testutil";

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function mockFetch(routes: Record<string, () => Response>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = `${method} ${url.replace(/^\/internal/, "").split("?")[0]}`;
    const reply = routes[key];
    if (!reply) throw new Error(`unexpected ${key}`);
    return reply();
  }));
  return calls;
}

const analyst = { id: "stf_2", email: "priya@securepay.sg", name: "Priya Nair", role: "fraud_analyst",
  role_label: "Fraud analyst", merchant: null };
const admin = { ...analyst, id: "stf_9", role: "administrator", role_label: "Administrator" };
const common = {
  "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
  "GET /security/alerts/open-count": () => json({ open: 0, latest_at: null }),
};
const rule = (over = {}) => ({ id: "frl_1", revision: 1, code: "high_amount", description: "Above S$500", feature: "amount_cents",
  op: "gt", value: 50000, action: "verify", enabled: true, condition: "amount_cents > 50000", created_at: "2026-11-16T00:00:00Z",
  created_by: null, superseded_at: null, ruleset_version: "rules-0.1", ...over });
const ruleset = (over = {}) => ({ version: "rules-0.1", frozen: null, rules: [rule()], features: ["amount_cents", "card_attempts_10m"],
  ops: [{ value: "gt", label: ">" }, { value: "gte", label: ">=" }], fixed: ["Block list and review list matches"], ...over });

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

describe("history search and block list", () => {
  it("searches by IP and blocklists the address with a reason", async () => {
    const calls = mockFetch({
      ...common,
      "GET /me": () => json(analyst),
      "GET /fraud/search": () => json({ by: "ip", searched: "203.0.113.•", count: 1, page: 1, page_size: 25,
        summary: { attempts: 1, merchants: 1, blocked: 0, flagged: 1 }, blocklisted: null,
        data: [{ case_id: "scr_1", payment: { id: "pay_1", reference: "SP-AAAA-BBBB", status: "authorised" },
          merchant: { id: "mer_1", name: "Demo Shop" }, amount: 60000, card: "Visa •••• 4242", outcome: "verify",
          score: 0.2, reasons: ["high_amount"], occurred_at: "2026-11-16T01:00:00Z" }] }),
      "POST /blocklist": () => json({ id: 1 }, 201),
    });
    at("/search?by=ip&value=203.0.113.9");
    expect(await screen.findByText("SP-AAAA-BBBB")).toBeTruthy();
    await expectAccessible();
    expect(screen.getByText("Attempts · 203.0.113.•")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Blocklist this IP address" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Botnet" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add to block list" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ kind: "ip", ip: "203.0.113.9", reason: "Botnet" });
  });

  it("lets only administrators remove block list entries", async () => {
    mockFetch({
      ...common,
      "GET /me": () => json(analyst),
      "GET /blocklist": () => json({ can_remove: false, data: [{ id: 1, kind: "card", action: "block", display: "Visa •••• 0101",
        reason: "Stolen", active: true, added_by: "stf_2", source_case: null, created_at: "2026-11-16T00:00:00Z",
        removed_by: null, removed_at: null, removal_reason: null }] }),
    });
    at("/blocklist");
    expect(await screen.findByText("Visa •••• 0101")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
  });
});

describe("fraud rules", () => {
  it("warns about a conflict and saves only when confirmed", async () => {
    let attempts = 0;
    const calls = mockFetch({
      ...common,
      "GET /me": () => json(admin),
      "GET /rules": () => json(ruleset()),
      "POST /rules": () => {
        attempts += 1;
        return attempts === 1
          ? json({ error: { code: "rule_conflict", message: "conflicts" }, conflicts: [{ rule_id: "frl_1", code: "high_amount",
            kind: "opposite_action", message: "amount_cents > 20000 (block) can apply to the same payments as high_amount." }] }, 409)
          : json(ruleset({ version: "rules-0.2", rules: [rule(), rule({ id: "frl_2", code: "large_order", action: "block", value: 20000,
            condition: "amount_cents > 20000" })] }), 201);
      },
    });
    at("/rules");
    fireEvent.click(await screen.findByRole("button", { name: "New rule" }));
    await expectAccessible();
    const dialog = await screen.findByRole("dialog", { name: "New fraud rule" });
    fireEvent.change(within(dialog).getByLabelText("Value"), { target: { value: "20000" } });
    fireEvent.change(within(dialog).getByLabelText(/Reason code/), { target: { value: "large_order" } });
    fireEvent.mouseDown(within(dialog).getAllByRole("combobox")[2]);
    fireEvent.click(await screen.findByRole("option", { name: "Block the payment" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save rule" }));
    expect(await within(dialog).findByText(/can apply to the same payments as high_amount/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save anyway" }));
    expect(await screen.findByText("large_order")).toBeTruthy();
    const posts = calls.filter((c) => c.method === "POST");
    expect(posts[0].body).toEqual({ rule: { code: "large_order", description: "", feature: "amount_cents", op: "gt", value: 20000,
      action: "block" }, confirm_conflicts: false });
    expect((posts[1].body as { confirm_conflicts: boolean }).confirm_conflicts).toBe(true);
  });

  it("is read-only for analysts and while frozen", async () => {
    mockFetch({
      ...common,
      "GET /me": () => json(analyst),
      "GET /rules": () => json(ruleset({ frozen: { since: "2026-11-16T00:00:00Z", by: "stf_9", note: "EV-3" } })),
    });
    at("/rules");
    expect(await screen.findByText(/for an evaluation run: EV-3/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "New rule" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect((screen.getByRole("checkbox", { name: "Switch off high_amount" }) as HTMLInputElement).disabled).toBe(true);
  });
});
