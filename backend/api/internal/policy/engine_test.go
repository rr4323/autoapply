package policy

import "testing"

func cleanRules() Rules {
	return Rules{
		Version:                 "policy-rules-v1",
		MinGenerateScore:        60,
		MinAutosubmitScore:      80,
		RequireReviewIfBotCheck: true,
		VelocityCapPerDay:       15,
		PlatformAllowlist:       []string{"greenhouse", "lever"},
	}
}

func floatPtr(f float64) *float64 { return &f }

func assertReasonsNonEmpty(t *testing.T, d Decision) {
	t.Helper()
	if len(d.Reasons) == 0 {
		t.Fatalf("decision %+v has no reasons — TDD.md §7.2 requires reasons on every path", d)
	}
}

// --- Post-scoring branches ---

func TestEvaluate_PostScoring_BelowThreshold(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{DecisionPoint: DecisionPointPostScoring, Score: 45})

	if d.Action != ActionStop {
		t.Fatalf("action = %v, want %v", d.Action, ActionStop)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PostScoring_SpendCapReached(t *testing.T) {
	rules := cleanRules()
	rules.MaxDailyGenerateSpendUSD = floatPtr(10.0)
	engine := NewEngine(rules)

	// Score is comfortably above min_generate_score — proves the spend
	// cap stops generation "regardless of score" (§7.2's own wording).
	d := engine.Evaluate(Context{
		DecisionPoint:         DecisionPointPostScoring,
		Score:                 95,
		TodayGenerateSpendUSD: 10.0,
	})

	if d.Action != ActionStop {
		t.Fatalf("action = %v, want %v", d.Action, ActionStop)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PostScoring_NoSpendCapSetDoesNotBlock(t *testing.T) {
	engine := NewEngine(cleanRules()) // MaxDailyGenerateSpendUSD is nil

	d := engine.Evaluate(Context{
		DecisionPoint:         DecisionPointPostScoring,
		Score:                 95,
		TodayGenerateSpendUSD: 1_000_000, // would blow any real cap, but none is set
	})

	if d.Action != ActionGenerate {
		t.Fatalf("action = %v, want %v", d.Action, ActionGenerate)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PostScoring_CleanPass(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{DecisionPoint: DecisionPointPostScoring, Score: 75})

	if d.Action != ActionGenerate {
		t.Fatalf("action = %v, want %v", d.Action, ActionGenerate)
	}
	assertReasonsNonEmpty(t, d)
}

// --- Pre-submit branches ---

func TestEvaluate_PreSubmit_BotCheck(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{
		DecisionPoint:    DecisionPointPreSubmit,
		Score:            95,
		BotCheckDetected: true,
		TodaySubmitCount: 0,
	})

	if d.Action != ActionRequireReview {
		t.Fatalf("action = %v, want %v", d.Action, ActionRequireReview)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PreSubmit_VelocityCap(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{
		DecisionPoint:    DecisionPointPreSubmit,
		Score:            95,
		BotCheckDetected: false,
		TodaySubmitCount: 15, // == velocity_cap_per_day: already hit today
	})

	if d.Action != ActionRequireReview {
		t.Fatalf("action = %v, want %v", d.Action, ActionRequireReview)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PreSubmit_BelowAutosubmitScore(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{
		DecisionPoint:    DecisionPointPreSubmit,
		Score:            70, // above min_generate_score, below min_autosubmit_score
		BotCheckDetected: false,
		TodaySubmitCount: 0,
	})

	if d.Action != ActionRequireReview {
		t.Fatalf("action = %v, want %v", d.Action, ActionRequireReview)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PreSubmit_CleanPass(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{
		DecisionPoint:    DecisionPointPreSubmit,
		Score:            90,
		BotCheckDetected: false,
		TodaySubmitCount: 3,
	})

	if d.Action != ActionSubmit {
		t.Fatalf("action = %v, want %v", d.Action, ActionSubmit)
	}
	assertReasonsNonEmpty(t, d)
}

func TestEvaluate_PreSubmit_MultipleReasonsCombine(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{
		DecisionPoint:    DecisionPointPreSubmit,
		Score:            50, // below min_autosubmit_score
		BotCheckDetected: true,
		TodaySubmitCount: 0,
	})

	if d.Action != ActionRequireReview {
		t.Fatalf("action = %v, want %v", d.Action, ActionRequireReview)
	}
	if len(d.Reasons) != 2 {
		t.Fatalf("reasons = %v, want exactly 2 (bot-check and low score)", d.Reasons)
	}
}

func TestEvaluate_RequireReviewIfBotCheckFalse_IgnoresBotCheck(t *testing.T) {
	rules := cleanRules()
	rules.RequireReviewIfBotCheck = false
	engine := NewEngine(rules)

	d := engine.Evaluate(Context{
		DecisionPoint:    DecisionPointPreSubmit,
		Score:            90,
		BotCheckDetected: true, // present, but the config toggle is off
		TodaySubmitCount: 0,
	})

	if d.Action != ActionSubmit {
		t.Fatalf("action = %v, want %v — the require_review_if_bot_check:false toggle should be honored", d.Action, ActionSubmit)
	}
}

func TestEvaluate_UnknownDecisionPoint_DefaultsToRequireReview(t *testing.T) {
	engine := NewEngine(cleanRules())

	d := engine.Evaluate(Context{DecisionPoint: "bogus", Score: 100})

	if d.Action != ActionRequireReview {
		t.Fatalf("action = %v, want %v (fail-safe default)", d.Action, ActionRequireReview)
	}
	assertReasonsNonEmpty(t, d)
}

// --- Table-driven sweep: reasons must be non-empty on every branch ---

func TestEvaluate_ReasonsNeverEmpty(t *testing.T) {
	engine := NewEngine(cleanRules())

	contexts := []Context{
		{DecisionPoint: DecisionPointPostScoring, Score: 0},
		{DecisionPoint: DecisionPointPostScoring, Score: 100},
		{DecisionPoint: DecisionPointPreSubmit, Score: 0, BotCheckDetected: true, TodaySubmitCount: 999},
		{DecisionPoint: DecisionPointPreSubmit, Score: 100, BotCheckDetected: false, TodaySubmitCount: 0},
	}

	for _, ctx := range contexts {
		assertReasonsNonEmpty(t, engine.Evaluate(ctx))
	}
}
