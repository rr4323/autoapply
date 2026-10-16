package policy

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

// AgentName identifies this consumer's writes in application_events and
// policy_decisions — the audit trail should say which component decided,
// not just what it decided.
const AgentName = "policy-engine"

const workingMemoryTTL = 24 * time.Hour

// ScoredConsumer wires Engine (Step 31's pure Evaluate) to the bus: it
// consumes application.scored, evaluates the post-scoring branch of §7.2,
// writes the audit row, and publishes policy.decision. Step 32's scope is
// deliberately just the post-scoring decision point — the pre-submit
// decision point (§7.2's other branch) is wired later by the Verifier
// Agent (Phase G), which is the actual component with bot-check and
// velocity-cap context to evaluate against.
type ScoredConsumer struct {
	Queries       *store.Queries
	Pool          *pgxpool.Pool
	Engine        *Engine
	Publisher     *bus.Publisher
	WorkingMemory *bus.WorkingMemory
}

// IsDuplicate implements bus.IsDuplicate.
func (s *ScoredConsumer) IsDuplicate(ctx context.Context, env bus.Envelope) (bool, error) {
	appID, err := parseApplicationID(env.JobID)
	if err != nil {
		return false, err
	}
	return s.Queries.HasApplicationEvent(ctx, store.HasApplicationEventParams{
		ApplicationID: appID,
		EventType:     bus.TopicPolicyDecision,
	})
}

// Handle implements bus.Handler.
func (s *ScoredConsumer) Handle(ctx context.Context, entryID string, env bus.Envelope) error {
	appID, err := parseApplicationID(env.JobID)
	if err != nil {
		return fmt.Errorf("policyengine: invalid job_id %q: %w", env.JobID, err)
	}

	app, err := s.Queries.GetApplication(ctx, appID)
	if err != nil {
		return fmt.Errorf("policyengine: failed to load application %s: %w", env.JobID, err)
	}

	score := 0.0
	if app.JdFitScore != nil {
		score = *app.JdFitScore
	}

	decision := s.Engine.Evaluate(Context{
		DecisionPoint: DecisionPointPostScoring,
		Score:         score,
		// No spend-tracking system exists yet (§7.5's Cost Circuit
		// Breaker is out of this step's scope) — 0 is a safe placeholder
		// since MaxDailyGenerateSpendUSD is nil by default anyway, making
		// this comparison a no-op until §7.5 actually wires real spend data.
		TodayGenerateSpendUSD: 0,
	})

	if err := s.persist(ctx, appID, decision); err != nil {
		return err
	}

	// Working-memory write + publish happen after the transaction commits,
	// same tradeoff as ApplicationsHandler.Create: Postgres and Redis
	// can't be written atomically together without an outbox this project
	// doesn't build. A failure here is logged loudly, not retried by
	// un-acking — un-acking would just redeliver into IsDuplicate, which
	// would now see the committed application_events row and skip
	// straight past this step forever.
	wmKey := bus.WorkingMemoryKey(env.JobID, "policy_decision")
	payload := map[string]any{
		"decision_point": DecisionPointPostScoring,
		"action":         decision.Action,
		"reasons":        decision.Reasons,
		"rules_version":  s.Engine.Rules.Version,
	}
	if err := s.WorkingMemory.Set(ctx, wmKey, payload, workingMemoryTTL); err != nil {
		slog.Error("policyengine: failed to write working memory", "job_id", env.JobID, "error", err)
	}

	outEnv := bus.Envelope{
		JobID:      env.JobID,
		TraceID:    env.TraceID,
		EventType:  bus.TopicPolicyDecision,
		ProducedBy: AgentName,
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		PayloadRef: wmKey,
	}
	if _, err := s.Publisher.Publish(ctx, bus.TopicPolicyDecision, outEnv); err != nil {
		slog.Error("policyengine: failed to publish policy.decision", "job_id", env.JobID, "error", err)
	}

	return nil
}

// persist writes the policy_decisions audit row and the
// application_events idempotency row in one transaction — a crash between
// the two must not leave a decision recorded without also being
// redelivery-safe, or vice versa.
func (s *ScoredConsumer) persist(ctx context.Context, appID pgtype.UUID, decision Decision) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("policyengine: failed to start transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	qtx := s.Queries.WithTx(tx)

	if err := RecordDecision(
		ctx, qtx, appID, DecisionPointPostScoring, decision,
		s.Engine.Rules.Version, AgentName, bus.TopicPolicyDecision,
	); err != nil {
		return fmt.Errorf("policyengine: %w", err)
	}

	// A "stop" is the one post-scoring outcome with nothing further ever
	// touching applications.status downstream — the pre-submit consumer
	// (agent_callback.go) only runs for applications that reach it, which
	// a stopped one never does. Recorded here so GET /applications/:id
	// reflects it, not left silently stuck at "scored" forever.
	if decision.Action == ActionStop {
		if _, err := qtx.MarkApplicationBelowThreshold(ctx, appID); err != nil {
			return fmt.Errorf("policyengine: failed to mark application below_threshold: %w", err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("policyengine: failed to commit transaction: %w", err)
	}
	return nil
}

func parseApplicationID(jobID string) (pgtype.UUID, error) {
	var id pgtype.UUID
	if err := id.Scan(jobID); err != nil {
		return pgtype.UUID{}, fmt.Errorf("policyengine: %q is not a valid UUID: %w", jobID, err)
	}
	return id, nil
}
