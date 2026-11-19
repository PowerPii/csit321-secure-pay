import { SecurePaySignatureError } from "./errors.js";
import { checkSignature, REASONS, type Payload } from "./signature.js";
import type { SecurePayEvent } from "./types.js";

export interface ConstructEventOptions {
  /** Allowed clock difference in seconds. Default 300 (5 minutes). */
  toleranceSeconds?: number;
  /** Current time in unix seconds, for tests. */
  now?: number;
}

/**
 * Verifies a webhook and returns the parsed event. Throws `SecurePaySignatureError` if the
 * signature is missing, stale or wrong.
 *
 * After this, still: ignore an event `id` you have already handled, and ignore an event whose
 * `sequence` is not higher than the one you stored for that payment (events can arrive out of
 * order). Reply 2xx within 10 seconds; do slow work afterwards.
 *
 * @param payload The raw request body, exactly as received (not re-serialised JSON).
 * @param header  The `SecurePay-Signature` request header.
 * @param secret  Your webhook signing secret (`whsec_...`) from the dashboard.
 */
export function constructEvent(
  payload: Payload,
  header: string | null | undefined,
  secret: string,
  options: ConstructEventOptions = {},
): SecurePayEvent {
  const result = checkSignature(payload, header, secret, options);
  if (!result.ok) throw new SecurePaySignatureError(REASONS[result.reason]);
  const text = typeof payload === "string" ? payload : new TextDecoder().decode(payload);
  let event: unknown;
  try {
    event = JSON.parse(text);
  } catch (cause) {
    throw new SecurePaySignatureError("The webhook body is signed but is not JSON.", { cause });
  }
  if (!event || typeof event !== "object" || (event as { object?: unknown }).object !== "event") {
    throw new SecurePaySignatureError("The webhook body is signed but is not a SecurePay event.");
  }
  return event as SecurePayEvent;
}
