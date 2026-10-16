//go:build integration

// M4 exit — the §7.3 enforcement boundary (docs/BACKEND_BUILD_STEPS.md
// Step 33): a compromised or buggy agent claiming "submit" must never be
// honored just because it claims it — Go re-derives the decision itself.
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/rr4323/autoapply/backend/api/internal/store"
)

func mustParseUUID(t *testing.T, s string) pgtype.UUID {
	t.Helper()
	var id pgtype.UUID
	if err := id.Scan(s); err != nil {
		t.Fatalf("failed to parse UUID %q: %v", s, err)
	}
	return id
}

func seedApplicationWithScore(
	t *testing.T, ctx context.Context, queries *store.Queries, pool *pgxpool.Pool, score float64,
) string {
	t.Helper()

	user, err := queries.CreateUser(ctx, "callback-test@example.com")
	if err != nil {
		t.Fatalf("create user failed: %v", err)
	}
	app, err := queries.CreateApplication(ctx, store.CreateApplicationParams{
		UserID: user.ID,
		Source: store.ApplicationSourceManual,
	})
	if err != nil {
		t.Fatalf("create application failed: %v", err)
	}

	if _, err := pool.Exec(ctx, "UPDATE applications SET jd_fit_score = $1 WHERE id = $2", score, app.ID); err != nil {
		t.Fatalf("failed to seed jd_fit_score: %v", err)
	}

	return uuidString(app.ID)
}

func postCallback(t *testing.T, router http.Handler, jobID, action string, botCheckDetected bool) *httptest.ResponseRecorder {
	t.Helper()

	body, err := json.Marshal(map[string]any{
		"job_id":             jobID,
		"action":             action,
		"bot_check_detected": botCheckDetected,
	})
	if err != nil {
		t.Fatalf("failed to encode request body: %v", err)
	}

	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost,
		"/internal/agent/callback", bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Secret", testInternalSharedSecret)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)
	return rec
}

// TestAgentCallback_AdversarialSubmitClaim_GoWins is Step 33's required
// adversarial test: an agent claims "submit" for an application whose
// score — as Go's own database independently records it, not anything
// the agent asserts — is below min_autosubmit_score. Go's re-check must
// disagree with the claim and win: no submit honored, the rejection
// audited in both policy_decisions and application_events.
func TestAgentCallback_AdversarialSubmitClaim_GoWins(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)

	jobID := seedApplicationWithScore(t, ctx, queries, pool, 40) // below min_autosubmit_score (80)

	rec := postCallback(t, router, jobID, "submit", false)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp agentCallbackResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.Accepted {
		t.Fatal("expected accepted=false — Go must not honor the agent's submit claim")
	}
	if resp.Action != "require_review" {
		t.Fatalf("action = %q, want require_review", resp.Action)
	}
	if len(resp.Reasons) == 0 {
		t.Fatal("expected non-empty reasons — §7.2 requires reasons on every path")
	}

	// The application must NOT be marked submitted.
	var appID = mustParseUUID(t, jobID)
	app, err := queries.GetApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to reload application: %v", err)
	}
	if app.Status == store.ApplicationStatusSubmitted {
		t.Fatal("application status is submitted — the agent's claim was wrongly honored")
	}
	if app.Status != store.ApplicationStatusReadyForReview {
		t.Fatalf("status = %v, want ready_for_review", app.Status)
	}
	if app.SubmittedAt.Valid {
		t.Fatal("submitted_at was set despite the submit being rejected")
	}

	// Audited: policy_decisions row.
	decisions, err := queries.ListPolicyDecisionsForApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list policy decisions: %v", err)
	}
	if len(decisions) != 1 || decisions[0].Action != "require_review" {
		t.Fatalf("policy_decisions = %+v, want exactly one require_review row", decisions)
	}
	if decisions[0].DecisionPoint != "pre_submit" {
		t.Errorf("decision_point = %v, want pre_submit", decisions[0].DecisionPoint)
	}

	// Audited: application_events row (TDD.md §8 names "submit-blocked...").
	events, err := queries.ListApplicationEvents(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list application events: %v", err)
	}
	if len(events) != 1 || events[0].EventType != "submit-blocked" {
		t.Fatalf("application_events = %+v, want exactly one submit-blocked event", events)
	}
}

// TestAgentCallback_BotCheckClaimedButSubmitRequested_GoWins covers a
// second adversarial shape: the agent's own report says a bot-check was
// detected, yet it still requests "submit". Go must not treat "action:
// submit" as an override of the very context the agent just reported.
func TestAgentCallback_BotCheckClaimedButSubmitRequested_GoWins(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)

	jobID := seedApplicationWithScore(t, ctx, queries, pool, 95) // comfortably above every threshold

	rec := postCallback(t, router, jobID, "submit", true) // bot_check_detected: true

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp agentCallbackResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.Accepted || resp.Action != "require_review" {
		t.Fatalf("expected a rejected require_review decision, got %+v", resp)
	}

	appID := mustParseUUID(t, jobID)
	events, err := queries.ListApplicationEvents(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list application events: %v", err)
	}
	if len(events) != 1 || events[0].EventType != "submit-blocked-by-captcha" {
		t.Fatalf("application_events = %+v, want exactly one submit-blocked-by-captcha event", events)
	}
}

// TestAgentCallback_CleanSubmit_Honored is the companion clean-pass case
// — Go's re-check agreeing with a legitimate claim, so the enforcement
// boundary isn't just a gate that never opens.
func TestAgentCallback_CleanSubmit_Honored(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)

	jobID := seedApplicationWithScore(t, ctx, queries, pool, 95)

	rec := postCallback(t, router, jobID, "submit", false)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp agentCallbackResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if !resp.Accepted || resp.Action != "submit" {
		t.Fatalf("expected an accepted submit decision, got %+v", resp)
	}

	appID := mustParseUUID(t, jobID)
	app, err := queries.GetApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to reload application: %v", err)
	}
	if app.Status != store.ApplicationStatusSubmitted {
		t.Fatalf("status = %v, want submitted", app.Status)
	}
	if !app.SubmittedAt.Valid {
		t.Fatal("submitted_at was not set")
	}
}

// TestAgentCallback_RetriedSubmitCallback_IsIdempotent proves a second
// callback for an already-submitted application doesn't re-evaluate or
// double-count against the velocity cap.
func TestAgentCallback_RetriedSubmitCallback_IsIdempotent(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)

	jobID := seedApplicationWithScore(t, ctx, queries, pool, 95)

	first := postCallback(t, router, jobID, "submit", false)
	if first.Code != http.StatusOK {
		t.Fatalf("first call: expected 200, got %d: %s", first.Code, first.Body.String())
	}

	second := postCallback(t, router, jobID, "submit", false)
	if second.Code != http.StatusOK {
		t.Fatalf("second call: expected 200, got %d: %s", second.Code, second.Body.String())
	}

	appID := mustParseUUID(t, jobID)
	decisions, err := queries.ListPolicyDecisionsForApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list policy decisions: %v", err)
	}
	if len(decisions) != 1 {
		t.Fatalf("policy_decisions rows = %d, want 1 (retry must not re-evaluate)", len(decisions))
	}
}
