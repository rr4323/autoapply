# Embedded Structs and JSON Flattening

## What it is

A struct field declared with only a type, no name, is an **embedded field**. `encoding/json` promotes an embedded struct's fields up to the outer struct's JSON object — they appear at the same level, not nested under a key. This is Go's answer to OpenAPI's `allOf` composition.

## Verified example (from `backend/api/internal/handlers/dto.go`)

`openapi.yaml` defines `ApplicationDetail` as:
```yaml
ApplicationDetail:
  allOf:
    - $ref: "#/components/schemas/ApplicationSummary"
    - type: object
      properties:
        jd_url: { type: string, nullable: true }
        score_breakdown: { ... }
        # ...
```
`allOf` here means: every `ApplicationSummary` field, *plus* these extra ones, all flattened into one JSON object.

```go
type applicationDetailResponse struct {
	applicationSummaryResponse          // embedded — no field name
	JDUrl              *string                 `json:"jd_url"`
	ScoreBreakdown     *scoreBreakdownResponse `json:"score_breakdown"`
	// ...
}
```
Confirmed via the real endpoint response:
```json
{"id":"8fb...","company":null,"role_title":null,"source":"manual","status":"pending",
 "jd_url":"https://boards.greenhouse.io/example/jobs/999","score_breakdown":null, ...}
```
`id`, `company`, `status`, etc. (from `applicationSummaryResponse`) and `jd_url`, `score_breakdown` (declared directly on `applicationDetailResponse`) all appear as siblings in one flat JSON object — not `{"applicationSummaryResponse": {...}, "jd_url": ...}`.

## The rule

`type Outer struct { Inner }` (no field name before `Inner`) embeds it. Both Go's own field access (`outer.ID` works directly, no need for `outer.Inner.ID`) and `encoding/json`'s marshaling promote the embedded struct's fields as if they were declared directly on the outer struct — **unless** there's a name collision, in which case the outer struct's own field wins and the embedded one is shadowed.

## Standard use case

Any OpenAPI schema using `allOf` to compose a "detail" shape out of a "summary" shape plus extra fields — exactly this codebase's `ApplicationSummary`/`ApplicationDetail` pair, and a pattern that'll repeat for `Profile`, `SearchProfile`, and others as their endpoints get built.
