# YAML Config Loading with `gopkg.in/yaml.v3`

## What it is

[11_json_marshaling.md](11_json_marshaling.md) covered `encoding/json` and struct tags for JSON. `gopkg.in/yaml.v3` is the same idea for YAML — struct tags map Go fields to YAML keys — used for the Policy Engine's rule config (`TDD.md` §7.1) specifically because it's meant to be a human-edited config file, not a wire format: YAML supports comments (`# set per §7.5...`), which is exactly what a rules file that a non-engineer might eventually edit ([§7.6](../docs/TDD.md)'s revisit trigger) benefits from and JSON can't do at all.

## Verified example (from `backend/api/internal/policy/rules.go`)

```go
type Rules struct {
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
```

## The wrapper-struct trick, for a nested top-level key

`backend/api/config/policy_rules.yaml` nests everything under a `rules:` top-level key (matching `TDD.md` §7.1's own example exactly, so the doc and the real config file read identically):
```yaml
rules:
  min_generate_score: 60
  ...
```
Unmarshaling straight into `Rules` would look for `min_generate_score` at the document's *root*, not inside `rules:`, and silently leave every field at its zero value — no error, just wrong data. `rulesFile{ Rules Rules `yaml:"rules"` }` gives `yaml.Unmarshal` a matching shape for the actual document structure; unwrapping to `wrapper.Rules` afterward keeps every other function in the package working with the plain `Rules` type, not the wrapper.

## `*float64` for "no cap set yet" — same nullable-pointer pattern as JSON

`max_daily_generate_spend_usd: null` in the YAML needs `*float64`, not `float64`, for exactly the reason [20_embedded_structs_json.md](20_embedded_structs_json.md) and the `applications` handlers already established for JSON: a bare `float64` can't distinguish "explicitly zero" from "not set," and `TDD.md` §7.5 is explicit that this field starts unset (`null`) until the Cost Circuit Breaker computes a real value from actual spend data. `TestLoadRules_ParsesTheRealConfigFile` asserts `rules.MaxDailyGenerateSpendUSD != nil` fails — i.e., it *is* nil — confirming the parse preserves that distinction rather than defaulting to `0.0`, which would (wrongly) mean "spend cap of $0, stop everything immediately."

## Standard use case

Any config file meant to be hand-edited by a person rather than only generated/consumed by code — comments and a more permissive syntax are YAML's actual advantage over JSON here, not a technical requirement.
