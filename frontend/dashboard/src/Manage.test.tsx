// Account management and limits (FR-ADM-02 to FR-ADM-05, FR-ADM-07, FR-ADM-12).
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

const admin = { id: "stf_9", email: "admin@securepay.sg", name: "Admin", role: "administrator",
  role_label: "Administrator", merchant: null };
const roles = [{ value: "merchant_operator", label: "Merchant operator" }, { value: "fraud_analyst", label: "Fraud analyst" },
  { value: "administrator", label: "Administrator" }];
const priya = { id: "stf_2", name: "Priya Nair", email: "priya@securepay.sg", role: "fraud_analyst", role_label: "Fraud analyst",
  merchant: null, status: "active", status_reason: null, status_changed_at: null, last_sign_in_at: null, created_at: "2026-11-01T00:00:00Z" };
const me = { ...priya, id: "stf_9", name: "Admin", email: "admin@securepay.sg", role: "administrator", role_label: "Administrator" };
const common = {
  "GET /me": () => json(admin),
  "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
  "GET /security/alerts/open-count": () => json({ open: 0, latest_at: null }),
};

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

describe("accounts", () => {
  it("suspends another account with a reason and confirmation, but never your own", async () => {
    let suspended = false;
    const calls = mockFetch({
      ...common,
      "GET /staff": () => json({ data: [me, { ...priya, status: suspended ? "suspended" : "active",
        status_reason: suspended ? "Suspected misuse" : null }], roles }),
      "POST /staff/stf_2/status": () => { suspended = true; return json({ ...priya, status: "suspended" }); },
    });
    at("/accounts");
    const ownRow = (await screen.findByText("admin@securepay.sg")).closest("tr")!;
    await expectAccessible();
    expect(within(ownRow as HTMLElement).queryByRole("button", { name: "Suspend" })).toBeNull();
    const row = screen.getByText("priya@securepay.sg").closest("tr")!;
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Suspend" }));
    const dialog = await screen.findByRole("dialog", { name: "Suspend Priya Nair" });
    expect(within(dialog).getByText(/signed out and cannot sign in/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm suspend" }));
    expect(await screen.findByText("Suspected misuse")).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ action: "suspend", reason: "Suspected misuse", confirm: true });
  });

  it("shows the last-administrator refusal on a role change", async () => {
    mockFetch({
      ...common,
      "GET /staff": () => json({ data: [me], roles }),
      "GET /merchants": () => json({ data: [] }),
      "POST /staff/stf_9/role": () => json({ error: { code: "last_administrator",
        message: "This is the last active administrator. Make another account an administrator first." } }, 409),
    });
    at("/accounts");
    fireEvent.click(await screen.findByRole("button", { name: "Role" }));
    const dialog = await screen.findByRole("dialog", { name: "Role of Admin" });
    fireEvent.mouseDown(within(dialog).getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Fraud analyst" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save role" }));
    expect(await within(dialog).findByText(/last active administrator/)).toBeTruthy();
  });
});

describe("limits", () => {
  it("changes the amount and rate limits after confirming", async () => {
    const limits = { effective: { max_amount_cents: 1000000, api_key_requests_per_minute: 100, ip_requests_per_minute: 300 },
      defaults: { max_amount_cents: 1000000, api_key_requests_per_minute: 100, ip_requests_per_minute: 300 },
      bounds: { max_amount_cents: [50, 1000000], requests_per_minute: [1, 10000] }, updated_at: null, updated_by: null };
    const calls = mockFetch({
      ...common,
      "GET /limits": () => json(limits),
      "POST /limits": () => json({ ...limits, effective: { ...limits.effective, max_amount_cents: 500000 },
        updated_at: "2026-11-16T07:00:00Z", updated_by: "stf_9" }),
    });
    at("/limits");
    const amount = await screen.findByLabelText("Maximum per payment (SGD)");
    await expectAccessible();
    fireEvent.change(amount, { target: { value: "20000" } });
    expect((screen.getByRole("button", { name: "Save limits" }) as HTMLButtonElement).disabled).toBe(true); // above the ceiling
    fireEvent.change(amount, { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save limits" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/New requests use the new limits/)).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      max_amount_cents: 500000, api_key_requests_per_minute: 100, ip_requests_per_minute: 300 });
  });
});
