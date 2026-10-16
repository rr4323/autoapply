//go:build integration

// GET/PUT /api/v1/profile round trip against a real Postgres container
// (docs/BACKEND_BUILD_STEPS.md Step 16), including upsert semantics and
// the experience_json array round trip (migration 0006).
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestProfileAPI_GetBeforePutIsNotFound(t *testing.T) {
	ctx := context.Background()
	router, queries, _, _ := setupTestRouter(t)

	user, err := queries.CreateUser(ctx, "profile-empty@example.com")
	if err != nil {
		t.Fatalf("create user failed: %v", err)
	}

	req := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/profile", nil)
	req.Header.Set("X-Demo-User-ID", uuidString(user.ID))
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 before any profile is saved, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestProfileAPI_PutThenGetRoundTrip(t *testing.T) {
	ctx := context.Background()
	router, queries, _, _ := setupTestRouter(t)

	user, err := queries.CreateUser(ctx, "profile-roundtrip@example.com")
	if err != nil {
		t.Fatalf("create user failed: %v", err)
	}
	userIDStr := uuidString(user.ID)

	putBody := `{
		"base_resume_doc_id": "storage_ref:resumes/first.pdf",
		"skills": ["Go", "Python"],
		"experience": [
			{"id": "e1", "company": "Acme", "title": "Engineer", "start_date": "2020-01", "end_date": null, "bullets": ["Built things"]}
		]
	}`
	putReq := httptest.NewRequestWithContext(ctx, http.MethodPut, "/api/v1/profile", bytes.NewBufferString(putBody))
	putReq.Header.Set("X-Demo-User-ID", userIDStr)
	putRec := httptest.NewRecorder()
	router.ServeHTTP(putRec, putReq)

	if putRec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", putRec.Code, putRec.Body.String())
	}
	var putResp putProfileResponse
	if err := json.Unmarshal(putRec.Body.Bytes(), &putResp); err != nil {
		t.Fatalf("failed to decode put response: %v", err)
	}
	if putResp.Reindexing {
		t.Fatal("expected reindexing=false — the re-embedding pipeline doesn't exist yet")
	}

	// --- GET reflects what was just saved ---
	getReq := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/profile", nil)
	getReq.Header.Set("X-Demo-User-ID", userIDStr)
	getRec := httptest.NewRecorder()
	router.ServeHTTP(getRec, getReq)

	if getRec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", getRec.Code, getRec.Body.String())
	}
	var profile profileResponse
	if err := json.Unmarshal(getRec.Body.Bytes(), &profile); err != nil {
		t.Fatalf("failed to decode get response: %v", err)
	}
	if profile.ID != putResp.ID {
		t.Fatalf("id mismatch: get=%s put=%s", profile.ID, putResp.ID)
	}
	if len(profile.Skills) != 2 || profile.Skills[0] != "Go" {
		t.Fatalf("unexpected skills: %+v", profile.Skills)
	}
	if len(profile.Experience) != 1 || profile.Experience[0].Company != "Acme" {
		t.Fatalf("unexpected experience: %+v", profile.Experience)
	}

	// --- PUT again with different data — must upsert, not duplicate ---
	secondPutBody := `{"skills": ["Rust"], "experience": []}`
	secondPutReq := httptest.NewRequestWithContext(ctx, http.MethodPut, "/api/v1/profile", bytes.NewBufferString(secondPutBody))
	secondPutReq.Header.Set("X-Demo-User-ID", userIDStr)
	secondPutRec := httptest.NewRecorder()
	router.ServeHTTP(secondPutRec, secondPutReq)

	if secondPutRec.Code != http.StatusAccepted {
		t.Fatalf("expected 202 on second put, got %d: %s", secondPutRec.Code, secondPutRec.Body.String())
	}
	var secondPutResp putProfileResponse
	_ = json.Unmarshal(secondPutRec.Body.Bytes(), &secondPutResp)
	if secondPutResp.ID != putResp.ID {
		t.Fatalf("expected the SAME profile id after upsert (not a new row): first=%s second=%s", putResp.ID, secondPutResp.ID)
	}

	finalGetReq := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/profile", nil)
	finalGetReq.Header.Set("X-Demo-User-ID", userIDStr)
	finalGetRec := httptest.NewRecorder()
	router.ServeHTTP(finalGetRec, finalGetReq)

	var finalProfile profileResponse
	_ = json.Unmarshal(finalGetRec.Body.Bytes(), &finalProfile)
	if len(finalProfile.Skills) != 1 || finalProfile.Skills[0] != "Rust" {
		t.Fatalf("expected skills overwritten to [Rust], got %+v", finalProfile.Skills)
	}
	if len(finalProfile.Experience) != 0 {
		t.Fatalf("expected experience overwritten to empty, got %+v", finalProfile.Experience)
	}
}
