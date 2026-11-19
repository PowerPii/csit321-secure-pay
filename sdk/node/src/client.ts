import { randomUUID } from "node:crypto";
import { SecurePayAPIError, SecurePayConnectionError, SecurePayError, SecurePaySignatureError } from "./errors.js";
import { checkSignature, REASONS, SIGNATURE_HEADER } from "./signature.js";
import type {
  ApiErrorType,
  CapturePaymentParams,
  CreatePaymentParams,
  CreateRefundParams,
  Payment,
  Refund,
  RefundList,
  SecurePayEvent,
} from "./types.js";
import { VERSION } from "./version.js";
import { constructEvent, type ConstructEventOptions } from "./webhooks.js";

export const DEFAULT_BASE_URL = "https://gateway.securepaysg.me";

export interface SecurePayOptions {
  /** Secret API key from the dashboard (`sp_test_...`). Keep it on your server. */
  apiKey: string;
  /**
   * Webhook signing secret (`whsec_...`). When set, every reply from the gateway is checked
   * against its `SecurePay-Signature` (a reply that fails throws `SecurePaySignatureError`),
   * and `webhooks.constructEvent` uses it by default. Recommended.
   */
  signingSecret?: string;
  /** Gateway address. Default `https://gateway.securepaysg.me`. */
  baseUrl?: string;
  /** Time limit for one attempt, in milliseconds. Default 30,000. */
  timeoutMs?: number;
  /**
   * Extra attempts after a network failure, a timeout, a 429, a 5xx, or a 409
   * `idempotency_request_in_progress`. Every attempt reuses the same `Idempotency-Key`, so a
   * retry never charges twice. Default 2.
   */
  maxRetries?: number;
  /** A fetch implementation. Default: the global `fetch` (Node.js 20.19 or later). */
  fetch?: typeof fetch;
  /** The API key is a secret: by default the client refuses to run in a web browser. */
  dangerouslyAllowBrowser?: boolean;
}

export interface RequestOptions {
  /**
   * For POST requests. Default: a new UUID v4 per call. Pass your own (for example derived
   * from your order ID) to make a retry after your own process restarts safe too.
   */
  idempotencyKey?: string;
  /** Override `timeoutMs` for this call. */
  timeoutMs?: number;
  /** Abort the call. */
  signal?: AbortSignal;
}

/** Facts about the HTTP reply behind a returned object. */
export interface ResponseMeta {
  /** HTTP status: 200, 201, or 202 when the simulated bank did not answer in time. */
  status: number;
  /** `SecurePay-Request-Id`. Quote it when asking for support. */
  requestId: string | null;
  /** `true` when the gateway replayed the stored reply to an earlier call with the same key. */
  idempotentReplayed: boolean;
  /** `true` when the reply's signature was checked (that is, `signingSecret` is set). */
  signatureVerified: boolean;
  /** The `Idempotency-Key` sent, for POST requests. */
  idempotencyKey: string | null;
}

/** A returned object, with `lastResponse` (not enumerable, so JSON.stringify leaves it out). */
export type WithResponse<T> = T & { readonly lastResponse: ResponseMeta };

const RETRY_STATUSES = new Set([429, 500, 502, 503, 504]);
const ID_PATTERN = /^[A-Za-z0-9_]+$/;

function pathId(kind: string, id: string): string {
  if (typeof id !== "string" || !ID_PATTERN.test(id)) {
    throw new TypeError(`${kind} must be an ID such as ${kind === "paymentId" ? "pay_..." : "rfd_..."}; got ${JSON.stringify(id)}.`);
  }
  return id;
}

function isBrowser(): boolean {
  const g = globalThis as { window?: unknown; document?: unknown };
  return typeof g.window !== "undefined" && typeof g.document !== "undefined";
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function retryAfterSeconds(headers: Headers): number | null {
  const raw = headers.get("retry-after");
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** Backoff for attempt n (0-based): 0.5 s, 1 s, 2 s ... with jitter, at most 8 s. */
function backoffMs(attempt: number): number {
  const base = Math.min(8000, 500 * 2 ** attempt);
  return base / 2 + Math.random() * (base / 2);
}

function withMeta<T extends object>(value: T, meta: ResponseMeta): WithResponse<T> {
  Object.defineProperty(value, "lastResponse", { value: meta, enumerable: false });
  return value as WithResponse<T>;
}

/**
 * Client for the SecurePay merchant API. Use it on your server only.
 *
 * ```ts
 * const securepay = new SecurePay({ apiKey: process.env.SECUREPAY_API_KEY!, signingSecret: process.env.SECUREPAY_SIGNING_SECRET });
 * const payment = await securepay.payments.create({ amount: 4590, currency: "SGD", order_reference: "ORD-10042", return_url: "https://shop.example.com/return" });
 * // send the customer to payment.checkout_url
 * ```
 */
export class SecurePay {
  readonly payments: Payments;
  readonly refunds: Refunds;
  readonly webhooks: Webhooks;

  readonly #apiKey: string;
  readonly #signingSecret: string | undefined;
  readonly #baseUrl: string;
  readonly #timeoutMs: number;
  readonly #maxRetries: number;
  readonly #fetch: typeof fetch;

  constructor(options: SecurePayOptions) {
    if (!options || typeof options.apiKey !== "string" || !options.apiKey.trim()) {
      throw new SecurePayError("An API key is required: new SecurePay({ apiKey: \"sp_test_...\" }).");
    }
    if (isBrowser() && !options.dangerouslyAllowBrowser) {
      throw new SecurePayError(
        "SecurePay's API key is a secret and must stay on your server. Create payments from your backend, " +
          "then send the customer to checkout_url. (Set dangerouslyAllowBrowser only for local experiments.)",
      );
    }
    const fetchImpl = options.fetch ?? (globalThis.fetch as typeof fetch | undefined);
    if (!fetchImpl) throw new SecurePayError("No fetch implementation found. Use Node.js 20.19 or later, or pass options.fetch.");
    this.#apiKey = options.apiKey.trim();
    this.#signingSecret = options.signingSecret || undefined;
    this.#baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.#timeoutMs = options.timeoutMs ?? 30_000;
    this.#maxRetries = Math.max(0, Math.floor(options.maxRetries ?? 2));
    this.#fetch = fetchImpl;
    this.payments = new Payments(this);
    this.refunds = new Refunds(this);
    this.webhooks = new Webhooks(this.#signingSecret);
  }

  /** @internal Sends one API call, with retries, signature checks and error mapping. */
  async request<T extends object>(method: "GET" | "POST", path: string, body?: object, options: RequestOptions = {}): Promise<WithResponse<T>> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.#apiKey}`,
      Accept: "application/json",
    };
    if (!isBrowser()) headers["User-Agent"] = `securepaysg-node/${VERSION}`;
    let idempotencyKey: string | null = null;
    let payload: string | undefined;
    if (method === "POST") {
      idempotencyKey = options.idempotencyKey ?? randomUUID();
      headers["Idempotency-Key"] = idempotencyKey;
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body ?? {});
    }
    const url = this.#baseUrl + path;
    const timeoutMs = options.timeoutMs ?? this.#timeoutMs;

    for (let attempt = 0; ; attempt++) {
      const last = attempt >= this.#maxRetries;
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(new Error(`timed out after ${timeoutMs} ms`)), timeoutMs);
      const signal = options.signal ? AbortSignal.any([options.signal, timeout.signal]) : timeout.signal;
      let response: Response;
      let text: string;
      try {
        response = await this.#fetch(url, { method, headers, body: payload, signal, redirect: "error" });
        text = await response.text();
      } catch (cause) {
        if (options.signal?.aborted) throw cause;
        if (!last) {
          await sleep(backoffMs(attempt), options.signal);
          continue;
        }
        const what = timeout.signal.aborted ? `timed out after ${timeoutMs} ms` : "failed";
        throw new SecurePayConnectionError(`${method} ${path} ${what} (${attempt + 1} attempt${attempt ? "s" : ""}).`, { cause });
      } finally {
        clearTimeout(timer);
      }

      const parsed = parseJson(text);
      const errorCode = errorBody(parsed)?.code;
      const retryable = RETRY_STATUSES.has(response.status) || (response.status === 409 && errorCode === "idempotency_request_in_progress");
      if (retryable && !last) {
        const wait = retryAfterSeconds(response.headers);
        await sleep(wait !== null ? Math.min(wait, 60) * 1000 : backoffMs(attempt), options.signal);
        continue;
      }

      const requestId = response.headers.get("securepay-request-id");
      const verified = this.#checkReply(response, text, requestId);
      if (!response.ok) throw this.#apiError(response, parsed, requestId);
      if (!parsed || typeof parsed !== "object") {
        throw new SecurePayAPIError({
          message: `The gateway sent a reply that is not JSON (HTTP ${response.status}).`,
          status: response.status,
          type: "unknown",
          code: "invalid_response",
          requestId,
          body: text,
        });
      }
      return withMeta(parsed as T, {
        status: response.status,
        requestId,
        idempotentReplayed: response.headers.get("idempotent-replayed") === "true",
        signatureVerified: verified,
        idempotencyKey,
      });
    }
  }

  /** Checks the reply's signature when a signing secret is set. 401 replies are never signed. */
  #checkReply(response: Response, text: string, requestId: string | null): boolean {
    if (!this.#signingSecret) return false;
    const header = response.headers.get(SIGNATURE_HEADER);
    // Unsigned 5xx replies can come from the proxy in front of the gateway (for example while it restarts).
    if (!header && (response.status === 401 || response.status >= 500)) return false;
    const result = checkSignature(text, header, this.#signingSecret);
    if (!result.ok) {
      throw new SecurePaySignatureError(`Reply to request ${requestId ?? "(no request ID)"} failed the signature check: ${REASONS[result.reason]}`);
    }
    return true;
  }

  #apiError(response: Response, parsed: unknown, requestId: string | null): SecurePayAPIError {
    const err = errorBody(parsed);
    return new SecurePayAPIError({
      message: err?.message ?? `HTTP ${response.status} from the gateway.`,
      status: response.status,
      type: (err?.type as ApiErrorType | undefined) ?? "unknown",
      code: err?.code ?? `http_${response.status}`,
      param: err?.param ?? null,
      requestId: err?.request_id ?? requestId,
      retryAfter: retryAfterSeconds(response.headers),
      body: parsed,
    });
  }
}

function parseJson(text: string): unknown {
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function errorBody(parsed: unknown): { type?: string; code?: string; message?: string; param?: string | null; request_id?: string } | undefined {
  if (parsed && typeof parsed === "object" && "error" in parsed) {
    const e = (parsed as { error: unknown }).error;
    if (e && typeof e === "object") return e as never;
  }
  return undefined;
}

/** `securepay.payments` */
export class Payments {
  readonly #client: SecurePay;
  constructor(client: SecurePay) {
    this.#client = client;
  }

  /**
   * Creates a payment and returns it with a `checkout_url` (valid for 1 hour). Send the
   * customer there. Never fulfil an order on the return to `return_url`: wait for the
   * `payment.authorised` webhook or call `retrieve`.
   */
  async create(params: CreatePaymentParams, options?: RequestOptions): Promise<WithResponse<Payment>> {
    return this.#client.request<Payment>("POST", "/v1/payments", params, options);
  }

  /** Gets a payment's current status (a signed reply). */
  async retrieve(paymentId: string, options?: Omit<RequestOptions, "idempotencyKey">): Promise<WithResponse<Payment>> {
    return this.#client.request<Payment>("GET", `/v1/payments/${pathId("paymentId", paymentId)}`, undefined, options);
  }

  /**
   * Captures an authorised payment: all of it, or `{ amount }` cents of it (once; the rest of
   * the authorisation is released). A 202 reply (`lastResponse.status`) means the simulated
   * bank did not answer yet: `pending_operation` is set and a `payment.captured` webhook
   * follows. Do not retry it with a new idempotency key.
   */
  async capture(paymentId: string, params: CapturePaymentParams = {}, options?: RequestOptions): Promise<WithResponse<Payment>> {
    return this.#client.request<Payment>("POST", `/v1/payments/${pathId("paymentId", paymentId)}/capture`, params, options);
  }

  /** Cancels (voids) an authorised payment. A captured payment must be refunded instead. */
  async cancel(paymentId: string, options?: RequestOptions): Promise<WithResponse<Payment>> {
    return this.#client.request<Payment>("POST", `/v1/payments/${pathId("paymentId", paymentId)}/cancel`, {}, options);
  }
}

/** `securepay.refunds` */
export class Refunds {
  readonly #client: SecurePay;
  constructor(client: SecurePay) {
    this.#client = client;
  }

  /**
   * Refunds all or part of a captured payment. `status` is `completed` or `failed` when the
   * simulated bank answered, `unresolved` when it did not (the amount stays reserved and a
   * `refund.*` webhook follows).
   */
  async create(paymentId: string, params: CreateRefundParams, options?: RequestOptions): Promise<WithResponse<Refund>> {
    return this.#client.request<Refund>("POST", `/v1/payments/${pathId("paymentId", paymentId)}/refunds`, params, options);
  }

  /** Lists a payment's refunds, oldest first, with what is still refundable. */
  async list(paymentId: string, options?: Omit<RequestOptions, "idempotencyKey">): Promise<WithResponse<RefundList>> {
    return this.#client.request<RefundList>("GET", `/v1/payments/${pathId("paymentId", paymentId)}/refunds`, undefined, options);
  }

  /** Gets one refund (a signed reply). */
  async retrieve(refundId: string, options?: Omit<RequestOptions, "idempotencyKey">): Promise<WithResponse<Refund>> {
    return this.#client.request<Refund>("GET", `/v1/refunds/${pathId("refundId", refundId)}`, undefined, options);
  }
}

/** `securepay.webhooks` */
export class Webhooks {
  readonly #secret: string | undefined;
  constructor(secret: string | undefined) {
    this.#secret = secret;
  }

  /**
   * Verifies a webhook with the client's `signingSecret` (or the `secret` option) and returns
   * the event. Throws `SecurePaySignatureError` when the check fails.
   */
  constructEvent(
    payload: string | Uint8Array,
    signatureHeader: string | null | undefined,
    options: ConstructEventOptions & { secret?: string } = {},
  ): SecurePayEvent {
    const secret = options.secret ?? this.#secret;
    if (!secret) throw new SecurePayError("No signing secret: pass signingSecret to new SecurePay(...) or { secret } here.");
    return constructEvent(payload, signatureHeader, secret, options);
  }
}
