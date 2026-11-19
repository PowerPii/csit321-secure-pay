import type { ApiErrorType } from "./types.js";

/** Base class of every error this library throws. */
export class SecurePayError extends Error {
  /**
   * The `Idempotency-Key` the failed `POST` was sent with (every attempt used the same one),
   * or `null` for a `GET` or an error raised before anything was sent. When `outcomeUnknown`
   * is `true`, retry with exactly this key: the gateway then replays the first result instead
   * of running the operation twice.
   */
  readonly idempotencyKey: string | null;
  /**
   * `true` when the gateway may have carried out the request even though no usable reply
   * arrived: a network failure or timeout, a 5xx or `409 idempotency_request_in_progress`
   * after the last retry, or a reply that failed the signature check. Never answer such an
   * error with a new key; retry with `idempotencyKey`, or look the operation up first.
   */
  readonly outcomeUnknown: boolean;

  constructor(message: string, options?: { cause?: unknown; idempotencyKey?: string | null; outcomeUnknown?: boolean }) {
    super(message, options?.cause === undefined ? undefined : { cause: options.cause });
    this.name = new.target.name;
    this.idempotencyKey = options?.idempotencyKey ?? null;
    this.outcomeUnknown = options?.outcomeUnknown ?? false;
  }
}

/**
 * The gateway answered with an error (4xx or 5xx). `code` is the stable, machine-readable
 * code from the error table (for example `refund_exceeds_refundable`); `message` may change.
 * A 4xx means nothing happened (or, for `409 idempotency_key_reused`, the key belongs to a
 * different request). A 5xx after the retries sets `outcomeUnknown`.
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
    idempotencyKey?: string | null;
  }) {
    super(init.message, {
      idempotencyKey: init.idempotencyKey,
      outcomeUnknown: init.status >= 500 || (init.status === 409 && init.code === "idempotency_request_in_progress"),
    });
    this.status = init.status;
    this.type = init.type;
    this.code = init.code;
    this.param = init.param ?? null;
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
    this.body = init.body;
  }
}

/**
 * The request never got an answer: network failure or timeout (after any retries). The
 * gateway may still have done the work, so `outcomeUnknown` is always `true`: retry with
 * `idempotencyKey` (within 24 hours), or look the operation up before doing anything else.
 */
export class SecurePayConnectionError extends SecurePayError {
  /** How many attempts were made, all with the same `idempotencyKey`. */
  readonly attempts: number;

  constructor(message: string, options: { cause?: unknown; idempotencyKey?: string | null; attempts: number }) {
    super(message, { cause: options.cause, idempotencyKey: options.idempotencyKey, outcomeUnknown: true });
    this.attempts = options.attempts;
  }
}

/**
 * A `SecurePay-Signature` header is missing, malformed, too old, or does not match the body.
 * Thrown by `webhooks.constructEvent`, and by the client when `signingSecret` is set and a
 * reply fails the check (then `outcomeUnknown` is `true` and `idempotencyKey` is set for a
 * `POST`). Never act on a payload that failed this check.
 */
export class SecurePaySignatureError extends SecurePayError {}
