import type {
  AnalysisOut,
  ExtractionOut,
  GoalProfile,
  ScribeCommentRequest,
  ScribeCommentResponse,
  ScribePostRequest,
  ScribePostResponse,
  UploadCreateResponse,
} from "@contracts/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function createUpload(input: { filename: string; mime_type: string; byte_size: number }) {
  return request<UploadCreateResponse>("/v1/uploads", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function putUploadBytes(uploadUrl: string, file: File): Promise<void> {
  const res = await fetch(uploadUrl, { method: "PUT", body: file });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
}

export function createAnalysis(input: { goal_profile: GoalProfile; upload_ids: string[] }, idempotencyKey: string) {
  return request<{ analysis_id: string; status: string }>("/v1/analyses", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  });
}

export function getAnalysis(id: string) {
  return request<AnalysisOut>(`/v1/analyses/${id}`);
}

export function getExtraction(id: string) {
  return request<ExtractionOut>(`/v1/analyses/${id}/extraction`);
}

export function patchExtraction(id: string, corrections: { field_id: string; corrected_value: string }[]) {
  return request<{ analysis_id: string; status: string }>(`/v1/analyses/${id}/extraction`, {
    method: "PATCH",
    body: JSON.stringify({ corrections }),
  });
}

export function submitFeedback(
  analysisId: string,
  input: {
    recommendation_id: string;
    accepted?: boolean | null;
    rejection_reason?: string | null;
    usefulness_score?: number | null;
    corrected_text?: string | null;
  }
) {
  return request<{ id: string }>(`/v1/analyses/${analysisId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ analysis_id: analysisId, ...input }),
  });
}

export function eventsUrl(analysisId: string): string {
  return `${API_URL}/v1/analyses/${analysisId}/events`;
}

export function deleteMyData() {
  return request<{ deleted: Record<string, number> }>("/v1/me/data", {
    method: "DELETE",
  });
}

export function generateScribePost(input: ScribePostRequest) {
  return request<ScribePostResponse>("/v1/scribe/post", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function generateScribeComment(input: ScribeCommentRequest) {
  return request<ScribeCommentResponse>("/v1/scribe/comment", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export { API_URL, ApiError };
