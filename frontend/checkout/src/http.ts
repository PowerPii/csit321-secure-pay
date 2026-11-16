// JSON transport shared by the customer-facing APIs. Each API keeps its own error type.
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

export interface Failure {
  status: number;
  code: string;
  message: string;
  param: string | null;
  retryAfter: number | null;
  attemptsRemaining: number | null;
}

const defaultError = ({ status, code, message, param }: Failure) =>
  new ApiError(status, code, message, param);

export function jsonClient(base: string, makeError: (failure: Failure) => ApiError = defaultError) {
  return async function call<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${base}/${path}`, {
        ...init,
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch {
      throw makeError({ status: 0, code: "network_error",
        message: "We couldn't reach SecurePay. Check your connection and try again.",
        param: null, retryAfter: null, attemptsRemaining: null });
    }
    if (response.status === 204) return undefined as T;
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const err = body?.error;
      const retry = Number(response.headers.get("Retry-After"));
      throw makeError({
        status: response.status,
        code: err?.code ?? "unknown_error",
        message: err?.message ?? "Something went wrong.",
        param: err?.param ?? null,
        retryAfter: Number.isFinite(retry) && retry > 0 ? retry : null,
        attemptsRemaining: typeof body?.attempts_remaining === "number" ? body.attempts_remaining : null,
      });
    }
    return body as T;
  };
}
