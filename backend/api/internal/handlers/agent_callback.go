package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/rr4323/autoapply/backend/api/internal/policy"
	"github.com/rr4323/autoapply/backend/api/internal/store"
)

const policyEngineAgentName = "policy-engine"

// AgentCallbackHandler implements POST /internal/agent/callback — the
// TDD.md §7.3 enforcement boundary. This step's scope is deliberately
// just the submit-claim re-check (action == "submit"); no other agent
// reports a stage result through this endpoint yet, since nothing else
// produces one (openapi.yaml's broader "any agent reports a stage
// result" description is the eventual shape, not what's built today).
type AgentCallbackHandler struct {
	Queries *store.Queries
	Pool    *pgxpool.Pool
	Engine  *policy.Engine
}

func NewAgentCallbackHandler(q *store.Queries, pool *pgxpool.Pool, engine *policy.Engine) *AgentCallbackHandler {
	return &AgentCallbackHandler{Queries: q, Pool: pool, Engine: engine}
}

type agentCallbackRequest struct {
	JobID            string `json:"job_id"`
	Action           string `json:"action"`
	BotCheckDetected bool   `json:"bot_check_detected"`
}

type agentCallbackResponse struct {
	Accepted bool     `json:"accepted"`
	Action   string   `json:"action"`
	Reasons  []string `json:"reasons"`
}

// Callback re-evaluates a claimed "submit" server-side before honoring
// it — the calling agent's own belief that it's clear to submit is never
// trusted directly. Go independently re-derives the decision from data
// it owns (the persisted score, its own submitted_at history for the
// velocity cap) combined with whatever live-DOM context the agent reports
// (bot_check_detected) through the same Evaluate() call every other
// decision point uses — never a bare "trust me" acceptance of the claim.
func (h *AgentCallbackHandler) Callback(w http.ResponseWriter, r *http.Request) {
	var req agentCallbackRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json", "request body must be valid JSON")
		return
	}

	if req.Action != "submit" {
		writeJSONError(w, http.StatusBadRequest, "unsupported_action",
			fmt.Sprintf("action %q is not supported by this endpoint yet", req.Action))
		return
	}

	var appID pgtype.UUID
	if err := appID.Scan(req.JobID); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_request", "job_id is not a valid UUID")
		return
	}

	ctx := r.Context()

	app, err := h.Queries.GetApplication(ctx, appID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSONError(w, http.StatusNotFound, "not_found", "application not found")
			return
		}
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to load application")
		return
	}

	// Idempotent: a submit already honored isn't re-evaluated (and
	// submitted_at isn't overwritten) on a retried callback.
	if app.Status == store.ApplicationStatusSubmitted {
		writeCallbackResponse(w, http.StatusOK, agentCallbackResponse{
			Accepted: true, Action: string(policy.ActionSubmit),
			Reasons: []string{"already submitted"},
		})
		return
	}

	score := 0.0
	if app.JdFitScore != nil {
		score = *app.JdFitScore
	}

	submitCount, err := h.Queries.CountSubmittedApplicationsToday(ctx, app.UserID)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to check velocity cap")
		return
	}

	decision := h.Engine.Evaluate(policy.Context{
		DecisionPoint:    policy.DecisionPointPreSubmit,
		Score:            score,
		BotCheckDetected: req.BotCheckDetected,
		TodaySubmitCount: int(submitCount),
	})
	accepted := decision.Action == policy.ActionSubmit

	if err := h.persist(ctx, appID, decision, req.BotCheckDetected, accepted); err != nil {
		slog.Error("agent callback: failed to persist decision", "job_id", req.JobID, "error", err)
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to record decision")
		return
	}

	status := http.StatusOK
	if !accepted {
		// The agent's claim is rejected — Go wins, not a client error on
		// the agent's part (its request was well-formed), so 409 Conflict
		// fits better than 400/403: the claimed action conflicts with
		// server-side state the agent doesn't have full visibility into.
		status = http.StatusConflict
	}
	writeCallbackResponse(w, status, agentCallbackResponse{
		Accepted: accepted, Action: string(decision.Action), Reasons: decision.Reasons,
	})
}

func (h *AgentCallbackHandler) persist(
	ctx context.Context, appID pgtype.UUID, decision policy.Decision, botCheckDetected, accepted bool,
) error {
	tx, err := h.Pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to start transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	qtx := h.Queries.WithTx(tx)

	// TDD.md §8's application_events examples name "submit-attempted" and
	// "submit-blocked-by-captcha" directly — used here exactly, with a
	// third, equally-descriptive event_type for a rejection that isn't
	// specifically about a bot-check (a low score or the velocity cap).
	eventType := "submit-attempted"
	if !accepted {
		if botCheckDetected {
			eventType = "submit-blocked-by-captcha"
		} else {
			eventType = "submit-blocked"
		}
	}

	if err := policy.RecordDecision(
		ctx, qtx, appID, policy.DecisionPointPreSubmit, decision,
		h.Engine.Rules.Version, policyEngineAgentName, eventType,
	); err != nil {
		return err
	}

	if accepted {
		if _, err := qtx.MarkApplicationSubmitted(ctx, appID); err != nil {
			return fmt.Errorf("failed to mark application submitted: %w", err)
		}
	} else {
		if _, err := qtx.MarkApplicationNeedsReview(ctx, appID); err != nil {
			return fmt.Errorf("failed to mark application needs review: %w", err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}
	return nil
}

func writeCallbackResponse(w http.ResponseWriter, status int, resp agentCallbackResponse) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(resp)
}
