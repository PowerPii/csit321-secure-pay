import { createHmac, timingSafeEqual } from "node:crypto";

/** Header on every signed reply and every webhook. */
export const SIGNATURE_HEADER = "SecurePay-Signature";
/** Default allowed clock difference, in seconds (the gateway's webhook rule: 5 minutes). */
export const DEFAULT_TOLERANCE_SECONDS = 300;

export type Payload = string | Uint8Array;

function toBytes(payload: Payload): Buffer {
  if (typeof payload === "string") return Buffer.from(payload, "utf8");
  if (payload instanceof Uint8Array) return Buffer.from(payload.buffer, payload.byteOffset, payload.byteLength);
  throw new TypeError(
    "The payload must be the raw request body (string, Buffer or Uint8Array), not parsed JSON. " +
      "In Express use express.raw({ type: \"application/json\" }) on the webhook route.",
  );
}

/** HMAC-SHA256 of `"<timestamp>." + body`, as lowercase hex. */
export function computeSignature(payload: Payload, secret: string, timestamp: number): string {
  return createHmac("sha256", secret).update(`${timestamp}.`).update(toBytes(payload)).digest("hex");
}

/** Builds a `SecurePay-Signature` value, for example to test your own webhook handler. */
export function signPayload(payload: Payload, secret: string, timestamp: number = Math.floor(Date.now() / 1000)): string {
  return `t=${timestamp},v1=${computeSignature(payload, secret, timestamp)}`;
}

export type SignatureCheck =
  | { ok: true; timestamp: number }
  | { ok: false; reason: "missing_header" | "malformed_header" | "timestamp_out_of_range" | "no_match" };

/** Checks a `SecurePay-Signature` header against the raw body. Does not throw. */
export function checkSignature(
  payload: Payload,
  header: string | null | undefined,
  secret: string,
  options: { toleranceSeconds?: number; now?: number } = {},
): SignatureCheck {
  if (!secret) throw new TypeError("A signing secret (whsec_...) is required to check signatures.");
  const bytes = toBytes(payload);
  if (!header) return { ok: false, reason: "missing_header" };
  let timestamp: number | null = null;
  const given: string[] = [];
  for (const part of header.split(",")) {
    const eq = part.indexOf("=");
    if (eq < 1) continue;
    const key = part.slice(0, eq).trim();
    const value = part.slice(eq + 1).trim();
    if (key === "t" && /^\d+$/.test(value)) timestamp = Number(value);
    else if (key === "v1" && /^[0-9a-f]{64}$/.test(value)) given.push(value);
  }
  if (timestamp === null || given.length === 0) return { ok: false, reason: "malformed_header" };
  const tolerance = options.toleranceSeconds ?? DEFAULT_TOLERANCE_SECONDS;
  const now = options.now ?? Math.floor(Date.now() / 1000);
  if (tolerance > 0 && Math.abs(now - timestamp) > tolerance) return { ok: false, reason: "timestamp_out_of_range" };
  const expected = Buffer.from(computeSignature(bytes, secret, timestamp), "hex");
  const match = given.some((g) => timingSafeEqual(expected, Buffer.from(g, "hex")));
  return match ? { ok: true, timestamp } : { ok: false, reason: "no_match" };
}

/** `true` when the header is a valid, fresh signature of the raw body. */
export function verifySignature(
  payload: Payload,
  header: string | null | undefined,
  secret: string,
  options: { toleranceSeconds?: number; now?: number } = {},
): boolean {
  return checkSignature(payload, header, secret, options).ok;
}

export const REASONS: Record<Exclude<SignatureCheck, { ok: true }>["reason"], string> = {
  missing_header: `No ${SIGNATURE_HEADER} header.`,
  malformed_header: `The ${SIGNATURE_HEADER} header is not in the form t=<unix seconds>,v1=<64 hex characters>.`,
  timestamp_out_of_range: `The ${SIGNATURE_HEADER} timestamp is outside the allowed clock difference. Check your server clock, or this may be a replayed message.`,
  no_match: `The ${SIGNATURE_HEADER} does not match the body. Check the signing secret, and pass the raw body exactly as received.`,
};
