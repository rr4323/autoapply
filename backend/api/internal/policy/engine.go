package policy

import "fmt"

// DecisionPoint identifies which of §7.2's two invocation points a
// Context describes — same engine, same Rules, different context shape.
type DecisionPoint string

const (
	DecisionPointPostScoring DecisionPoint = "post_scoring"
	DecisionPointPreSubmit   DecisionPoint = "pre_submit"
)

type Action string

const (
	ActionGenerate      Action = "generate"
	ActionStop          Action = "stop"
	ActionSubmit        Action = "submit"
	ActionRequireReview Action = "require_review"
)

// Context carries only what one decision point needs; fields irrelevant
// to the current DecisionPoint are simply unused, not an error.
type Context struct {
	DecisionPoint         DecisionPoint
	Score                 float64
	BotCheckDetected      bool
	TodayGenerateSpendUSD float64
	TodaySubmitCount      int
}

// Decision.Reasons is never empty (TDD.md §7.2: "not optional") — every
// branch, including a clean pass, states why.
type Decision struct {
	Action  Action
	Reasons []string
}

// Engine binds one loaded Rules to Evaluate. Pure: no I/O, no clock, no
// randomness — the same Context always produces the same Decision.
type Engine struct {
	Rules Rules
}

func NewEngine(rules Rules) *Engine {
	return &Engine{Rules: rules}
}

func (e *Engine) Evaluate(ctx Context) Decision {
	switch ctx.DecisionPoint {
	case DecisionPointPostScoring:
		return e.evaluatePostScoring(ctx)
	case DecisionPointPreSubmit:
		return e.evaluatePreSubmit(ctx)
	default:
		// An unrecognized decision point is a caller bug, not a reason to
		// guess — require_review is the safe default in every direction
		// this engine can fail toward (§1: auto-submit is the narrow,
		// conservative action, everything else defaults to "wait for a human").
		return Decision{
			Action:  ActionRequireReview,
			Reasons: []string{fmt.Sprintf("unrecognized decision point %q", ctx.DecisionPoint)},
		}
	}
}

func (e *Engine) evaluatePostScoring(ctx Context) Decision {
	var reasons []string

	if ctx.Score < e.Rules.MinGenerateScore {
		reasons = append(reasons, fmt.Sprintf(
			"score %.1f is below min_generate_score %.1f", ctx.Score, e.Rules.MinGenerateScore,
		))
	}
	if e.Rules.MaxDailyGenerateSpendUSD != nil && ctx.TodayGenerateSpendUSD >= *e.Rules.MaxDailyGenerateSpendUSD {
		// "regardless of score" (§7.2) — this reason is independent of and
		// additive to the score check above, not a replacement for it.
		reasons = append(reasons, fmt.Sprintf(
			"today's generation spend $%.2f has reached the $%.2f daily cap",
			ctx.TodayGenerateSpendUSD, *e.Rules.MaxDailyGenerateSpendUSD,
		))
	}

	if len(reasons) > 0 {
		return Decision{Action: ActionStop, Reasons: reasons}
	}
	return Decision{
		Action: ActionGenerate,
		Reasons: []string{fmt.Sprintf(
			"score %.1f meets min_generate_score %.1f and the daily generate spend cap has not been reached",
			ctx.Score, e.Rules.MinGenerateScore,
		)},
	}
}

func (e *Engine) evaluatePreSubmit(ctx Context) Decision {
	var reasons []string

	if e.Rules.RequireReviewIfBotCheck && ctx.BotCheckDetected {
		reasons = append(reasons, "bot-check detected on the live page")
	}
	if ctx.Score < e.Rules.MinAutosubmitScore {
		reasons = append(reasons, fmt.Sprintf(
			"score %.1f is below min_autosubmit_score %.1f", ctx.Score, e.Rules.MinAutosubmitScore,
		))
	}
	if ctx.TodaySubmitCount >= e.Rules.VelocityCapPerDay {
		reasons = append(reasons, fmt.Sprintf(
			"today's auto-submit count %d has reached the velocity cap of %d",
			ctx.TodaySubmitCount, e.Rules.VelocityCapPerDay,
		))
	}

	if len(reasons) > 0 {
		return Decision{Action: ActionRequireReview, Reasons: reasons}
	}
	return Decision{
		Action: ActionSubmit,
		Reasons: []string{fmt.Sprintf(
			"no bot-check detected, score %.1f meets min_autosubmit_score %.1f, and today's submit count is under the velocity cap of %d",
			ctx.Score, e.Rules.MinAutosubmitScore, e.Rules.VelocityCapPerDay,
		)},
	}
}
