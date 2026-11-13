// Pure helpers and labels for the dashboard (tested in format.test.ts).
import type { PaymentStatus } from "./api/client";

const ZONE = "Asia/Singapore"; // dashboard dates are Singapore time, like the gateway's filters

/** 8990 -> "S$ 89.90" (amounts are integer cents, SGD only). */
export function money(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100).toLocaleString("en-SG");
  return `${sign}S$ ${dollars}.${String(abs % 100).padStart(2, "0")}`;
}

/** "89.90", "89.9", "89" or "S$ 89.90" -> 8990; null if it is not a valid amount. */
export function parseMoney(text: string): number | null {
  const clean = text.replace(/S\$|\s|,/gi, "");
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  const [whole, frac = ""] = clean.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}

/** "2026-11-02T06:52:00Z" -> "2 Nov, 14:52" (Singapore time). */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-SG", {
    timeZone: ZONE, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

/** "2 Nov 2026, 14:52" */
export function longDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-SG", {
    timeZone: ZONE, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    hour12: false,
  });
}

/** "14:52:05" */
export function timeOnly(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-SG", { timeZone: ZONE, hour12: false });
}

export function cardLabel(card: { brand: string; last4: string } | null): string {
  if (!card) return "";
  const brand = { visa: "Visa", mastercard: "MC", amex: "Amex" }[card.brand] ?? card.brand;
  return `${brand} •••• ${card.last4}`;
}

export const STATUS_LABELS: Record<PaymentStatus, string> = {
  created: "Created",
  screening: "Screening",
  verification_required: "Awaiting code",
  processing: "Processing",
  authorised: "Authorised",
  captured: "Captured",
  declined: "Declined",
  blocked: "Blocked",
  unresolved: "Unresolved",
  cancelled: "Cancelled",
  expired: "Expired",
};

/** The status shown on D3/D4: a captured payment with refunds reads "Refunded" or
 *  "Partially refunded", as in the wireframes. */
export function statusLabel(status: PaymentStatus, amount = 0, refunded = 0): string {
  if (status === "captured" && refunded > 0) return refunded >= amount ? "Refunded" : "Partially refunded";
  return STATUS_LABELS[status] ?? status;
}

/** Dark badges for settled money, outlined for everything else (wireframe Badge tones). */
export function statusTone(status: PaymentStatus): "dark" | "neutral" {
  return status === "captured" ? "dark" : "neutral";
}

export function riskLabel(risk: { decision: string; verification: string | null } | null): string {
  if (!risk) return "";
  if (risk.decision === "verify") return `Verify · ${risk.verification ?? "pending"}`;
  return { allow: "Allow", block: "Block", not_screened: "Not screened" }[risk.decision] ?? risk.decision;
}

export const CASE_DECISION_LABELS: Record<string, string> = {
  blocked: "Blocked",
  verify_failed: "Verify failed",
  verify_passed: "Verify passed",
  verify_pending: "Verify pending",
};

/** Why screening flagged an attempt, in words an analyst or merchant can act on. */
export const REASON_LABELS: Record<string, string> = {
  blocklisted_card: "Card on blocklist",
  blocklisted_email: "Email on blocklist",
  blocklisted_ip: "IP address on blocklist",
  review_list_card: "Card on review list",
  review_list_email: "Email on review list",
  review_list_ip: "IP address on review list",
  amount_over_limit: "Amount over the limit",
  card_attempt_burst: "Burst of attempts with this card (10 min)",
  high_amount: "Amount over S$ 500",
  model_score_high: "Model score at or above the block threshold",
  model_score_medium: "Model score at or above the verify threshold",
  screening_unavailable: "Screening unavailable (not a fraud finding)",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code.replace(/_/g, " ");
}

export const FINDING_LABELS: Record<string, string> = {
  confirmed_fraud: "Confirmed fraud",
  false_positive: "False positive",
  inconclusive: "Inconclusive",
};

export const FEATURE_LABELS: Record<string, string> = {
  amount_cents: "Amount (cents)",
  card_attempts_10m: "Card attempts, 10 min",
  card_attempts_1h: "Card attempts, 1 h",
  card_attempts_24h: "Card attempts, 24 h",
  card_blocked_24h: "Card blocked, 24 h",
  card_distinct_emails_24h: "Emails on this card, 24 h",
  card_allowed_30d: "Card allowed, 30 days",
  email_attempts_24h: "Email attempts, 24 h",
  email_distinct_cards_24h: "Cards on this email, 24 h",
  ip_attempts_1h: "IP attempts, 1 h",
  ip_distinct_cards_1h: "Cards from this IP, 1 h",
};

/** Audit actions as status-history lines (D4). */
const ACTION_LABELS: Record<string, string> = {
  "payment.created": "Created by merchant API",
  "checkout.card_added": "Card entered on the hosted checkout (tokenised in the vault)",
  "payment.submitted": "Submitted and screened",
  "payment.verification_required": "Screening: Verify, code sent",
  "payment.verification_code_resent": "Verification code sent again",
  "payment.verification_failed_attempt": "Wrong verification code",
  "payment.verified": "Verification code passed",
  "payment.authorised": "Authorised by the simulator",
  "payment.declined": "Declined",
  "payment.blocked": "Blocked",
  "payment.unresolved": "No answer from the simulator: unresolved",
  "payment.expired": "Checkout expired",
  "payment.capture_requested": "Capture requested",
  "payment.captured": "Captured",
  "payment.cancel_requested": "Cancel requested",
  "payment.cancelled": "Cancelled",
  "payment.capture_unresolved": "Capture sent, no answer yet",
  "payment.cancel_unresolved": "Cancel sent, no answer yet",
  "payment.capture_not_processed": "Capture not processed by the simulator",
  "payment.cancel_not_processed": "Cancel not processed by the simulator",
  "payment.capture_rejected_by_processor": "Capture refused by the simulator",
  "payment.cancel_rejected_by_processor": "Cancel refused by the simulator",
  "refund.requested": "Refund requested",
  "refund.rejected": "Refund rejected: more than the refundable amount",
  "refund.completed": "Refund completed",
  "refund.failed": "Refund failed",
  "refund.unresolved": "Refund sent, no answer yet",
  "operation.escalated": "Escalated to administrators after status checks",
  "operation.rechecked": "Re-checked with the simulator",
  "operation.recheck_no_answer": "Re-checked: still no answer",
  "review.assigned": "Fraud case assigned",
  "review.unassigned": "Fraud case unassigned",
  "review.finding_recorded": "Fraud finding recorded",
  "review.reopened": "Fraud case reopened",
};

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replace(/[._]/g, " ");
}

export function actorLabel(actorType: string, actor: string | null): string {
  if (actorType === "merchant_api") return `merchant API${actor ? ` (${actor.slice(0, 8)}…)` : ""}`;
  if (actorType === "staff") return actor ?? "staff";
  if (actorType === "customer") return "customer";
  return actor ? `system (${actor})` : "system";
}

export function titleCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).replace(/_/g, " ");
}
