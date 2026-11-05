// Thin wrapper over the gateway's staff API (/internal/*). Session cookie + CSRF token;
// the backend is the authority on permissions and merchant scoping.
export type PaymentStatus =
  | "created" | "screening" | "verification_required" | "processing" | "authorised"
  | "captured" | "declined" | "blocked" | "unresolved" | "cancelled" | "expired";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}`);
  }
}

function csrfToken(): string {
  return document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] ?? "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/internal${path}`, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), ...init.headers },
  });
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}
