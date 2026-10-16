package handlers

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
	"github.com/rr4323/autoapply/backend/api/internal/middleware"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

// workingMemoryTTL bounds how long a job's working-memory scratchpad
// survives (TDD.md §5 — "cleared after the job reaches a terminal state").
// No terminal-state-triggered cleanup exists yet (that needs the Verifier
// Agent, much later), so a generous fixed TTL is the interim backstop.
const workingMemoryTTL = 24 * time.Hour

type ApplicationsHandler struct {
	Queries       *store.Queries
	Pool          *pgxpool.Pool
	Publisher     *bus.Publisher
	WorkingMemory *bus.WorkingMemory
}

func NewApplicationsHandler(q *store.Queries, pool *pgxpool.Pool, pub *bus.Publisher, wm *bus.WorkingMemory) *ApplicationsHandler {
	return &ApplicationsHandler{Queries: q, Pool: pool, Publisher: pub, WorkingMemory: wm}
}

// Create handles POST /api/v1/applications — submit a JD manually. The
// application row and its application_events audit row are written in
// one Postgres transaction (docs/BACKEND_BUILD_STEPS.md Step 17's M1
// exit criterion); the jd.discovered bus publish happens after that
// transaction commits, since a single atomic write spanning Postgres
// and Redis isn't possible without infrastructure (a transactional
// outbox) this project hasn't built. If the publish fails after a
// successful commit, the create has still genuinely succeeded — that's
// logged loudly as an operational problem, not surfaced as a client error.
func (h *ApplicationsHandler) Create(w http.ResponseWriter, r *http.Request) {
	userID, ok := currentUserID(w, r)
	if !ok {
		return
	}

	var req createApplicationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json", "request body must be valid JSON")
		return
	}

	hasURL := req.JDUrl != nil && *req.JDUrl != ""
	hasText := req.JDText != nil && *req.JDText != ""
	if hasURL == hasText {
		writeJSONError(w, http.StatusBadRequest, "invalid_request", "exactly one of jd_url or jd_text is required")
		return
	}

	ctx := r.Context()

	tx, err := h.Pool.Begin(ctx)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to start transaction")
		return
	}
	defer func() { _ = tx.Rollback(ctx) }() // no-op once committed below

	qtx := h.Queries.WithTx(tx)

	app, err := qtx.CreateApplication(ctx, store.CreateApplicationParams{
		UserID: userID,
		JdUrl:  req.JDUrl,
		JdText: req.JDText,
		Source: store.ApplicationSourceManual,
	})
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to create application")
		return
	}

	traceID := uuid.NewString()
	jobID := uuidString(app.ID)

	eventPayload, err := json.Marshal(map[string]any{
		"trace_id": traceID,
		"jd_url":   req.JDUrl,
		"jd_text":  req.JDText,
	})
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to encode event payload")
		return
	}

	if _, err := qtx.AppendApplicationEvent(ctx, store.AppendApplicationEventParams{
		ApplicationID:   app.ID,
		EventType:       bus.TopicJDDiscovered,
		ProducedByAgent: "api",
		PayloadJson:     eventPayload,
	}); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to record application event")
		return
	}

	if err := tx.Commit(ctx); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to commit transaction")
		return
	}

	wmKey := bus.WorkingMemoryKey(jobID, "jd_discovered")
	if err := h.WorkingMemory.Set(ctx, wmKey, map[string]any{
		"jd_url":  req.JDUrl,
		"jd_text": req.JDText,
	}, workingMemoryTTL); err != nil {
		slog.Error("failed to write working memory", "job_id", jobID, "error", err)
	}

	envelope := bus.Envelope{
		JobID:      jobID,
		TraceID:    traceID,
		EventType:  bus.TopicJDDiscovered,
		ProducedBy: "api",
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		PayloadRef: wmKey,
	}
	if _, err := h.Publisher.Publish(ctx, bus.TopicJDDiscovered, envelope); err != nil {
		slog.Error("failed to publish jd.discovered", "job_id", jobID, "error", err)
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(applicationCreatedResponse{
		ID:        jobID,
		Status:    string(app.Status),
		Source:    string(app.Source),
		CreatedAt: timestampString(app.CreatedAt),
	})
}

// List handles GET /api/v1/applications — optionally filtered by status[],
// limited to the current user's own applications. Cursor-based pagination
// (openapi.yaml's `cursor` param) isn't implemented yet — next_cursor is
// always null, which a correct client reads as "no more pages" rather
// than behaving incorrectly.
func (h *ApplicationsHandler) List(w http.ResponseWriter, r *http.Request) {
	userID, ok := currentUserID(w, r)
	if !ok {
		return
	}

	// []string, not []store.ApplicationStatus — pgx has no default encode
	// plan for a Go slice of a custom enum type; the query casts to
	// text[]/text on the Postgres side instead (see the query comment).
	statuses := r.URL.Query()["status"]
	if statuses == nil {
		statuses = []string{}
	}

	limit := int32(20)
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 && parsed <= 100 {
			limit = int32(parsed)
		}
	}

	apps, err := h.Queries.ListApplicationsByUserFiltered(r.Context(), store.ListApplicationsByUserFilteredParams{
		UserID:       userID,
		StatusFilter: statuses,
		RowLimit:     limit,
	})
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to list applications")
		return
	}

	data := make([]applicationSummaryResponse, 0, len(apps))
	for _, a := range apps {
		data = append(data, toSummary(a))
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"data":        data,
		"next_cursor": nil,
	})
}

// Get handles GET /api/v1/applications/{id} — full application detail,
// scoped to the current user so a guessed/leaked id from another user
// can't resolve.
func (h *ApplicationsHandler) Get(w http.ResponseWriter, r *http.Request) {
	userID, ok := currentUserID(w, r)
	if !ok {
		return
	}

	var appID pgtype.UUID
	if err := appID.Scan(chi.URLParam(r, "id")); err != nil {
		writeJSONError(w, http.StatusNotFound, "not_found", "application not found")
		return
	}

	app, err := h.Queries.GetApplicationForUser(r.Context(), store.GetApplicationForUserParams{
		ID:     appID,
		UserID: userID,
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSONError(w, http.StatusNotFound, "not_found", "application not found")
			return
		}
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to fetch application")
		return
	}

	documents, err := h.Queries.ListGeneratedDocumentsForApplication(r.Context(), appID)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to fetch generated documents")
		return
	}

	decisions, err := h.Queries.ListPolicyDecisionsForApplication(r.Context(), appID)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to fetch policy decisions")
		return
	}

	detail := applicationDetailResponse{
		applicationSummaryResponse: toSummary(app),
		JDUrl:                      app.JdUrl,
		ScoreBreakdown:             parseScoreBreakdown(app.ScoreBreakdownJson),
		RetrievedEvidence:          []retrievedEvidenceItem{},
		GeneratedDocuments:         toGeneratedDocuments(documents),
		PolicyDecisions:            toPolicyDecisions(decisions),
		Outcome:                    nil,
		UpdatedAt:                  timestampString(app.UpdatedAt),
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(detail)
}

// ConfirmSubmit handles POST /api/v1/applications/{id}/confirm-submit — a
// human confirming a ready_for_review application (docs/BACKEND_BUILD_STEPS.md
// Step 44). This is a different trust boundary than the automated §7.3
// enforcement callback (Step 33): that boundary exists because an agent's
// claim can't be trusted; here, an authenticated user is making an
// informed decision about their own application, which is what
// ready_for_review is waiting for in the first place — no further
// automated gate re-runs on top of it.
func (h *ApplicationsHandler) ConfirmSubmit(w http.ResponseWriter, r *http.Request) {
	userID, ok := currentUserID(w, r)
	if !ok {
		return
	}

	var appID pgtype.UUID
	if err := appID.Scan(chi.URLParam(r, "id")); err != nil {
		writeJSONError(w, http.StatusNotFound, "not_found", "application not found")
		return
	}

	ctx := r.Context()

	tx, err := h.Pool.Begin(ctx)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to start transaction")
		return
	}
	defer func() { _ = tx.Rollback(ctx) }()

	qtx := h.Queries.WithTx(tx)

	app, err := qtx.GetApplicationForUser(ctx, store.GetApplicationForUserParams{
		ID:     appID,
		UserID: userID,
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSONError(w, http.StatusNotFound, "not_found", "application not found")
			return
		}
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to fetch application")
		return
	}

	if app.Status != store.ApplicationStatusReadyForReview {
		writeJSONError(w, http.StatusConflict, "invalid_state",
			"application is not ready_for_review")
		return
	}

	updated, err := qtx.MarkApplicationSubmitted(ctx, appID)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to confirm submission")
		return
	}

	if _, err := qtx.AppendApplicationEvent(ctx, store.AppendApplicationEventParams{
		ApplicationID:   appID,
		EventType:       "manual_confirm_submit",
		ProducedByAgent: "api",
		PayloadJson:     []byte(`{"initiated_by":"user"}`),
	}); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to record confirmation event")
		return
	}

	if err := tx.Commit(ctx); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to commit transaction")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(confirmSubmitResponse{
		ID:          uuidString(updated.ID),
		Status:      string(updated.Status),
		SubmittedAt: nullableTimestampString(updated.SubmittedAt),
	})
}

// currentUserID reads the stub identity from context (Step 14) and parses
// it as a UUID, writing the appropriate error response itself if either
// step fails so handlers can just `if !ok { return }`.
func currentUserID(w http.ResponseWriter, r *http.Request) (pgtype.UUID, bool) {
	idStr, ok := middleware.UserIDFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "missing user context")
		return pgtype.UUID{}, false
	}

	var id pgtype.UUID
	if err := id.Scan(idStr); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "invalid user id")
		return pgtype.UUID{}, false
	}

	return id, true
}
