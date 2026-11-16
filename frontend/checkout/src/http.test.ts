import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getSession } from "./api";
import { AccountApiError, getMe, signOut as accountSignOut } from "./accountApi";
import { GuestApiError, getGuestPayment, signOut as guestSignOut } from "./guestApi";

afterEach(() => vi.unstubAllGlobals());

const clients = [
  { call: () => getSession("session/id"), path: "/checkout/session%2Fid", error: ApiError },
  { call: getMe, path: "/customer/me", error: AccountApiError },
  { call: getGuestPayment, path: "/guest/status/payment", error: GuestApiError },
];

describe.each(clients)("JSON API $path", ({ call, path, error }) => {
  it("preserves same-origin cookies, no-store and JSON headers", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"reference":"SP-test"}'));
    vi.stubGlobal("fetch", fetch);
    await expect(call()).resolves.toEqual({ reference: "SP-test" });
    expect(fetch).toHaveBeenCalledWith(path, expect.objectContaining({
      credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
    }));
  });

  it("retains the API's error class when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const failure = await call().catch((e) => e);
    expect(failure).toBeInstanceOf(error);
    expect(failure).toMatchObject({ status: 0, code: "network_error", param: null });
  });

  it("handles non-JSON error responses without hiding the HTTP status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })));
    await expect(call()).rejects.toMatchObject({ status: 502, code: "unknown_error" });
  });
});

it.each([accountSignOut, guestSignOut])("accepts an empty sign-out response", async (signOut) => {
  const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  await expect(signOut()).resolves.toBeUndefined();
  expect(fetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ method: "POST", body: "{}" }));
});

it.each([null, "invalid", "0", "-1", "30"])("preserves guest attempt counts and Retry-After %s", async (retry) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: "wrong_code", message: "Try again.", param: "code" }, attempts_remaining: 2,
  }), { status: 429, headers: retry === null ? {} : { "Retry-After": retry } })));
  const failure = await getGuestPayment().catch((e) => e);
  expect(failure).toBeInstanceOf(GuestApiError);
  expect(failure).toMatchObject({ code: "wrong_code", param: "code", attemptsRemaining: 2,
    retryAfter: retry === "30" ? 30 : null });
});

it("preserves account lockout retry information", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: "account_locked", message: "Wait before trying again." },
  }), { status: 429, headers: { "Retry-After": "900" } })));
  await expect(getMe()).rejects.toMatchObject({ code: "account_locked", retryAfter: 900 });
});
