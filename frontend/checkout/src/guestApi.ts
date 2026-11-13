// Guest status API (gateway/apps/guest, contracts/openapi/guest-status.v1.yaml). Same origin,
// JSON only. The unlocked payment lives in an HttpOnly cookie the page never sees.
import { ApiError } from "./api";

export interface CodeRequested {
  challenge_id: string;
  message: string;
  expires_in_seconds: number;
}

export interface GuestPayment {
  reference: string;
  merchant_name: string;
  amount: number;
  currency: string;
  status: string;
  status_label: "Paid" | "Not charged" | "Being checked - do not pay again" | "In progress";
  card: { brand: string; last4: string } | null;
  refunded_amount?: number;
  created_at: string;
  timeline: { at: string; label: string }[];
}

export class GuestApiError extends ApiError {
  constructor(
    status: number,
    code: string,
    message: string,
    param: string | null,
    public attemptsRemaining: number | null,
    public retryAfter: number | null,
  ) {
    super(status, code, message, param);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/guest/status/${path}`, {
      ...init,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new GuestApiError(0, "network_error", "We couldn't reach SecurePay. Check your connection and try again.", null, null, null);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const err = body?.error;
    const retry = Number(response.headers.get("Retry-After"));
    throw new GuestApiError(
      response.status,
      err?.code ?? "unknown_error",
      err?.message ?? "Something went wrong.",
      err?.param ?? null,
      typeof body?.attempts_remaining === "number" ? body.attempts_remaining : null,
      Number.isFinite(retry) && retry > 0 ? retry : null,
    );
  }
  return body as T;
}

export const requestCode = (reference: string, email: string) =>
  call<CodeRequested>("code", { method: "POST", body: JSON.stringify({ reference, email }) });

export const verifyCode = (challengeId: string, code: string) =>
  call<GuestPayment>("verify", { method: "POST", body: JSON.stringify({ challenge_id: challengeId, code }) });

export const getGuestPayment = () => call<GuestPayment>("payment");

export const signOut = () => call<void>("sign-out", { method: "POST", body: "{}" });
