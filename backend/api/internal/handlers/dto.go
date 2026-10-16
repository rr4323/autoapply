// Package handlers implements the HTTP handlers for the public API
// surface, matching backend/api/openapi.yaml exactly (docs/BACKEND_BUILD_STEPS.md
// Step 15). retrieved_evidence and search_profile_name are still always
// empty/null — per-application retrieval results are never persisted
// (Step 26's context.retrieved is ephemeral, working-memory-only) and
// search profiles don't exist yet. score_breakdown, generated_documents,
// and policy_decisions are populated for real (Step 45) from the tables
// the Scoring/Generator/Policy Engine agents actually write to.
package handlers

import (
	"encoding/json"
	"math"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgtype"

	"github.com/rr4323/autoapply/backend/api/internal/store"
)

type createApplicationRequest struct {
	JDUrl  *string `json:"jd_url"`
	JDText *string `json:"jd_text"`
}

type applicationCreatedResponse struct {
	ID        string `json:"id"`
	Status    string `json:"status"`
	Source    string `json:"source"`
	CreatedAt string `json:"created_at"`
}

type confirmSubmitResponse struct {
	ID          string  `json:"id"`
	Status      string  `json:"status"`
	SubmittedAt *string `json:"submitted_at"`
}

type applicationSummaryResponse struct {
	ID                string  `json:"id"`
	Company           *string `json:"company"`
	RoleTitle         *string `json:"role_title"`
	Source            string  `json:"source"`
	SearchProfileID   *string `json:"search_profile_id"`
	SearchProfileName *string `json:"search_profile_name"`
	JDFitScore        *int32  `json:"jd_fit_score"`
	ResumeMatchScore  *int32  `json:"resume_match_score"`
	Status            string  `json:"status"`
	BotCheckDetected  bool    `json:"bot_check_detected"`
	SubmittedAt       *string `json:"submitted_at"`
	CreatedAt         string  `json:"created_at"`
}

// scoreSignalContribution and scoreBreakdownResponse mirror the exact
// shape ScoreBreakdown.to_json_dict() (backend/agents/.../scoring/combiner.py)
// writes into applications.score_breakdown_json — Python is the writer,
// this is just an honest reader, not an independently-designed contract.
type scoreSignalContribution struct {
	Value        float64 `json:"value"`
	Weight       float64 `json:"weight"`
	Contribution float64 `json:"contribution"`
}

type scoreBreakdownResponse struct {
	Score               int                                `json:"score"`
	ScoringModelVersion string                             `json:"scoring_model_version"`
	Signals             map[string]scoreSignalContribution `json:"signals"`
}

type retrievedEvidenceItem struct {
	ChunkID    string  `json:"chunk_id"`
	Text       string  `json:"text"`
	Similarity float64 `json:"similarity"`
}

type generatedDocumentItem struct {
	ID                string   `json:"id"`
	Type              string   `json:"type"`
	StorageRef        string   `json:"storage_ref"`
	SourceChunkIDs    []string `json:"source_chunk_ids"`
	GroundednessScore float64  `json:"groundedness_score"`
}

type policyDecisionItem struct {
	DecisionPoint string   `json:"decision_point"`
	Action        string   `json:"action"`
	Reasons       []string `json:"reasons"`
	CreatedAt     string   `json:"created_at"`
}

// applicationDetailResponse embeds applicationSummaryResponse anonymously
// so encoding/json flattens its fields into this struct's JSON object —
// matching openapi.yaml's `allOf: [ApplicationSummary, {...}]` shape.
type applicationDetailResponse struct {
	applicationSummaryResponse
	JDUrl              *string                 `json:"jd_url"`
	ScoreBreakdown     *scoreBreakdownResponse `json:"score_breakdown"`
	RetrievedEvidence  []retrievedEvidenceItem `json:"retrieved_evidence"`
	GeneratedDocuments []generatedDocumentItem `json:"generated_documents"`
	PolicyDecisions    []policyDecisionItem    `json:"policy_decisions"`
	Outcome            *string                 `json:"outcome"`
	UpdatedAt          string                  `json:"updated_at"`
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type errorResponse struct {
	Error errorBody `json:"error"`
}

func writeJSONError(w http.ResponseWriter, status int, code, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(errorResponse{Error: errorBody{Code: code, Message: message}})
}

func toSummary(a store.Application) applicationSummaryResponse {
	return applicationSummaryResponse{
		ID:                uuidString(a.ID),
		Company:           a.Company,
		RoleTitle:         a.RoleTitle,
		Source:            string(a.Source),
		SearchProfileID:   nullableUUIDString(a.SearchProfileID),
		SearchProfileName: nil, // requires a join with search_profiles — not built yet
		JDFitScore:        scoreToInt32Ptr(a.JdFitScore),
		ResumeMatchScore:  scoreToInt32Ptr(a.ResumeMatchScore),
		Status:            string(a.Status),
		BotCheckDetected:  a.BotCheckDetected,
		SubmittedAt:       nullableTimestampString(a.SubmittedAt),
		CreatedAt:         timestampString(a.CreatedAt),
	}
}

func parseScoreBreakdown(raw []byte) *scoreBreakdownResponse {
	if len(raw) == 0 {
		return nil
	}
	var breakdown scoreBreakdownResponse
	if err := json.Unmarshal(raw, &breakdown); err != nil {
		// Malformed score_breakdown_json is a data problem, not a reason
		// to 500 the whole application detail response — the rest of the
		// payload (status, documents, decisions) is still useful without it.
		return nil
	}
	return &breakdown
}

func toGeneratedDocuments(docs []store.GeneratedDocument) []generatedDocumentItem {
	items := make([]generatedDocumentItem, 0, len(docs))
	for _, d := range docs {
		var groundedness float64
		if d.GroundednessScore != nil {
			groundedness = *d.GroundednessScore
		}
		chunkIDs := make([]string, 0, len(d.SourceChunkIds))
		for _, c := range d.SourceChunkIds {
			chunkIDs = append(chunkIDs, uuidString(c))
		}
		items = append(items, generatedDocumentItem{
			ID:                uuidString(d.ID),
			Type:              string(d.Type),
			StorageRef:        d.StorageRef,
			SourceChunkIDs:    chunkIDs,
			GroundednessScore: groundedness,
		})
	}
	return items
}

func toPolicyDecisions(decisions []store.PolicyDecision) []policyDecisionItem {
	items := make([]policyDecisionItem, 0, len(decisions))
	for _, d := range decisions {
		var reasons []string
		_ = json.Unmarshal(d.ReasonsJson, &reasons)
		items = append(items, policyDecisionItem{
			DecisionPoint: d.DecisionPoint,
			Action:        d.Action,
			Reasons:       reasons,
			CreatedAt:     timestampString(d.CreatedAt),
		})
	}
	return items
}

func uuidString(id pgtype.UUID) string {
	v, _ := id.Value()
	s, _ := v.(string)
	return s
}

func nullableUUIDString(id pgtype.UUID) *string {
	if !id.Valid {
		return nil
	}
	s := uuidString(id)
	return &s
}

func timestampString(t pgtype.Timestamptz) string {
	return t.Time.UTC().Format(time.RFC3339)
}

func nullableTimestampString(t pgtype.Timestamptz) *string {
	if !t.Valid {
		return nil
	}
	s := timestampString(t)
	return &s
}

func scoreToInt32Ptr(f *float64) *int32 {
	if f == nil {
		return nil
	}
	v := int32(math.Round(*f))
	return &v
}
