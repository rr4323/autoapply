// Hand-written to match backend/api/internal/handlers/dto.go and
// backend/api/openapi.yaml exactly — Go is the source of truth. If a
// field is added/renamed on the Go side, update it here in the same
// change (docs/BACKEND_BUILD_STEPS.md's "Contract discipline" rule).

// Matches the Postgres application_status enum exactly (migrations/).
export type ApplicationStatus =
  | 'pending'
  | 'scored'
  | 'below_threshold'
  | 'filling'
  | 'ready_for_review'
  | 'needs_input'
  | 'submitted'
  | 'failed'

export interface ApplicationSummary {
  id: string
  company: string | null
  role_title: string | null
  source: 'manual' | 'discovered'
  search_profile_id: string | null
  search_profile_name: string | null
  jd_fit_score: number | null
  resume_match_score: number | null
  status: ApplicationStatus
  bot_check_detected: boolean
  submitted_at: string | null
  created_at: string
}

export interface ScoreSignal {
  value: number
  weight: number
  contribution: number
}

export interface ScoreBreakdown {
  score: number
  scoring_model_version: string
  signals: Record<string, ScoreSignal>
}

export interface RetrievedEvidenceItem {
  chunk_id: string
  text: string
  similarity: number
}

export type GeneratedDocumentType = 'resume' | 'cover_letter' | 'screener_answer'

export interface GeneratedDocumentItem {
  id: string
  type: GeneratedDocumentType
  storage_ref: string
  source_chunk_ids: string[]
  groundedness_score: number
}

export interface PolicyDecisionItem {
  decision_point: 'post_scoring' | 'pre_submit'
  action: string
  reasons: string[]
  created_at: string
}

export interface ApplicationDetail extends ApplicationSummary {
  jd_url: string | null
  score_breakdown: ScoreBreakdown | null
  retrieved_evidence: RetrievedEvidenceItem[]
  generated_documents: GeneratedDocumentItem[]
  policy_decisions: PolicyDecisionItem[]
  outcome: string | null
  updated_at: string
}

export interface ApplicationCreated {
  id: string
  status: string
  source: string
  created_at: string
}

export interface ConfirmSubmitResult {
  id: string
  status: string
  submitted_at: string | null
}

export interface ExperienceEntry {
  id: string
  company: string
  title: string
  start_date: string
  end_date: string | null
  bullets: string[]
}

export interface Profile {
  id: string
  base_resume_doc_id: string | null
  skills: string[]
  experience: ExperienceEntry[]
}

export interface PutProfileRequest {
  base_resume_doc_id: string | null
  skills: string[]
  experience: ExperienceEntry[]
}

export interface PutProfileResult {
  id: string
  reindexing: boolean
}

export interface ApiErrorBody {
  error: { code: string; message: string }
}
