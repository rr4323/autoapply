# A Real Bug: `pgx` Can't Encode a Slice of a Custom Enum Type

## What happened

Building the `GET /api/v1/applications` status filter (Step 15), the query took an optional `application_status[]` array parameter. sqlc generated the Go param type as `[]ApplicationStatus` (its own enum wrapper type, from `models.go`). Calling the query with an **empty** slice of that type failed:
```
failed to encode args[1]: unable to encode []store.ApplicationStatus{} into text format
for unknown type (OID 17867): cannot find encode plan
```

## Why

`pgx` v5 knows how to encode plain Go types (`string`, `[]string`, `int32`, ...) into their matching Postgres wire formats automatically. It has **no built-in encode plan for a slice of a custom named type** (`[]store.ApplicationStatus`, where `ApplicationStatus` is `type ApplicationStatus string`) targeting a custom Postgres enum array (`application_status[]`) — that combination needs an explicit type registration `pgx` wasn't given.

## The fix — cast on the SQL side instead

```sql
-- Before (broken): sqlc infers []ApplicationStatus from the target type
AND (cardinality(sqlc.arg(status_filter)::application_status[]) = 0
     OR status = ANY(sqlc.arg(status_filter)::application_status[]))

-- After (works): cast to text[]/text — sqlc then infers plain []string
AND (cardinality(sqlc.arg(status_filter)::text[]) = 0
     OR status::text = ANY(sqlc.arg(status_filter)::text[]))
```
Casting the *target* type to `text[]` (and casting the `status` column to `text` for the comparison) means sqlc generates a plain `StatusFilter []string` parameter — a type `pgx` already knows how to encode natively, with zero custom registration needed. Verified fix, reproduced first:
```
$ go run ./cmd/debugquery
list result: [] err: <nil>
```
(Previously the same call returned the "cannot find encode plan" error above.)

## The lesson

sqlc infers Go parameter types from the *SQL* type the value is cast/compared against — if that's a custom Postgres enum type, you get a custom Go type, and pgx may not have an encoder ready for a *slice* of it even though it handles scalar custom enums fine. Casting to a plain built-in type (`text`, `text[]`, `int`, ...) on the SQL side, where the actual generated code doesn't need type-specific data, sidesteps the whole problem — Postgres's own implicit/explicit casting does the semantic work instead of the Go driver.

## Standard use case

Any sqlc query taking an **array** of a Postgres enum as a parameter. Scalar enum params don't hit this — confirmed by `CreateApplication` (Step 13/15), which passes `Source: store.ApplicationSourceManual` (a bare `ApplicationSource` value) successfully on every test run. That works because `ApplicationSource` is `type ApplicationSource string`, and pgx's default text-encoding fallback covers any named type whose underlying `reflect.Kind` is `string` — no explicit `Value()` method needed (checking `models.go`, the enum types only generate `Scan`, for reading *out* of the database; there's no `Value()` at all on the bare type, only on its `Null*` wrapper). That scalar fallback doesn't extend to **slices** of such a type — a `[]ApplicationStatus` needs a registered array codec for the specific element OID, which isn't there by default. It's specifically the slice case that's unsupported, not custom enums in general.
