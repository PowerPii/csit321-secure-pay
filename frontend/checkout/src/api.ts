// The hosted checkout API (gateway/apps/checkout). Same origin, JSON only, session-bound:
// the browser sends card details and "pay"; it can never set merchant, amount or currency.

export type Result =
  | "open"
  | "processing"
  | "verification_required"
  | "approved"
  | "declined"
  | "not_completed"
  | "pending"
  | "cancelled"
  | "expired";

export interface Session {
  session_id: string;
  status: string;
  result: Result;
  merchant: { name: string };
  amount: number;
  currency: string;
  order_reference: string;
  description: string | null;
  reference: string | null;
  email_required: boolean;
  customer_email_masked: string | null;
  card: { brand: string; last4: string } | null;
  expires_at: string;
  submitted_at: string | null;
  authorised_at: string | null;
  return_url: string;
}

export interface CardInput {
  number: string;
  expiry_month: number;
  expiry_year: number;
  cvc: string;
  email?: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public param: string | null = null,
  ) {
    super(message);
  }
}

const API_BASE = "/checkout";

async function call(path: string, init?: RequestInit): Promise<Session> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/${path}`, {
      ...init,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "We couldn't reach SecurePay. Check your connection and try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const err = body?.error;
    throw new ApiError(response.status, err?.code ?? "unknown_error", err?.message ?? "Something went wrong.", err?.param ?? null);
  }
  return body as Session;
}

export const getSession = (sessionId: string) => call(encodeURIComponent(sessionId));

export const addCard = (sessionId: string, card: CardInput) =>
  call(`${encodeURIComponent(sessionId)}/card`, { method: "POST", body: JSON.stringify(card) });

export const submit = (sessionId: string) =>
  call(`${encodeURIComponent(sessionId)}/submit`, { method: "POST", body: "{}" });
