// Package dbmigrate runs pending schema migrations at API startup
// (docs/BACKEND_BUILD_STEPS.md Step 45). Before this, `make migrate-up`
// was a separate manual step using the migrate CLI — fine for local dev
// where a human runs it once, but a cold `make up` (Step 45's own M6
// exit criterion) brings up a fresh Postgres volume with no schema at
// all unless something applies migrations automatically. Using the
// golang-migrate library directly (not shelling out to the CLI) keeps
// the Docker image self-contained — no separate migrate binary to bake
// into it or coordinate as its own compose service/init container.
package dbmigrate

import (
	"errors"
	"fmt"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres" // driver registration side effect
	_ "github.com/golang-migrate/migrate/v4/source/file"       // driver registration side effect
)

// Run applies every pending .up.sql migration under migrationsDir.
// Idempotent — running it again against an already-current database is
// a safe no-op (migrate.ErrNoChange), which is exactly what happens on
// every subsequent restart of an already-migrated deployment.
func Run(databaseURL, migrationsDir string) error {
	m, err := migrate.New("file://"+migrationsDir, databaseURL)
	if err != nil {
		return fmt.Errorf("dbmigrate: failed to initialize: %w", err)
	}
	defer func() { _, _ = m.Close() }()

	if err := m.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return fmt.Errorf("dbmigrate: failed to apply migrations: %w", err)
	}
	return nil
}
