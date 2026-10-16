// Package terminal wires application.terminal (published by the Python
// Verifier Agent, docs/BACKEND_BUILD_STEPS.md Step 43) to the Go control
// plane: applications.status is the durable record a human reviewer or
// the dashboard reads, so a terminal outcome reached inside a Python
// agent's browser session has to land there, not just in that agent's
// own process memory.
package terminal

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jackc/pgx/v5/pgtype"

	"github.com/rr4323/autoapply/backend/api/internal/bus"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

// AgentName identifies this consumer's writes in application_events.
const AgentName = "terminal-consumer"

// terminalPayload mirrors the shape
// agentos_agents.filler.verify.publish_terminal_event writes to working
// memory — status is either "submitted" or "ready_for_review" (Step 43's
// two possible outcomes; a needs_input pause is a later phase, not
// produced by the Verifier Agent).
type terminalPayload struct {
	Status           string   `json:"status"`
	Reasons          []string `json:"reasons"`
	BotCheckDetected bool     `json:"bot_check_detected"`
}

// Consumer applies a terminal outcome to applications.status.
type Consumer struct {
	Queries       *store.Queries
	WorkingMemory *bus.WorkingMemory
}

// IsDuplicate implements bus.IsDuplicate.
func (c *Consumer) IsDuplicate(ctx context.Context, env bus.Envelope) (bool, error) {
	appID, err := parseApplicationID(env.JobID)
	if err != nil {
		return false, err
	}
	return c.Queries.HasApplicationEvent(ctx, store.HasApplicationEventParams{
		ApplicationID: appID,
		EventType:     bus.TopicApplicationTerminal,
	})
}

// Handle implements bus.Handler.
func (c *Consumer) Handle(ctx context.Context, entryID string, env bus.Envelope) error {
	appID, err := parseApplicationID(env.JobID)
	if err != nil {
		return fmt.Errorf("terminal: invalid job_id %q: %w", env.JobID, err)
	}

	var payload terminalPayload
	if err := c.WorkingMemory.Get(ctx, env.PayloadRef, &payload); err != nil {
		return fmt.Errorf("terminal: failed to read working memory %s: %w", env.PayloadRef, err)
	}

	switch payload.Status {
	case "submitted":
		if _, err := c.Queries.MarkApplicationSubmitted(ctx, appID); err != nil {
			return fmt.Errorf("terminal: failed to mark application submitted: %w", err)
		}
	case "ready_for_review":
		if _, err := c.Queries.MarkApplicationNeedsReview(ctx, appID); err != nil {
			return fmt.Errorf("terminal: failed to mark application needs review: %w", err)
		}
	default:
		return fmt.Errorf("terminal: unrecognized status %q", payload.Status)
	}

	reasonsJSON, err := json.Marshal(payload.Reasons)
	if err != nil {
		return fmt.Errorf("terminal: failed to encode reasons: %w", err)
	}
	if _, err := c.Queries.AppendApplicationEvent(ctx, store.AppendApplicationEventParams{
		ApplicationID:   appID,
		EventType:       bus.TopicApplicationTerminal,
		ProducedByAgent: AgentName,
		PayloadJson:     reasonsJSON,
	}); err != nil {
		return fmt.Errorf("terminal: failed to record application event: %w", err)
	}

	return nil
}

func parseApplicationID(jobID string) (pgtype.UUID, error) {
	var id pgtype.UUID
	if err := id.Scan(jobID); err != nil {
		return pgtype.UUID{}, fmt.Errorf("terminal: %q is not a valid UUID: %w", jobID, err)
	}
	return id, nil
}
