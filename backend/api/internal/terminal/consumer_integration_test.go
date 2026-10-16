//go:build integration

// application.terminal consumed by the Go API -> applications.status
// updated (docs/BACKEND_BUILD_STEPS.md Step 44). Real Postgres + real
// Redis (miniredis) — the same rigor as every other agent's integration
// test in this project.
package terminal

import (
	"context"
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

func setupTerminalTestDB(t *testing.T) (*store.Queries, *pgxpool.Pool) {
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

func newTerminalTestRedisClient(t *testing.T) *redis.Client {
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

func seedApplication(t *testing.T, ctx context.Context, queries *store.Queries) string {
	t.Helper()
	user, err := queries.CreateUser(ctx, "terminal-test@example.com")
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
	v, _ := app.ID.Value()
	s, _ := v.(string)
	return s
}

func buildEnvelope(jobID, payloadRef string) bus.Envelope {
	return bus.Envelope{
		JobID: jobID, TraceID: "trace-1", EventType: bus.TopicApplicationTerminal,
		ProducedBy: "verifier-agent", Timestamp: time.Now().UTC().Format(time.RFC3339),
		PayloadRef: payloadRef,
	}
}

func TestConsumer_Submitted_UpdatesStatusAndSubmittedAt(t *testing.T) {
	ctx := context.Background()
	queries, pool := setupTerminalTestDB(t)
	redisClient := newTerminalTestRedisClient(t)
	workingMemory := bus.NewWorkingMemory(redisClient)

	jobID := seedApplication(t, ctx, queries)
	wmKey := bus.WorkingMemoryKey(jobID, "application_terminal")
	if err := workingMemory.Set(ctx, wmKey, map[string]any{
		"status": "submitted", "reasons": []string{"clean pass"}, "bot_check_detected": false,
	}, time.Hour); err != nil {
		t.Fatalf("failed to seed working memory: %v", err)
	}

	consumer := &Consumer{Queries: queries, WorkingMemory: workingMemory}
	if err := consumer.Handle(ctx, "entry-1", buildEnvelope(jobID, wmKey)); err != nil {
		t.Fatalf("Handle failed: %v", err)
	}

	appID := mustParseUUID(t, jobID)
	app, err := queries.GetApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to reload application: %v", err)
	}
	if app.Status != store.ApplicationStatusSubmitted {
		t.Errorf("status = %v, want submitted", app.Status)
	}
	if !app.SubmittedAt.Valid {
		t.Error("submitted_at was not set")
	}

	events, err := queries.ListApplicationEvents(ctx, appID)
	if err != nil {
		t.Fatalf("failed to list application events: %v", err)
	}
	if len(events) != 1 || events[0].EventType != bus.TopicApplicationTerminal {
		t.Fatalf("application_events = %+v, want exactly one %q event", events, bus.TopicApplicationTerminal)
	}

	_ = pool // exercised indirectly via queries
}

func TestConsumer_ReadyForReview_UpdatesStatusWithoutSubmittedAt(t *testing.T) {
	ctx := context.Background()
	queries, _ := setupTerminalTestDB(t)
	redisClient := newTerminalTestRedisClient(t)
	workingMemory := bus.NewWorkingMemory(redisClient)

	jobID := seedApplication(t, ctx, queries)
	wmKey := bus.WorkingMemoryKey(jobID, "application_terminal")
	if err := workingMemory.Set(ctx, wmKey, map[string]any{
		"status": "ready_for_review", "reasons": []string{"bot-check detected"}, "bot_check_detected": true,
	}, time.Hour); err != nil {
		t.Fatalf("failed to seed working memory: %v", err)
	}

	consumer := &Consumer{Queries: queries, WorkingMemory: workingMemory}
	if err := consumer.Handle(ctx, "entry-1", buildEnvelope(jobID, wmKey)); err != nil {
		t.Fatalf("Handle failed: %v", err)
	}

	appID := mustParseUUID(t, jobID)
	app, err := queries.GetApplication(ctx, appID)
	if err != nil {
		t.Fatalf("failed to reload application: %v", err)
	}
	if app.Status != store.ApplicationStatusReadyForReview {
		t.Errorf("status = %v, want ready_for_review", app.Status)
	}
	if app.SubmittedAt.Valid {
		t.Error("submitted_at was set for a ready_for_review outcome")
	}
}

func TestConsumer_IsDuplicate_TrueAfterHandle(t *testing.T) {
	ctx := context.Background()
	queries, _ := setupTerminalTestDB(t)
	redisClient := newTerminalTestRedisClient(t)
	workingMemory := bus.NewWorkingMemory(redisClient)

	jobID := seedApplication(t, ctx, queries)
	wmKey := bus.WorkingMemoryKey(jobID, "application_terminal")
	if err := workingMemory.Set(ctx, wmKey, map[string]any{
		"status": "submitted", "reasons": []string{}, "bot_check_detected": false,
	}, time.Hour); err != nil {
		t.Fatalf("failed to seed working memory: %v", err)
	}

	consumer := &Consumer{Queries: queries, WorkingMemory: workingMemory}
	env := buildEnvelope(jobID, wmKey)

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
}

func mustParseUUID(t *testing.T, s string) pgtype.UUID {
	t.Helper()
	var id pgtype.UUID
	if err := id.Scan(s); err != nil {
		t.Fatalf("failed to parse UUID %q: %v", s, err)
	}
	return id
}
