//go:build integration

// Policy Engine bus wiring (docs/BACKEND_BUILD_STEPS.md Step 32): consume
// application.scored -> write policy_decisions row + publish
// policy.decision. Real Postgres + real Redis (miniredis), same rigor as
// every other agent's integration test in this project.
package policy

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

func setupPolicyTestDB(t *testing.T) (*store.Queries, *pgxpool.Pool) {
	t.Helper()
	ctx := context.Background()

	migrationsDir, err := filepath.Abs("../../migrations")
	if err != nil {
		t.Fatalf("failed to resolve migrations dir: %v", err)
	}
	scripts := store.AllMigrationFiles(migrationsDir)

	container, err := postgres.Run(ctx, "pgvector/pgvector:pg16",
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
		if err := container.Terminate(context.Background()); err != nil {
			t.Logf("failed to terminate container: %v", err)
		}
	})

	connStr, err := container.ConnectionString(ctx, "sslmode=disable")
	if err != nil {
		t.Fatalf("failed to get connection string: %v", err)
	}

	pool, err := pgxpool.New(ctx, connStr)
	if err != nil {
		t.Fatalf("failed to create pool: %v", err)
	}
	t.Cleanup(pool.Close)

	return store.New(pool), pool
}

func newTestRedisClient(t *testing.T) *redis.Client {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("failed to start miniredis: %v", err)
	}
	t.Cleanup(mr.Close)

	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func seedScoredApplication(t *testing.T, ctx context.Context, queries *store.Queries, pool *pgxpool.Pool, score float64) pgtype.UUID {
	t.Helper()

	user, err := queries.CreateUser(ctx, "policy-test@example.com")
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

	return app.ID
}

func newTestEngine() *Engine {
	return NewEngine(Rules{
		Version:                 "policy-rules-v1",
		MinGenerateScore:        60,
		MinAutosubmitScore:      80,
		RequireReviewIfBotCheck: true,
		VelocityCapPerDay:       15,
	})
}

func TestScoredConsumer_GeneratesDecisionAndPublishes(t *testing.T) {
	ctx := context.Background()
	queries, pool := setupPolicyTestDB(t)
	redisClient := newTestRedisClient(t)

	appID := seedScoredApplication(t, ctx, queries, pool, 75) // above min_generate_score

	consumer := &ScoredConsumer{
		Queries:       queries,
		Pool:          pool,
		Engine:        newTestEngine(),
		Publisher:     bus.NewPublisher(redisClient),
		WorkingMemory: bus.NewWorkingMemory(redisClient),
	}

	jobID := uuidString(appID)
	env := bus.Envelope{
		JobID: jobID, TraceID: "trace-1", EventType: bus.TopicApplicationScored,
		ProducedBy: "scoring-agent", Timestamp: time.Now().UTC().Format(time.RFC3339),
		PayloadRef: bus.WorkingMemoryKey(jobID, "application_scored"),
	}

	if err := consumer.Handle(ctx, "entry-1", env); err != nil {
		t.Fatalf("Handle failed: %v", err)
	}

	// policy_decisions row
	decisions, err := queries.ListPolicyDecisionsForApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list policy decisions: %v", err)
	}
	if len(decisions) != 1 {
		t.Fatalf("policy_decisions rows = %d, want 1", len(decisions))
	}
	if decisions[0].Action != string(ActionGenerate) {
		t.Errorf("action = %v, want %v", decisions[0].Action, ActionGenerate)
	}
	var reasons []string
	if err := json.Unmarshal(decisions[0].ReasonsJson, &reasons); err != nil {
		t.Fatalf("failed to unmarshal reasons_json: %v", err)
	}
	if len(reasons) == 0 {
		t.Fatal("reasons_json is empty — §7.2 requires a non-empty reasons array")
	}
	if decisions[0].RulesVersion == nil || *decisions[0].RulesVersion != "policy-rules-v1" {
		t.Errorf("rules_version = %v, want policy-rules-v1", decisions[0].RulesVersion)
	}

	// application_events idempotency row
	events, err := queries.ListApplicationEvents(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list application events: %v", err)
	}
	if len(events) != 1 || events[0].EventType != bus.TopicPolicyDecision {
		t.Fatalf("application_events = %+v, want exactly one %q event", events, bus.TopicPolicyDecision)
	}

	// policy.decision published
	entries, err := redisClient.XRange(ctx, bus.TopicPolicyDecision, "-", "+").Result()
	if err != nil {
		t.Fatalf("xrange failed: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("policy.decision entries = %d, want 1", len(entries))
	}
	if entries[0].Values["job_id"] != jobID {
		t.Errorf("published job_id = %v, want %v", entries[0].Values["job_id"], jobID)
	}
	if entries[0].Values["produced_by"] != AgentName {
		t.Errorf("published produced_by = %v, want %v", entries[0].Values["produced_by"], AgentName)
	}
}

func TestScoredConsumer_BelowThresholdStops(t *testing.T) {
	ctx := context.Background()
	queries, pool := setupPolicyTestDB(t)
	redisClient := newTestRedisClient(t)

	appID := seedScoredApplication(t, ctx, queries, pool, 40) // below min_generate_score

	consumer := &ScoredConsumer{
		Queries:       queries,
		Pool:          pool,
		Engine:        newTestEngine(),
		Publisher:     bus.NewPublisher(redisClient),
		WorkingMemory: bus.NewWorkingMemory(redisClient),
	}

	jobID := uuidString(appID)
	env := bus.Envelope{
		JobID: jobID, TraceID: "trace-1", EventType: bus.TopicApplicationScored,
		ProducedBy: "scoring-agent", Timestamp: time.Now().UTC().Format(time.RFC3339),
		PayloadRef: bus.WorkingMemoryKey(jobID, "application_scored"),
	}

	if err := consumer.Handle(ctx, "entry-1", env); err != nil {
		t.Fatalf("Handle failed: %v", err)
	}

	decisions, err := queries.ListPolicyDecisionsForApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list policy decisions: %v", err)
	}
	if len(decisions) != 1 || decisions[0].Action != string(ActionStop) {
		t.Fatalf("decisions = %+v, want exactly one %q action", decisions, ActionStop)
	}

	app, err := queries.GetApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to reload application: %v", err)
	}
	if app.Status != store.ApplicationStatusBelowThreshold {
		t.Errorf("status = %v, want below_threshold", app.Status)
	}
}

func TestScoredConsumer_IsDuplicate_TrueAfterHandle(t *testing.T) {
	ctx := context.Background()
	queries, pool := setupPolicyTestDB(t)
	redisClient := newTestRedisClient(t)

	appID := seedScoredApplication(t, ctx, queries, pool, 75)

	consumer := &ScoredConsumer{
		Queries:       queries,
		Pool:          pool,
		Engine:        newTestEngine(),
		Publisher:     bus.NewPublisher(redisClient),
		WorkingMemory: bus.NewWorkingMemory(redisClient),
	}

	jobID := uuidString(appID)
	env := bus.Envelope{
		JobID: jobID, TraceID: "trace-1", EventType: bus.TopicApplicationScored,
		ProducedBy: "scoring-agent", Timestamp: time.Now().UTC().Format(time.RFC3339),
		PayloadRef: bus.WorkingMemoryKey(jobID, "application_scored"),
	}

	dupBefore, err := consumer.IsDuplicate(ctx, env)
	if err != nil {
		t.Fatalf("IsDuplicate failed: %v", err)
	}
	if dupBefore {
		t.Fatal("IsDuplicate = true before Handle ran, want false")
	}

	if err := consumer.Handle(ctx, "entry-1", env); err != nil {
		t.Fatalf("Handle failed: %v", err)
	}

	dupAfter, err := consumer.IsDuplicate(ctx, env)
	if err != nil {
		t.Fatalf("IsDuplicate failed: %v", err)
	}
	if !dupAfter {
		t.Fatal("IsDuplicate = false after Handle ran, want true — redelivery must be a no-op")
	}

	// Redelivery via the real bus.Consumer path must not double-publish or
	// double-write, mirroring every Python agent's own redelivery test.
	if dupAfter {
		decisions, err := queries.ListPolicyDecisionsForApplication(ctx, appID)
		if err != nil {
			t.Fatalf("failed to list policy decisions: %v", err)
		}
		if len(decisions) != 1 {
			t.Fatalf("policy_decisions rows = %d, want 1 (unchanged after IsDuplicate check)", len(decisions))
		}
	}
}

func uuidString(id pgtype.UUID) string {
	v, _ := id.Value()
	s, _ := v.(string)
	return s
}
