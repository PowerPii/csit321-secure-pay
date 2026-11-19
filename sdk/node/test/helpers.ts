import { readFileSync } from "node:fs";
import { join } from "node:path";
import { signPayload } from "../src/index.js";

// Tests run from sdk/node (npm test), so the contract examples are two folders up.
export const CONTRACTS = join(process.cwd(), "..", "..", "contracts");

export function example(rel: string): string {
  return readFileSync(join(CONTRACTS, "examples", rel), "utf8");
}

export const SECRET = "whsec_test_vector_secret";

export interface Call {
  url: string;
  init: RequestInit;
  headers: Record<string, string>;
}

type Reply = { status: number; body?: string; headers?: Record<string, string>; sign?: boolean } | Error;

/** A fetch that answers from a script of replies and records each call. */
export function fakeFetch(replies: Reply[]) {
  const calls: Call[] = [];
  const impl = (async (input: string | URL | Request, init: RequestInit = {}) => {
    const headers = Object.fromEntries(Object.entries((init.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v]));
    calls.push({ url: String(input), init, headers });
    const r = replies.shift();
    if (!r) throw new Error("fakeFetch: no reply left");
    if (r instanceof Error) throw r;
    const body = r.body ?? "";
    const h = new Headers(r.headers);
    if (r.sign !== false && r.status !== 401) h.set("SecurePay-Signature", signPayload(body, SECRET));
    if (!h.has("SecurePay-Request-Id")) h.set("SecurePay-Request-Id", "req_TEST00000000000000000001");
    return new Response(body || null, { status: r.status, headers: h });
  }) as typeof fetch;
  return { impl, calls };
}
