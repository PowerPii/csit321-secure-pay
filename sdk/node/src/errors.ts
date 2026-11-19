import type { ApiErrorType } from "./types.js";

/** Base class of every error this library throws. */
export class SecurePayError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = new.target.name;
  }
}

/**
 * The gateway answered with an error (4xx or 5xx). `code` is the stable, machine-readable
 * code from the error table (for example `refund_exceeds_refundable`); `message` may change.
 */
export class SecurePayAPIError extends SecurePayError {
  /** HTTP status, for example 422. */
  readonly status: number;
  /** Broad class: invalid_request, authentication, permission, not_found, conflict, business_rule, rate_limit or server. */
  readonly type: ApiErrorType | "unknown";
  /** Stable error code, for example `idempotency_key_reused`. */
  readonly code: string;
  /** The request field at fault, if any. */
  readonly param: string | null;
  /** Quote this when asking for support (also the `SecurePay-Request-Id` header). */
  readonly requestId: string | null;
  /** Seconds to wait before trying again, from `Retry-After` (429 and some 409s). */
  readonly retryAfter: number | null;
  /** The parsed reply body, if it was JSON. */
  readonly body: unknown;

  constructor(init: {
    message: string;
    status: number;
    type: ApiErrorType | "unknown";
    code: string;
    param?: string | null;
    requestId?: string | null;
    retryAfter?: number | null;
    body?: unknown;
  }) {
    super(init.message);
    this.status = init.status;
    this.type = init.type;
    this.code = init.code;
    this.param = init.param ?? null;
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
    this.body = init.body;
  }
}

/** The request never got an answer: network failure or timeout (after any retries). */
export class SecurePayConnectionError extends SecurePayError {}

/**
 * A `SecurePay-Signature` header is missing, malformed, too old, or does not match the body.
 * Thrown by `webhooks.constructEvent`, and by the client when `signingSecret` is set and a
 * reply fails the check. Never act on a payload that failed this check.
 */
export class SecurePaySignatureError extends SecurePayError {}
