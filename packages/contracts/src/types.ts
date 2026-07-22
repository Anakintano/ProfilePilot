/**
 * Shared types mirroring services/api/app/schemas/*.py (Pydantic is the
 * source of truth). Hand-maintained rather than codegen'd from the OpenAPI
 * schema for now — see README "Known limitations" — keep the two in sync
 * when either side changes.
 */

export type Seniority = "intern" | "entry" | "junior";

export type AnalysisStatus =
  | "queued"
  | "running"
  | "needs_review"
  | "scoring"
  | "completed"
  | "failed";

export type Stage =
  | "ingest"
  | "extract"
  | "normalize"
  | "score"
  | "recommend"
  | "audit"
  | "publish";

export type ExtractionMethod = "embedded_text" | "ocr" | "vision_llm";

export type AuditStatus =
  | "supported"
  | "unsupported"
  | "vague"
  | "contradictory"
  | "not_audited";

export type ImpactEffort = "low" | "medium" | "high";

export type ConfidenceBand = "low" | "medium" | "high";

export interface GoalProfile {
  id?: string;
  target_role: string;
  seniority: Seniority;
  geography: string;
  outcome: string;
  job_description?: string | null;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ExtractedField {
  id: string;
  upload_id: string;
  section: string;
  field_key: string;
  value: string;
  normalized_value?: unknown;
  source_page: number | null;
  bbox: BoundingBox | null;
  extraction_method: ExtractionMethod;
  confidence: number | null;
  user_corrected: boolean;
  corrected_value: string | null;
}

export interface ScoreItem {
  dimension: string;
  score: number;
  confidence: number;
  evidence_refs: string[];
  reasoning_summary: string;
  improvement_conditions: string[];
}

export interface Recommendation {
  id: string;
  priority: number;
  expected_impact: ImpactEffort;
  effort: ImpactEffort;
  source_section: string;
  original_text: string | null;
  proposed_rewrite: string;
  research_citations: string[];
  audit_status: AuditStatus;
  audit_notes: string | null;
}

export interface AnalysisReport {
  analysis_id: string;
  score_run_id: string;
  rubric_version: string;
  prompt_version: string;
  model_versions: Record<string, string>;
  total_score: number;
  confidence_band: ConfidenceBand;
  dimension_scores: ScoreItem[];
  limitations: string[];
  recommendations: Recommendation[];
  action_plan: string[];
  published_at: string;
}

export interface AnalysisOut {
  id: string;
  status: AnalysisStatus;
  current_stage: Stage;
  created_at: string;
  updated_at: string;
  error_code: string | null;
  error_message: string | null;
  report: AnalysisReport | null;
}

export interface AnalysisEventOut {
  seq: number;
  stage: Stage;
  status: AnalysisStatus;
  message: string;
  created_at: string;
}

export interface UploadCreateResponse {
  upload_id: string;
  upload_url: string;
  expires_at: string;
}

export interface UploadOut {
  id: string;
  filename: string;
  mime_type: string;
  byte_size: number;
  page_count: number | null;
  status: "pending" | "validated" | "rejected";
  rejection_reason: string | null;
  created_at: string;
  expires_at: string;
}

export interface ExtractionOut {
  analysis_id: string;
  fields: ExtractedField[];
  required_sections_covered: string[];
  required_sections_missing: string[];
  mean_confidence: number | null;
}

export type ScribeStyle =
  | "professional"
  | "storytelling"
  | "thought_leadership"
  | "casual"
  | "data_driven"
  | "listicle";

export type ScribeCommentType =
  | "engaging"
  | "supportive"
  | "insightful"
  | "question"
  | "congratulatory";

export interface ScribePostRequest {
  style: ScribeStyle;
  topic: string;
  rough_sketch?: string | null;
  use_web_search: boolean;
}

export interface ScribePostResponse {
  post_text: string;
  hashtags: string[];
}

export interface ScribeCommentRequest {
  post_content: string;
  comment_type: ScribeCommentType;
}

export interface ScribeCommentResponse {
  comment_text: string;
}
