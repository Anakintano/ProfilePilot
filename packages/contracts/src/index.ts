export * from "./types";

export const REQUIRED_SECTIONS = ["contact", "experience", "education", "skills"] as const;

export const ALLOWED_UPLOAD_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;

export const WORKFLOW_STAGES = [
  "ingest",
  "extract",
  "normalize",
  "score",
  "recommend",
  "audit",
  "publish",
] as const;
