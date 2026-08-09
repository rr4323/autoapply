# Message Envelope Contract

Source of truth: `docs/TDD.md` §4.1. Both `backend/api` (Go) and `backend/agents` (Python) implement this identically — if the shape ever needs to change, update this file, the Go struct (`backend/api/internal/bus/envelope.go`), and the Pydantic model (`backend/agents/src/agentos_agents/common/envelope.py`) in the same change.

## Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `job_id` | string | yes | Identifies the application this message belongs to. Used as the Redis Streams partition key (§4.3 — ordering enforced per-`job_id`, not globally) and as part of the working-memory key. |
| `trace_id` | string | yes | Propagated end-to-end across every hop of one application's journey (§11.1). Independent of `job_id` — every message carries it purely for observability. |
| `event_type` | string | yes | Which topic/stage this message represents, e.g. `"jd.parsed"`. |
| `produced_by` | string | yes | Which agent/service produced this message, e.g. `"scraper-agent"`. |
| `timestamp` | string | yes | RFC3339 (e.g. `"2026-08-09T14:00:00Z"`). Kept as a plain string on both sides deliberately — avoids Go `time.Time` / Python `datetime` serialization mismatches; the value is treated as opaque for now. |
| `payload_ref` | string | yes | Pointer into working memory (see below) where the actual message content lives — the envelope itself never carries large payloads (§4.1). |

## Validation rule

All six fields are required. A message missing any of them — especially `job_id`/`trace_id`, since those are what make a message routable and traceable at all — must be rejected before any handler logic runs, not silently processed with a blank field.

## Working-memory key scheme (§5)

```
working_memory:job:{job_id}:{stage}
```
e.g. `working_memory:job:b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f:jd_parsed`. Built by a single helper function on each side (`WorkingMemoryKey` in Go, `working_memory_key` in Python) — never hand-formatted at the call site, so the scheme can only drift in one place if it ever needs to change.

## Cross-language proof

`testdata/envelope_golden.json` is the canonical example both languages' test suites parse. If both a Go test and a Python test independently agree on what every field in that same file means, that's the proof the two implementations share one wire format — no actual inter-process round trip needed for this to be a valid test.
