# Error Handling

## What it is

Go has no exceptions/try-catch for ordinary errors. A function that can fail simply returns an extra value of type `error` — by convention, always the *last* return value. Callers check it immediately with `if err != nil`.

## Verified example

```go
func parseScore(raw string) (int, error) {
	if raw == "" {
		return 0, errors.New("score cannot be empty")
	}
	score := 0
	for _, ch := range raw {
		if ch < '0' || ch > '9' {
			return 0, fmt.Errorf("invalid character %q in score %q", ch, raw)
		}
		score = score*10 + int(ch-'0')
	}
	return score, nil
}

func main() {
	inputs := []string{"85", "", "8x"}
	for _, in := range inputs {
		score, err := parseScore(in)
		if err != nil {
			fmt.Printf("input %q failed: %v\n", in, err)
			continue
		}
		fmt.Printf("input %q -> score %d\n", in, score)
	}
}
```
```
input "85" -> score 85
input "" failed: score cannot be empty
input "8x" failed: invalid character 'x' in score "8x"
```

## The idiom: `if err != nil` immediately after every fallible call

It looks repetitive coming from try/catch languages. The payoff: error handling is never invisible — you can't accidentally let a failure fall through a scope the way a missing `catch` block can. You'll type this exact five-token pattern hundreds of times in this codebase.

## `errors.New` vs. `fmt.Errorf`

- `errors.New("fixed message")` — no interpolation.
- `fmt.Errorf("invalid input: %s", val)` — string interpolation, `%v`/`%s`/`%q` etc.
- `fmt.Errorf("query failed: %w", err)` — the `%w` verb specifically **wraps** an underlying error rather than just stringifying it, so a caller further up can `errors.Is`/`errors.As` to check what actually went wrong underneath a higher-level message. Worth reaching for once you're wrapping DB/HTTP errors in step 13+.

## What `errcheck` (in `.golangci.yml`) actually polices

```go
os.Open("/does/not/exist") // error return value silently dropped
```
```
$ golangci-lint run
main.go:6:9: Error return value of `os.Open` is not checked (errcheck)
```
A silently-ignored error usually means "the program thinks it succeeded when it didn't" — a nasty bug class to debug after the fact. The linter makes this a hard failure, not a suggestion.

## Standard use case

The Policy Engine's `Decision{action, reasons}` (`TDD.md` §7.2) is this idiom scaled up: `reasons` is never optional, matching the principle that a failure/decision is always explicit and auditable, never silent. Every DB query, HTTP call, and Redis operation in the Go control plane returns `(result, error)` and gets checked the same way.
