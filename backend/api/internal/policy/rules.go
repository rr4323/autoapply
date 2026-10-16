// Package policy implements the Policy Engine (TDD.md §7) — the single,
// named component authorized to decide generate/stop/submit/require_review.
// Deliberately isolated from every AI/agent code path: nothing here calls
// an LLM or reads a retrieved chunk, so it can stay boring and auditable.
package policy

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Rules is the declarative rule config from TDD.md §7.1 — a config edit,
// not a code change, is what it takes to move a threshold.
type Rules struct {
	Version                  string   `yaml:"version"`
	MinGenerateScore         float64  `yaml:"min_generate_score"`
	MinAutosubmitScore       float64  `yaml:"min_autosubmit_score"`
	RequireReviewIfBotCheck  bool     `yaml:"require_review_if_bot_check"`
	VelocityCapPerDay        int      `yaml:"velocity_cap_per_day"`
	PlatformAllowlist        []string `yaml:"platform_allowlist"`
	MaxDailyGenerateSpendUSD *float64 `yaml:"max_daily_generate_spend_usd"`
}

type rulesFile struct {
	Rules Rules `yaml:"rules"`
}

// LoadRules reads and parses a policy_rules.yaml file (e.g.
// backend/api/config/policy_rules.yaml). The only I/O in this package —
// Evaluate itself takes an already-loaded Rules and does none.
func LoadRules(path string) (Rules, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Rules{}, fmt.Errorf("policy: failed to read rules file %s: %w", path, err)
	}

	var wrapper rulesFile
	if err := yaml.Unmarshal(data, &wrapper); err != nil {
		return Rules{}, fmt.Errorf("policy: failed to parse rules yaml %s: %w", path, err)
	}

	return wrapper.Rules, nil
}
