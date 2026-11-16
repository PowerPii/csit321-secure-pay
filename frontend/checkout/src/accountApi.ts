// Customer account API (gateway/apps/customers), screens C10 to C12. Same origin, JSON only.
// The session lives in the HttpOnly `sp_customer` cookie; the page never sees it.
import { ApiError } from "./api";

export interface Customer {
  id: string;
  full_name: string;
  email: string;
  idle_minutes: number;
}

export interface HistoryRow {
  reference: string;
  merchant_name: string;
  amount: number;
  currency: string;
  status: string;
  status_label: string;
  created_at: string;
}

export interface PaymentDetail extends HistoryRow {
  order_reference: string;
  card: { brand: string; last4: string } | null;
  refunded_amount?: number;
  timeline: { at: string; label: string }[];
}

export class AccountApiError extends ApiError {
  constructor(status: number, code: string, message: string, param: string | null, public retryAfter: number | null) {
    super(status, code, message, param);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/customer/${path}`, {
      ...init,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new AccountApiError(0, "network_error", "We couldn't reach SecurePay. Check your connection and try again.", null, null);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const err = body?.error;
    const retry = Number(response.headers.get("Retry-After"));
    throw new AccountApiError(
      response.status,
      err?.code ?? "unknown_error",
      err?.message ?? "Something went wrong.",
      err?.param ?? null,
      Number.isFinite(retry) && retry > 0 ? retry : null,
    );
  }
  return body as T;
}

const post = <T>(path: string, body: unknown = {}) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const getMe = () => call<Customer>("me");
export const signIn = (email: string, password: string, remember: boolean) =>
  post<Customer>("sign-in", { email, password, remember });
export const register = (full_name: string, email: string, password: string) =>
  post<Customer>("register", { full_name, email, password });
export const signOut = () => post<void>("sign-out");
export const signOutEverywhere = () => post<void>("sign-out-everywhere");
export const changePassword = (current_password: string, password: string) =>
  post<{ message: string }>("password", { current_password, password });
export const getPayments = () => call<{ data: HistoryRow[]; has_more: boolean }>("payments");
export const getPayment = (reference: string) => call<PaymentDetail>(`payments/${encodeURIComponent(reference)}`);
export const requestReset = (email: string) => post<{ message: string }>("password-reset/request", { email });
export const checkReset = (token: string) => post<{ email: string }>("password-reset/check", { token });
export const confirmReset = (token: string, password: string) =>
  post<{ message: string }>("password-reset/confirm", { token, password });
