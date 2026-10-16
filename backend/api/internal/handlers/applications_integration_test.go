//go:build integration

// Create -> list -> detail round trip against a real Postgres container
// and the real chi routes (docs/BACKEND_BUILD_STEPS.md Step 15).
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	tcredis "github.com/testcontainers/testcontainers-go/modules/redis"
	"github.com/testcontainers/testcontainers-go/wait"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
	"github.com/rr4323/autoapply/backend/api/internal/middleware"
	"github.com/rr4323/autoapply/backend/api/internal/policy"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

const testInternalSharedSecret = "test-internal-secret"

func setupTestRouter(t *testing.T) (http.Handler, *store.Queries, *redis.Client, *pgxpool.Pool) {
	t.Helper()
	ctx := context.Background()

	migrationsDir, err := filepath.Abs("../../migrations")
	if err != nil {
		t.Fatalf("failed to resolve migrations dir: %v", err)
	}
	scripts := store.AllMigrationFiles(migrationsDir)

	// pgvector/pgvector:pg16 — see store_integration_test.go's setupTestDB
	// for why (migration 0007 needs the vector extension present).
	pgContainer, err := postgres.Run(ctx, "pgvector/pgvector:pg16",
		postgres.WithDatabase("agentos_test"),
		postgres.WithUsername("agentos"),
		postgres.WithPassword("agentos_test"),
		postgres.WithOrderedInitScripts(scripts...),
		testcontainers.WithWaitStrategy(
			wait.ForLog("database system is ready to accept connections").WithOccurrence(2),
		),
	)
	if err != nil {
		t.Fatalf("failed to start postgres container: %v", err)
	}
	t.Cleanup(func() {
		if err := pgContainer.Terminate(context.Background()); err != nil {
			t.Logf("failed to terminate postgres container: %v", err)
		}
	})

	connStr, err := pgContainer.ConnectionString(ctx, "sslmode=disable")
	if err != nil {
		t.Fatalf("failed to get connection string: %v", err)
	}

	pool, err := pgxpool.New(ctx, connStr)
	if err != nil {
		t.Fatalf("failed to create pool: %v", err)
	}
	t.Cleanup(pool.Close)

	redisContainer, err := tcredis.Run(ctx, "redis:7-alpine")
	if err != nil {
		t.Fatalf("failed to start redis container: %v", err)
	}
	t.Cleanup(func() {
		if err := redisContainer.Terminate(context.Background()); err != nil {
			t.Logf("failed to terminate redis container: %v", err)
		}
	})

	redisAddr, err := redisContainer.PortEndpoint(ctx, "6379/tcp", "")
	if err != nil {
		t.Fatalf("failed to get redis endpoint: %v", err)
	}
	redisClient := redis.NewClient(&redis.Options{Addr: redisAddr})
	t.Cleanup(func() { _ = redisClient.Close() })

	queries := store.New(pool)
	publisher := bus.NewPublisher(redisClient)
	workingMemory := bus.NewWorkingMemory(redisClient)
	appHandler := NewApplicationsHandler(queries, pool, publisher, workingMemory)
	profileHandler := NewProfileHandler(queries)

	rulesPath, err := filepath.Abs("../../config/policy_rules.yaml")
	if err != nil {
		t.Fatalf("failed to resolve policy rules path: %v", err)
	}
	rules, err := policy.LoadRules(rulesPath)
	if err != nil {
		t.Fatalf("failed to load policy rules: %v", err)
	}
	agentCallbackHandler := NewAgentCallbackHandler(queries, pool, policy.NewEngine(rules))

	router := chi.NewRouter()
	router.Route("/api/v1", func(r chi.Router) {
		r.Use(middleware.UserContext)
		r.Route("/applications", func(r chi.Router) {
			r.Post("/", appHandler.Create)
			r.Get("/", appHandler.List)
			r.Get("/{id}", appHandler.Get)
			r.Post("/{id}/confirm-submit", appHandler.ConfirmSubmit)
		})
		r.Route("/profile", func(r chi.Router) {
			r.Get("/", profileHandler.Get)
			r.Put("/", profileHandler.Put)
		})
	})
	router.Route("/internal", func(r chi.Router) {
		r.Use(middleware.InternalAuth(testInternalSharedSecret))
		r.Post("/agent/callback", agentCallbackHandler.Callback)
	})

	return router, queries, redisClient, pool
}

func TestApplicationsAPI_CreateListDetail(t *testing.T) {
	ctx := context.Background()
	router, queries, _, _ := setupTestRouter(t)

	user, err := queries.CreateUser(ctx, "handlers-roundtrip@example.com")
	if err != nil {
		t.Fatalf("create user failed: %v", err)
	}
	userIDStr := uuidString(user.ID)

	// --- Create ---
	createBody := `{"jd_url": "https://boards.greenhouse.io/example/jobs/123"}`
	createReq := httptest.NewRequestWithContext(ctx, http.MethodPost, "/api/v1/applications", bytes.NewBufferString(createBody))
	createReq.Header.Set("X-Demo-User-ID", userIDStr)
	createRec := httptest.NewRecorder()

	router.ServeHTTP(createRec, createReq)

	if createRec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", createRec.Code, createRec.Body.String())
	}
	var created applicationCreatedResponse
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("failed to decode create response: %v", err)
	}
	if created.Status != "pending" || created.Source != "manual" {
		t.Fatalf("unexpected create response: %+v", created)
	}

	// --- List ---
	listReq := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/applications", nil)
	listReq.Header.Set("X-Demo-User-ID", userIDStr)
	listRec := httptest.NewRecorder()

	router.ServeHTTP(listRec, listReq)

	if listRec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", listRec.Code, listRec.Body.String())
	}
	var listBody struct {
		Data       []applicationSummaryResponse `json:"data"`
		NextCursor *string                      `json:"next_cursor"`
	}
	if err := json.Unmarshal(listRec.Body.Bytes(), &listBody); err != nil {
		t.Fatalf("failed to decode list response: %v", err)
	}
	if len(listBody.Data) != 1 || listBody.Data[0].ID != created.ID {
		t.Fatalf("expected exactly 1 listed application matching %s, got %+v", created.ID, listBody.Data)
	}
	if listBody.NextCursor != nil {
		t.Fatalf("expected next_cursor to be null, got %v", *listBody.NextCursor)
	}

	// --- Detail ---
	detailReq := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/applications/"+created.ID, nil)
	detailReq.Header.Set("X-Demo-User-ID", userIDStr)
	detailRec := httptest.NewRecorder()

	router.ServeHTTP(detailRec, detailReq)

	if detailRec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", detailRec.Code, detailRec.Body.String())
	}
	var detail applicationDetailResponse
	if err := json.Unmarshal(detailRec.Body.Bytes(), &detail); err != nil {
		t.Fatalf("failed to decode detail response: %v", err)
	}
	if detail.ID != created.ID {
		t.Fatalf("detail id mismatch: got %s, want %s", detail.ID, created.ID)
	}
	if detail.JDUrl == nil || *detail.JDUrl != "https://boards.greenhouse.io/example/jobs/123" {
		t.Fatalf("unexpected jd_url in detail: %+v", detail.JDUrl)
	}
	if detail.ScoreBreakdown != nil {
		t.Fatalf("expected nil score_breakdown (Scoring Agent not built yet), got %+v", detail.ScoreBreakdown)
	}
	if len(detail.RetrievedEvidence) != 0 || len(detail.GeneratedDocuments) != 0 || len(detail.PolicyDecisions) != 0 {
		t.Fatalf("expected empty (not null) arrays for not-yet-populated fields, got %+v", detail)
	}
}

func TestApplicationsAPI_GetNotFoundForOtherUser(t *testing.T) {
	ctx := context.Background()
	router, queries, _, _ := setupTestRouter(t)

	owner, err := queries.CreateUser(ctx, "owner@example.com")
	if err != nil {
		t.Fatalf("create owner failed: %v", err)
	}
	intruder, err := queries.CreateUser(ctx, "intruder@example.com")
	if err != nil {
		t.Fatalf("create intruder failed: %v", err)
	}

	createReq := httptest.NewRequestWithContext(ctx, http.MethodPost, "/api/v1/applications",
		bytes.NewBufferString(`{"jd_text": "some JD text"}`))
	createReq.Header.Set("X-Demo-User-ID", uuidString(owner.ID))
	createRec := httptest.NewRecorder()
	router.ServeHTTP(createRec, createReq)

	var created applicationCreatedResponse
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)

	// The intruder requests the owner's application by its real id.
	detailReq := httptest.NewRequestWithContext(ctx, http.MethodGet, "/api/v1/applications/"+created.ID, nil)
	detailReq.Header.Set("X-Demo-User-ID", uuidString(intruder.ID))
	detailRec := httptest.NewRecorder()
	router.ServeHTTP(detailRec, detailReq)

	if detailRec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for another user's application, got %d: %s", detailRec.Code, detailRec.Body.String())
	}
}
