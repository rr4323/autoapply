# JSON Marshaling — `encoding/json` and Struct Tags

## What it is

`encoding/json` converts between Go structs and JSON. **Struct tags** — the backtick-quoted strings after each field — tell it which JSON key maps to which Go field, since Go field names are capitalized (`X`) but JSON keys usually aren't (`x`).

## Verified example

```go
type Point struct {
	X     int    `json:"x"`
	Y     int    `json:"y"`
	Label string `json:"label,omitempty"`
}
```
```
$ go run json_demo.go
marshaled: {"x":1,"y":2,"label":"origin"}
unmarshaled: {X:1 Y:2 Label:origin}
```
- **`json.Marshal(p)`** — Go struct → JSON bytes.
- **`json.Unmarshal(data, &p2)`** — JSON bytes → Go struct. Note the `&` — `Unmarshal` needs a pointer so it can write into the target.
- **`json:"x"`** — the field appears as `"x"` in JSON, not `"X"`.
- **`,omitempty`** — if the field is the zero value (`""`, `0`, `nil`, ...), omit it from the output entirely rather than writing `"label":""`.

## The gap worth knowing about: no built-in "required"

```go
badJSON := `{"x": 5, "y": 6}`  // no "label" key at all
var p3 Point
json.Unmarshal([]byte(badJSON), &p3)
fmt.Printf("%+v\n", p3) // {X:5 Y:6 Label:}  — no error!
```
`Unmarshal` doesn't care that `label` was missing — the field just stays at its zero value (`""` for a string). Go's `encoding/json` has **no concept of "required field."** If your data has a real invariant ("`trace_id` must always be present"), you write it yourself:
```go
func (p Point) Validate() error {
	if p.Label == "" {
		return errors.New("label is required")
	}
	return nil
}
```
Contrast this with [python_concepts/01_pydantic_basics.md](../python_concepts/01_pydantic_basics.md) — Pydantic enforces "required" automatically from the type annotation alone, no `Validate()` method needed. Different languages, genuinely different defaults; worth knowing rather than assuming Go behaves like whatever you're used to.

## Standard use case

Every message on the Redis Streams bus (`TDD.md` §4.1's envelope: `job_id`, `trace_id`, `event_type`, `produced_by`, `timestamp`, `payload_ref`) is a Go struct with `json` tags on the publishing side, and needs an explicit `Validate()` to reject a malformed envelope (missing `job_id`/`trace_id`) before it's trusted — this is the literal shape of `docs/BACKEND_BUILD_STEPS.md` Step 4.
