//go:build integration

// POST /:id/confirm-submit (docs/BACKEND_BUILD_STEPS.md Step 44): a human
// confirming a ready_for_review application.
package handlers

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/rr4323/autoapply/backend/api/internal/store"
)

func seedReadyForReviewApplication(t *testing.T, ctx context.Context, queries *store.Queries, pool *pgxpool.Pool) (userIDStr, appIDStr string) {
	t.Helper()

	user, err := queries.CreateUser(ctx, "confirm-submit-test@example.com")
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
	if _, err := pool.Exec(ctx, "UPDATE applications SET status = 'ready_for_review' WHERE id = $1", app.ID); err != nil {
		t.Fatalf("failed to seed ready_for_review status: %v", err)
	}

	return uuidString(user.ID), uuidString(app.ID)
}

func postConfirmSubmit(t *testing.T, router http.Handler, userID, appID string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost,
		"/api/v1/applications/"+appID+"/confirm-submit", nil)
	req.Header.Set("X-Demo-User-ID", userID)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)
	return rec
}

func TestConfirmSubmitAPI_TransitionsReadyForReviewToSubmitted(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)
	userID, appID := seedReadyForReviewApplication(t, ctx, queries, pool)

	rec := postConfirmSubmit(t, router, userID, appID)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp confirmSubmitResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.Status != "submitted" {
		t.Errorf("status = %q, want submitted", resp.Status)
	}
	if resp.SubmittedAt == nil {
		t.Error("submitted_at was not set")
	}

	appUUID := mustParseUUID(t, appID)
	events, err := queries.ListApplicationEvents(ctx, appUUID)
	if err != nil {
		t.Fatalf("failed to list application events: %v", err)
	}
	if len(events) != 1 || events[0].EventType != "manual_confirm_submit" {
		t.Fatalf("application_events = %+v, want exactly one manual_confirm_submit event", events)
	}
}

func TestConfirmSubmitAPI_NotReadyForReviewReturns409(t *testing.T) {
	ctx := context.Background()
	router, queries, _, _ := setupTestRouter(t)

	user, err := queries.CreateUser(ctx, "confirm-submit-pending@example.com")
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

	rec := postConfirmSubmit(t, router, uuidString(user.ID), uuidString(app.ID))

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409 for a still-pending application, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestConfirmSubmitAPI_RetryAfterSubmitReturns409(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)
	userID, appID := seedReadyForReviewApplication(t, ctx, queries, pool)

	first := postConfirmSubmit(t, router, userID, appID)
	if first.Code != http.StatusOK {
		t.Fatalf("first call: expected 200, got %d: %s", first.Code, first.Body.String())
	}

	second := postConfirmSubmit(t, router, userID, appID)
	if second.Code != http.StatusConflict {
		t.Fatalf("second call: expected 409 (already submitted), got %d: %s", second.Code, second.Body.String())
	}
}

func TestConfirmSubmitAPI_OtherUsersApplicationReturns404(t *testing.T) {
	ctx := context.Background()
	router, queries, _, pool := setupTestRouter(t)
	_, appID := seedReadyForReviewApplication(t, ctx, queries, pool)

	otherUser, err := queries.CreateUser(ctx, "someone-else@example.com")
	if err != nil {
		t.Fatalf("create other user failed: %v", err)
	}

	rec := postConfirmSubmit(t, router, uuidString(otherUser.ID), appID)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for another user's application, got %d: %s", rec.Code, rec.Body.String())
	}
}
