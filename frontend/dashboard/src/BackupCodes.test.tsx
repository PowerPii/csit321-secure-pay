import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

type Reply = (init?: RequestInit) => Response;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
const unauthorised = () => json({ error: { code: "not_signed_in", message: "Sign in to the dashboard." } }, 401);

function mockFetch(routes: Record<string, Reply | Reply[]>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const used: Record<string, number> = {};
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = `${method} ${url.replace(/^\/internal/, "").split("?")[0]}`;
    const reply = routes[key];
    if (!reply) return json({}, 200);
    if (Array.isArray(reply)) {
      const i = Math.min(used[key] ?? 0, reply.length - 1);
      used[key] = (used[key] ?? 0) + 1;
      return reply[i](init);
    }
    return reply(init);
  }));
  return calls;
}

const analyst = {
  id: "stf_2", email: "analyst@securepay.sg", name: "Daniel Lim", role: "fraud_analyst",
  role_label: "Fraud analyst", merchant: null, backup_codes_left: 10,
};
const codes = ["abcde-fghjk", "bcdef-ghjkm", "cdefg-hjkmn", "defgh-jkmnp", "efghj-kmnpq",
  "fghjk-mnpqr", "ghjkm-npqrs", "hjkmn-pqrst", "jkmnp-qrstu", "kmnpq-rstuv"];
const overview = { today: {}, chart: [], latest: [] };

beforeEach(() => { document.cookie = "csrftoken=tok123"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function at(path: string) {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
  render(<App />);
}

async function passwordStep(setup: unknown = null) {
  fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "analyst@securepay.sg" } });
  fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "correct horse" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Two-step verification")).toBeTruthy();
  return setup;
}

describe("backup codes for two-step verification", () => {
  it("signs in with a backup code instead of the authenticator app", async () => {
    const calls = mockFetch({
      "GET /me": [unauthorised, unauthorised, () => json({ ...analyst, backup_codes_left: 2 })],
      "POST /auth/login": () => json({ next: "totp", email: analyst.email, setup: null }),
      "POST /auth/backup-code": () => json({ ...analyst, backup_codes_left: 2 }),
      "GET /overview": () => json(overview),
    });
    at("/login");
    await passwordStep();
    fireEvent.click(screen.getByRole("button", { name: /Use a backup code/ }));
    const verify = screen.getByRole("button", { name: "Verify" }) as HTMLButtonElement;
    expect(verify.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Backup code/), { target: { value: "ABCDE-FGHJK" } });
    fireEvent.click(verify);
    // Few codes left: the dashboard asks for new ones.
    expect(await screen.findByText(/Only 2 backup codes left/)).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/auth/backup-code"))!.body).toEqual({ code: "ABCDE-FGHJK" });
    expect(calls.some((c) => c.url.endsWith("/auth/totp") && c.method === "POST")).toBe(false);
  });

  it("shows a wrong backup code error from the server", async () => {
    mockFetch({
      "GET /me": unauthorised,
      "POST /auth/login": () => json({ next: "totp", email: analyst.email, setup: null }),
      "POST /auth/backup-code": () => json({ error: { code: "code_incorrect",
        message: "That backup code is not right or has already been used. Each backup code works once." } }, 401),
    });
    at("/login");
    await passwordStep();
    fireEvent.click(screen.getByRole("button", { name: /Use a backup code/ }));
    fireEvent.change(screen.getByLabelText(/Backup code/), { target: { value: "aaaaa-aaaaa" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/already been used/);
  });

  it("shows the backup codes once after first-time setup and waits for 'I have saved these codes'", async () => {
    const setup = { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x", qr_svg: "data:image/svg+xml;base64,PHN2Zy8+" };
    mockFetch({
      "GET /me": [unauthorised, unauthorised, () => json(analyst)],
      "POST /auth/login": () => json({ next: "totp", email: analyst.email, setup }),
      "POST /auth/totp": () => json({ ...analyst, backup_codes: codes }),
      "GET /overview": () => json(overview),
    });
    at("/login");
    await passwordStep(setup);
    // No backup-code option during setup: there are no codes yet.
    expect(screen.queryByRole("button", { name: /Use a backup code/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Digit 1"), { target: { value: "279013" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("Save your backup codes")).toBeTruthy();
    const list = screen.getByTestId("backup-codes");
    expect(within(list).getAllByRole("listitem")).toHaveLength(10);
    expect(within(list).getByText("abcde-fghjk")).toBeTruthy();
    const go = screen.getByRole("button", { name: "Continue to the dashboard" }) as HTMLButtonElement;
    expect(go.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("I have saved these codes"));
    expect(go.disabled).toBe(false);
  });

  it("makes new codes on the Two-step verification page after the authenticator code", async () => {
    const calls = mockFetch({
      "GET /me": () => json(analyst),
      "GET /me/backup-codes": () => json({ remaining: 1, total: 10, generated_at: "2026-11-17T06:00:00Z" }),
      "POST /me/backup-codes": () => json({ remaining: 10, total: 10, generated_at: "2026-11-17T07:00:00Z", codes }),
    });
    at("/two-step");
    expect(await screen.findByText("1 of 10")).toBeTruthy();
    expect(screen.getByText(/Only 1 backup code left/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Make new codes" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/authenticator app/), { target: { value: "123 456" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Make new codes" }));
    expect(await screen.findByText("Your new backup codes")).toBeTruthy();
    expect(screen.getByText("10 of 10")).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/me/backup-codes") && c.method === "POST")!.body).toEqual({ code: "123456" });
  });
});
