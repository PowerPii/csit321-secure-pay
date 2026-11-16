// Thin wrapper over the gateway's staff API (/internal/*). Session cookie + CSRF token;
// the backend is the authority on permissions and merchant scoping.
export type PaymentStatus =
  | "created" | "screening" | "verification_required" | "processing" | "authorised"
  | "captured" | "declined" | "blocked" | "unresolved" | "cancelled" | "expired";

export type Role = "merchant_operator" | "fraud_analyst" | "administrator";

export interface ErrorBody {
  error?: { type: string; code: string; message: string; param: string | null };
}

export class ApiError extends Error {
  constructor(public status: number, public body: ErrorBody | null) {
    super(body?.error?.message ?? `Request failed (${status})`);
  }
  get code(): string | undefined {
    return this.body?.error?.code;
  }
}

function csrfToken(): string {
  // Read on every request: signing in rotates the token.
  return document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] ?? "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (init.method && init.method !== "GET" && !csrfToken()) {
    // First POST of a visit (sign-in): GET /me sets the CSRF cookie, even when it answers 401.
    await fetch("/internal/me", { credentials: "same-origin" }).catch(() => undefined);
  }
  const res = await fetch(`/internal${path}`, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), ...init.headers },
  });
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

export function post<T>(path: string, body: unknown = {}): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

// --- shapes --------------------------------------------------------------------------------

export interface Staff {
  id: string;
  email: string;
  name: string;
  role: Role;
  role_label: string;
  merchant: { id: string; name: string; status?: Merchant["status"] } | null;
}

export interface Card { brand: string; last4: string }
export interface MerchantRef { id: string; name: string }

export interface PaymentRow {
  id: string;
  reference: string;
  order_reference: string;
  merchant: MerchantRef;
  amount: number;
  currency: string;
  status: PaymentStatus;
  refunded_amount: number;
  card: Card | null;
  risk: { decision: string; verification: string | null } | null;
  customer: string | null;
  outcome_reason: string | null;
  created_at: string;
}

export interface Page<T> {
  count: number;
  page: number;
  page_size: number;
  data: T[];
}

export interface PaymentList extends Page<PaymentRow> {
  summary: {
    awaiting_capture: number;
    unresolved: number;
    blocked_today: number;
    refunded_this_month: number;
    escalated: number | null;
  };
}

export interface Screening {
  id: string;
  outcome: string;
  score: number | null;
  reasons: string[];
  features: Record<string, number>;
  model_version: string | null;
  rules_version: string | null;
  policy_version: string | null;
  feature_schema_version: string | null;
  thresholds: { verify: number; block: number } | null;
  elapsed_ms: number;
  error: string | null;
  occurred_at: string;
}

export interface Operation {
  id: string;
  type: string;
  status: string;
  amount: number;
  simulator_reference: string | null;
  reconciliation_checks: number;
  last_checked_at: string | null;
  next_check_at: string | null;
  escalated_at: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Refund {
  id: string;
  reference: string;
  amount: number;
  status: string;
  reason: string | null;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface TimelineEntry {
  at: string;
  action: string;
  actor_type: string;
  actor: string | null;
  target_type: string;
  target_id: string;
  details: Record<string, unknown>;
}

export interface Webhook {
  id: string;
  type: string;
  sequence: number;
  status: string;
  attempts: number;
  last_http_status: number | null;
  last_error: string | null;
  next_attempt_at: string | null;
  delivered_at: string | null;
}

export interface PaymentDetail {
  id: string;
  reference: string;
  order_reference: string;
  status: PaymentStatus;
  amount: number;
  currency: string;
  line_items: { name: string; quantity: number; unit_amount: number }[] | null;
  captured_amount: number;
  refundable_amount: number;
  refunded_amount: number;
  refund_reserved_amount: number;
  card: { token: string; brand: string; last4: string } | null;
  outcome: { reason: string; message: string } | null;
  pending_operation: { type: string; status: string; requested_at: string } | null;
  authorisation_expires_at: string | null;
  created_at: string;
  authorised_at: string | null;
  captured_at: string | null;
  cancelled_at: string | null;
  merchant: MerchantRef;
  customer: string | null;
  description: string | null;
  screening: Screening | null;
  screening_decision: string | null;
  verification: string | null;
  operations: Operation[];
  refunds: Refund[];
  webhooks: Webhook[];
  timeline: TimelineEntry[];
  actions: { capture: boolean; cancel: boolean; refund: boolean; recheck: boolean; review: boolean };
}

export interface Review {
  status: "open" | "closed";
  assigned_to: { id: string; name: string } | null;
  finding: string | null;
  notes: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface CaseRow {
  id: string;
  payment: { id: string; reference: string; amount: number; currency: string; status: PaymentStatus };
  merchant: MerchantRef;
  score: number | null;
  outcome: string;
  decision: string;
  reasons: string[];
  occurred_at: string;
  review: Review;
}

export interface CaseList extends Page<CaseRow> {
  counts: { open: number; mine: number; closed: number };
}

export interface LinkCount { attempts: number; merchants: number; blocked: number }

export interface CaseDetail extends CaseRow {
  payment: CaseRow["payment"] & {
    order_reference: string;
    card: Card | null;
    customer: string | null;
    outcome_reason: string | null;
    created_at: string;
  };
  screening: Screening;
  linked_activity: { window_hours: number; card: LinkCount | null; email: LinkCount | null; ip: LinkCount | null };
  related: {
    case_id: string | null;
    payment: { id: string; reference: string; status: PaymentStatus };
    merchant: string;
    amount: number;
    outcome: string;
    score: number | null;
    shared: string[];
    occurred_at: string;
  }[];
}

export interface Merchant {
  id: string;
  name: string;
  status: "pending" | "active" | "rejected" | "suspended";
  webhook_url: string | null;
  webhook_url_approved: boolean;
  max_amount_cents: number | null;
  api_key: { id: string; hint: string; last_used_at: string | null } | null;
  created_at: string;
  credentials?: { api_key: string; signing_secret: string };
  self_registered?: boolean;
  registration?: {
    registration_number: string;
    website: string;
    contact_name: string;
    contact_email: string;
    email_verified_at: string | null;
  } | null;
}

/** The signed-in operator's own merchant (D8). */
export interface OwnMerchant {
  id: string;
  name: string;
  status: Merchant["status"];
  registration_number: string | null;
  webhook_url: string | null;
  webhook_url_approved: boolean;
  api_key: { id: string; hint: string; created_at: string; last_used_at: string | null } | null;
  can_generate_key: boolean;
  credentials?: { api_key: string; signing_secret: string };
}

export interface AuditRow {
  id: number;
  at: string;
  action: string;
  actor_type: string;
  actor_id: string | null;
  merchant_id: string | null;
  target_type: string | null;
  target_id: string | null;
  request_id: string | null;
  details: Record<string, unknown>;
}
