//go:build integration

// The sqlc-generated repository layer's integration test — a real
// Postgres container, real migrations applied, create -> read -> list
// round trip (docs/BACKEND_BUILD_STEPS.md Step 13).
package store

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"
)

func setupTestDB(t *testing.T) *Queries {
	t.Helper()
	ctx := context.Background()

	migrationsDir, err := filepath.Abs("../../migrations")
	if err != nil {
		t.Fatalf("failed to resolve migrations dir: %v", err)
	}
	scripts := AllMigrationFiles(migrationsDir)

	// pgvector/pgvector:pg16, not plain postgres:16-alpine — migration 0007
	// runs CREATE EXTENSION vector, same image docker-compose.yml already
	// uses for local dev.
	container, err := postgres.Run(ctx, "pgvector/pgvector:pg16",
		postgres.WithDatabase("agentos_test"),
		postgres.WithUsername("agentos"),
		postgres.WithPassword("agentos_test"),
		postgres.WithOrderedInitScripts(scripts...),
		// Postgres restarts once after running init scripts on first boot —
		// the module's default readiness check can fire on the pre-restart
		// log line, racing a connection attempt against the restart itself.
		// Require the log line's SECOND occurrence (post-restart) instead.
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

	return New(pool)
}

func TestApplicationsProfiles_CreateReadList(t *testing.T) {
	ctx := context.Background()
	q := setupTestDB(t)

	user, err := q.CreateUser(ctx, "roundtrip@example.com")
	if err != nil {
		t.Fatalf("create user failed: %v", err)
	}

	// Profile: create -> read
	baseResumeDocID := "storage_ref:resumes/roundtrip.pdf"
	profile, err := q.CreateProfile(ctx, CreateProfileParams{
		UserID:          user.ID,
		BaseResumeDocID: &baseResumeDocID,
		Skills:          []string{"Go", "Python"},
		ExperienceJson:  []byte(`{"years": 5}`),
	})
	if err != nil {
		t.Fatalf("create profile failed: %v", err)
	}

	fetchedProfile, err := q.GetProfile(ctx, profile.ID)
	if err != nil {
		t.Fatalf("get profile failed: %v", err)
	}
	if fetchedProfile.UserID != user.ID {
		t.Fatalf("fetched profile user_id mismatch: got %v, want %v", fetchedProfile.UserID, user.ID)
	}
	if len(fetchedProfile.Skills) != 2 || fetchedProfile.Skills[0] != "Go" {
		t.Fatalf("fetched profile skills mismatch: got %v", fetchedProfile.Skills)
	}

	// Application: create -> read -> list
	jdURL := "https://boards.greenhouse.io/example/jobs/123"
	app, err := q.CreateApplication(ctx, CreateApplicationParams{
		UserID: user.ID,
		JdUrl:  &jdURL,
		Source: ApplicationSourceManual,
	})
	if err != nil {
		t.Fatalf("create application failed: %v", err)
	}
	if app.Status != ApplicationStatusPending {
		t.Fatalf("expected default status 'pending', got %q", app.Status)
	}

	fetchedApp, err := q.GetApplication(ctx, app.ID)
	if err != nil {
		t.Fatalf("get application failed: %v", err)
	}
	if fetchedApp.ID != app.ID {
		t.Fatalf("fetched application id mismatch")
	}

	listed, err := q.ListApplicationsByUser(ctx, user.ID)
	if err != nil {
		t.Fatalf("list applications failed: %v", err)
	}
	if len(listed) != 1 || listed[0].ID != app.ID {
		t.Fatalf("expected exactly 1 listed application matching %v, got %+v", app.ID, listed)
	}

	// application_events: append-only writer
	event, err := q.AppendApplicationEvent(ctx, AppendApplicationEventParams{
		ApplicationID:   app.ID,
		EventType:       "jd.discovered",
		ProducedByAgent: "ingestion-cron",
		PayloadJson:     []byte(`{}`),
	})
	if err != nil {
		t.Fatalf("append event failed: %v", err)
	}

	events, err := q.ListApplicationEvents(ctx, app.ID)
	if err != nil {
		t.Fatalf("list events failed: %v", err)
	}
	if len(events) != 1 || events[0].ID != event.ID {
		t.Fatalf("expected exactly 1 event matching %v, got %+v", event.ID, events)
	}
}
