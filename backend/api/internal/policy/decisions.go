package policy

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jackc/pgx/v5/pgtype"

	"github.com/rr4323/autoapply/backend/api/internal/store"
)

// RecordDecision writes the policy_decisions audit row and an
// application_events row for one Decision, using an already
// transaction-scoped Queries (qtx) — callers own the transaction
// boundary (and whatever else needs to be atomic with it, e.g. an
// applications.status update), this only adds the two audit writes to it.
// Shared by ScoredConsumer (post-scoring) and AgentCallbackHandler
// (pre-submit) rather than duplicating the same two inserts twice.
func RecordDecision(
	ctx context.Context,
	qtx *store.Queries,
	appID pgtype.UUID,
	decisionPoint DecisionPoint,
	decision Decision,
	rulesVersion string,
	agentName string,
	eventType string,
) error {
	reasonsJSON, err := json.Marshal(decision.Reasons)
	if err != nil {
		return fmt.Errorf("policy: failed to encode reasons: %w", err)
	}

	if _, err := qtx.CreatePolicyDecision(ctx, store.CreatePolicyDecisionParams{
		ApplicationID: appID,
		DecisionPoint: string(decisionPoint),
		Action:        string(decision.Action),
		ReasonsJson:   reasonsJSON,
		RulesVersion:  &rulesVersion,
	}); err != nil {
		return fmt.Errorf("policy: failed to write policy_decisions row: %w", err)
	}

	if _, err := qtx.AppendApplicationEvent(ctx, store.AppendApplicationEventParams{
		ApplicationID:   appID,
		EventType:       eventType,
		ProducedByAgent: agentName,
		PayloadJson:     reasonsJSON,
	}); err != nil {
		return fmt.Errorf("policy: failed to record application event: %w", err)
	}

	return nil
}
