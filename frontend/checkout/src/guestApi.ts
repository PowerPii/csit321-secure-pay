// Guest status API (gateway/apps/guest, contracts/openapi/guest-status.v1.yaml). Same origin,
// JSON only. The unlocked payment lives in an HttpOnly cookie the page never sees.
import { ApiError, jsonClient } from "./http";

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

const call = jsonClient("/guest/status", ({ status, code, message, param, retryAfter, attemptsRemaining }) =>
  new GuestApiError(status, code, message, param, attemptsRemaining, retryAfter));

export const requestCode = (reference: string, email: string) =>
  call<CodeRequested>("code", { method: "POST", body: JSON.stringify({ reference, email }) });

export const verifyCode = (challengeId: string, code: string) =>
  call<GuestPayment>("verify", { method: "POST", body: JSON.stringify({ challenge_id: challengeId, code }) });

export const getGuestPayment = () => call<GuestPayment>("payment");

export const signOut = () => call<void>("sign-out", { method: "POST", body: "{}" });
