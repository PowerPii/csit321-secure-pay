// Integrity and keys page (FR-ADM-09, FR-ADM-14, FR-ADM-15, NFR-PRI-01).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { expectAccessible } from "./a11y.testutil";

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function mockFetch(routes: Record<string, (body: unknown) => Response>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url, method, body });
    const key = `${method} ${url.replace(/^\/internal/, "").split("?")[0]}`;
    const reply = routes[key];
    if (!reply) throw new Error(`unexpected ${key}`);
    return reply(body);
  }));
  return calls;
}

const admin = { id: "stf_9", email: "admin@securepay.sg", name: "Admin", role: "administrator",
  role_label: "Administrator", merchant: null };
const common = {
  "GET /me": () => json(admin),
  "GET /alerts/unread": () => json({ unread: 0, latest_at: null }),
  "GET /security/alerts/open-count": () => json({ open: 0, latest_at: null }),
  "GET /integrity/runs": () => json({ data: [] }),
};

const key = (id: string, purpose: "vault" | "field", over = {}) => ({
  id, purpose, purpose_label: purpose === "vault" ? "Card data (vault)" : "Signing secrets and email bodies",
  status: "active", created_at: "2026-08-01T00:00:00Z", created_by: null, retired_at: null, age_days: 107,
  rotate_by: "2026-10-30T00:00:00Z", overdue: true, due_soon: true, ...over,
});

const run = (kind: string, summary: unknown, outcome = "passed") => ({
  id: `mrn_${kind}`, kind, kind_label: kind, outcome, started_at: "2026-11-16T02:00:00Z",
  finished_at: "2026-11-16T02:00:01Z", started_by: null, summary,
});

function overview(over = {}) {
  return {
    runs: {
      self_check: run("self_check", { checks: [
        { id: "https", name: "HTTPS enforced", practice: "PCI DSS 4.2.1: strong cryptography in transit", status: "passed", detail: "ok" },
        { id: "key_age", name: "Encryption keys rotated within 90 days", practice: "PCI DSS 3.6.1, 3.7.4", status: "failed", detail: "1 active key(s) are older than 90 days" },
      ], counts: { passed: 1, failed: 1, not_checked: 0 } }, "problems"),
      integrity: run("integrity", {
        payments: { checked: 12, baselined: 0, problems: 1, findings: [{ payment_id: "pay_1", reference: "SP-AAAA-BBBB" }] },
        audit: { checked: 40, unsealed_recent: 0, problems: 0, counts: { edited: 0 }, findings: [] },
      }, "problems"),
      retention: null,
    },
    schedule: { self_check: { every_hours: 24, next_at: null }, integrity: { every_hours: 6, next_at: null },
      retention: { every_hours: 24, next_at: null } },
    keys: [key("dk_vault1", "vault"), key("dk_field1", "field", { overdue: false, due_soon: false, age_days: 3 })],
    key_max_age_days: 90,
    ...over,
  };
}

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

describe("integrity and keys", () => {
  it("shows self-checks with their PCI DSS practice, changed payments and overdue keys", async () => {
    mockFetch({ ...common, "GET /integrity": () => json(overview()) });
    at("/integrity");
    const checks = await screen.findByRole("table", { name: "Self-checks" });
    await expectAccessible();
    expect(within(checks).getByText("PCI DSS 4.2.1: strong cryptography in transit")).toBeTruthy();
    expect(within(checks).getByText("Failed")).toBeTruthy();
    expect(screen.getByText(/SP-AAAA-BBBB/)).toBeTruthy();
    expect(screen.getByText(/1 active key\(s\) are past 90 days/)).toBeTruthy();
    expect(screen.getByText("Active · overdue")).toBeTruthy();
  });

  it("rotates a key only with the authenticator code", async () => {
    const calls = mockFetch({
      ...common,
      "GET /integrity": () => json(overview()),
      "POST /security/keys/rotate": () => json(overview({ keys: [
        key("dk_vault2", "vault", { overdue: false, due_soon: false, age_days: 0 }),
        key("dk_vault1", "vault", { status: "decrypt_only", overdue: false, due_soon: false }),
        key("dk_field1", "field", { overdue: false, due_soon: false, age_days: 3 }),
      ] })),
    });
    at("/integrity");
    const keys = await screen.findByRole("table", { name: "Encryption keys" });
    const row = within(keys).getByText("dk_vault1").closest("tr")!;
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Rotate" }));
    const dialog = await screen.findByRole("dialog", { name: /Rotate key: Card data/ });
    const confirm = within(dialog).getByRole("button", { name: "Rotate key" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText("Code from your authenticator app"), { target: { value: "123456" } });
    fireEvent.click(confirm);
    expect(await screen.findByText("Decrypt only")).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/security/keys/rotate"))?.body).toEqual({ purpose: "vault", code: "123456" });
  });

  it("runs the clean-up on demand", async () => {
    const calls = mockFetch({
      ...common,
      "GET /integrity": () => json(overview()),
      "POST /integrity/run": () => json({ ...overview({ runs: { ...overview().runs,
        retention: run("retention", { counts: { payments_anonymised: 2, emails_deleted: 1 } }) } }) }),
    });
    at("/integrity");
    fireEvent.click(await screen.findByRole("button", { name: "Clean up now" }));
    expect(await screen.findByText(/2 payments anonymised · 1 emails deleted/)).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "retention" });
  });
});
