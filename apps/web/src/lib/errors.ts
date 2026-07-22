import { ApiError } from "./api";

/**
 * API errors carry a raw response body (usually FastAPI's `{"detail": "..."}"`).
 * Unwrap that JSON shape when present so screens can surface the exact
 * server-provided reason (e.g. a rejection_reason or quota message) verbatim.
 */
export function getApiErrorDetail(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message);
      if (parsed && typeof parsed.detail === "string") return parsed.detail;
    } catch {
      // body wasn't JSON — fall through to raw message
    }
    return err.message || "Something went wrong talking to the server.";
  }
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

export function isApiErrorStatus(err: unknown, status: number): boolean {
  return err instanceof ApiError && err.status === status;
}
