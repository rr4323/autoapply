package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
	"github.com/rr4323/autoapply/backend/api/internal/config"
	"github.com/rr4323/autoapply/backend/api/internal/dbmigrate"
	"github.com/rr4323/autoapply/backend/api/internal/handlers"
	"github.com/rr4323/autoapply/backend/api/internal/health"
	authmw "github.com/rr4323/autoapply/backend/api/internal/middleware"
	"github.com/rr4323/autoapply/backend/api/internal/policy"
	"github.com/rr4323/autoapply/backend/api/internal/store"
	"github.com/rr4323/autoapply/backend/api/internal/terminal"
)

func main() {
	cfg := config.Load()

	// Run before anything else touches the schema — a cold `make up`
	// (Step 45's M6 exit) brings up a fresh Postgres volume with no
	// tables at all otherwise. Idempotent: a no-op on every restart of an
	// already-migrated deployment.
	if err := dbmigrate.Run(cfg.DatabaseURL, cfg.MigrationsPath); err != nil {
		slog.Error("failed to run database migrations", "error", err)
		os.Exit(1)
	}

	dbPool, err := pgxpool.New(context.Background(), cfg.DatabaseURL)
	if err != nil {
		slog.Error("failed to create postgres pool", "error", err)
		os.Exit(1)
	}
	defer dbPool.Close()

	redisClient := redis.NewClient(&redis.Options{Addr: cfg.RedisAddr})
	defer func() {
		if err := redisClient.Close(); err != nil {
			slog.Error("failed to close redis client", "error", err)
		}
	}()

	checker := health.NewChecker(dbPool, redisPinger{redisClient})
	queries := store.New(dbPool)

	publisher := bus.NewPublisher(redisClient)
	workingMemory := bus.NewWorkingMemory(redisClient)
	applicationsHandler := handlers.NewApplicationsHandler(queries, dbPool, publisher, workingMemory)
	profileHandler := handlers.NewProfileHandler(queries)
	// P1 (SaaS pivot): real JWT auth replaces the Phase 1 stub user
	// (internal/middleware.DefaultStubUserID) — see internal/auth and
	// internal/middleware/jwtauth.go.
	authHandler := handlers.NewAuthHandler(queries, []byte(cfg.JWTSigningKey))

	rules, err := policy.LoadRules(cfg.PolicyRulesPath)
	if err != nil {
		slog.Error("failed to load policy rules", "path", cfg.PolicyRulesPath, "error", err)
		os.Exit(1)
	}
	policyEngine := policy.NewEngine(rules)
	agentCallbackHandler := handlers.NewAgentCallbackHandler(queries, dbPool, policyEngine)

	router := chi.NewRouter()
	router.Get("/healthz", checker.Healthz)
	router.Get("/readyz", checker.Readyz)

	router.Route("/api/v1", func(r chi.Router) {
		r.Route("/auth", func(r chi.Router) {
			r.Post("/signup", authHandler.Signup)
			r.Post("/login", authHandler.Login)
		})
		r.Group(func(r chi.Router) {
			r.Use(authmw.JWTAuth([]byte(cfg.JWTSigningKey)))
			r.Route("/applications", func(r chi.Router) {
				r.Post("/", applicationsHandler.Create)
				r.Get("/", applicationsHandler.List)
				r.Get("/{id}", applicationsHandler.Get)
				r.Post("/{id}/confirm-submit", applicationsHandler.ConfirmSubmit)
			})
			r.Route("/profile", func(r chi.Router) {
				r.Get("/", profileHandler.Get)
				r.Put("/", profileHandler.Put)
			})
		})
	})

	router.Route("/internal", func(r chi.Router) {
		r.Use(authmw.InternalAuth(cfg.InternalSharedSecret))
		r.Get("/ping", internalPingHandler)
		r.Post("/agent/callback", agentCallbackHandler.Callback)
	})

	srv := &http.Server{
		Addr:    ":" + cfg.Port,
		Handler: router,
	}

	stopCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Bus consumers — the Go-side halves of the post-scoring policy
	// decision (Step 32) and the application.terminal outcome the
	// Verifier Agent publishes (Step 44). One consumer instance each is
	// enough at Phase 1 scale; ConsumerName would need to vary per
	// replica if this process ever runs horizontally scaled.
	scoredHandler := &policy.ScoredConsumer{
		Queries: queries, Pool: dbPool, Engine: policyEngine,
		Publisher: publisher, WorkingMemory: workingMemory,
	}
	scoredConsumer := &bus.Consumer{
		Redis: redisClient, Topic: bus.TopicApplicationScored,
		Group: "policy-engine", ConsumerName: "api-1",
		BlockDuration: 2 * time.Second, ReclaimIdle: 30 * time.Second,
		Handle: scoredHandler.Handle, IsDuplicate: scoredHandler.IsDuplicate,
	}
	go func() {
		if err := scoredConsumer.Run(stopCtx); err != nil {
			slog.Error("scored consumer stopped with error", "error", err)
		}
	}()

	terminalHandler := &terminal.Consumer{Queries: queries, WorkingMemory: workingMemory}
	terminalConsumer := &bus.Consumer{
		Redis: redisClient, Topic: bus.TopicApplicationTerminal,
		Group: "terminal-consumer", ConsumerName: "api-1",
		BlockDuration: 2 * time.Second, ReclaimIdle: 30 * time.Second,
		Handle: terminalHandler.Handle, IsDuplicate: terminalHandler.IsDuplicate,
	}
	go func() {
		if err := terminalConsumer.Run(stopCtx); err != nil {
			slog.Error("terminal consumer stopped with error", "error", err)
		}
	}()

	go func() {
		slog.Info("agentos api starting", "port", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	<-stopCtx.Done()

	slog.Info("shutdown signal received")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
		os.Exit(1)
	}
	slog.Info("shutdown complete")
}

// redisPinger adapts *redis.Client to health.Pinger. go-redis's Ping
// returns *redis.StatusCmd, not a bare error, so — unlike *pgxpool.Pool,
// which already matches health.Pinger's shape exactly — a thin wrapper
// is needed here to satisfy the interface.
type redisPinger struct {
	client *redis.Client
}

func (p redisPinger) Ping(ctx context.Context) error {
	return p.client.Ping(ctx).Err()
}

func internalPingHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}
