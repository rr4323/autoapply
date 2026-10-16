//go:build integration

// The actual M1 exit criterion (docs/BACKEND_BUILD_STEPS.md Step 17):
// one POST /applications produces two side effects — an application_events
// row AND a message on the jd.discovered Redis stream — proven
// independently of what the HTTP response itself claims.
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgtype"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
)

func TestApplicationsAPI_M1Exit_PublishesAndRecordsEvent(t *testing.T) {
	ctx := context.Background()
	router, queries, redisClient, _ := setupTestRouter(t)

	user, err := queries.CreateUser(ctx, "m1-exit@example.com")
	if err != nil {
		t.Fatalf("create user failed: %v", err)
	}

	// --- the one curl ---
	createReq := httptest.NewRequestWithContext(ctx, http.MethodPost, "/api/v1/applications",
		bytes.NewBufferString(`{"jd_url": "https://boards.greenhouse.io/example/jobs/456"}`))
	createReq.Header.Set("X-Demo-User-ID", uuidString(user.ID))
	createRec := httptest.NewRecorder()
	router.ServeHTTP(createRec, createReq)

	if createRec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", createRec.Code, createRec.Body.String())
	}
	var created applicationCreatedResponse
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("failed to decode create response: %v", err)
	}

	var appID pgtype.UUID
	if err := appID.Scan(created.ID); err != nil {
		t.Fatalf("failed to parse created id %q: %v", created.ID, err)
	}

	// --- side effect 1: application_events row exists ---
	events, err := queries.ListApplicationEvents(ctx, appID)
	if err != nil {
		t.Fatalf("list events failed: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("expected exactly 1 application_events row, got %d", len(events))
	}
	if events[0].EventType != bus.TopicJDDiscovered {
		t.Fatalf("expected event_type %q, got %q", bus.TopicJDDiscovered, events[0].EventType)
	}
	if events[0].ProducedByAgent != "api" {
		t.Fatalf("expected produced_by_agent %q, got %q", "api", events[0].ProducedByAgent)
	}

	// --- side effect 2: a message actually landed on the jd.discovered stream ---
	entries, err := redisClient.XRange(ctx, bus.TopicJDDiscovered, "-", "+").Result()
	if err != nil {
		t.Fatalf("xrange failed: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected exactly 1 entry on %q, got %d", bus.TopicJDDiscovered, len(entries))
	}
	if entries[0].Values["job_id"] != created.ID {
		t.Fatalf("stream entry job_id mismatch: got %v, want %v", entries[0].Values["job_id"], created.ID)
	}
	payloadRef, _ := entries[0].Values["payload_ref"].(string)
	if payloadRef == "" {
		t.Fatal("expected a non-empty payload_ref on the published envelope")
	}

	// --- bonus: working memory actually holds the JD content the
	// payload_ref points at, not just a dangling reference ---
	wmContent, err := redisClient.Get(ctx, payloadRef).Result()
	if err != nil {
		t.Fatalf("expected working memory content at %q, got error: %v", payloadRef, err)
	}
	var wm struct {
		JDUrl *string `json:"jd_url"`
	}
	if err := json.Unmarshal([]byte(wmContent), &wm); err != nil {
		t.Fatalf("failed to decode working memory content: %v", err)
	}
	if wm.JDUrl == nil || *wm.JDUrl != "https://boards.greenhouse.io/example/jobs/456" {
		t.Fatalf("unexpected working memory content: %+v", wm)
	}
}
