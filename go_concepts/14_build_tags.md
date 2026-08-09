# Build Tags — Excluding Code from the Default Build

## What it is

A `//go:build <tag>` comment at the very top of a file (before `package`, with a blank line after it) tells the Go toolchain "only compile this file when `<tag>` is explicitly passed." Without that tag on the command line, the file is invisible to `go build`/`go test`/`go vet` — not even parsed.

## Verified example

`backend/api/internal/bus/roundtrip_integration_test.go` starts with:
```go
//go:build integration

package bus
```
Confirmed behavior:
```
$ go test ./...              # no -tags flag
ok  	.../internal/bus	0.008s     # roundtrip test doesn't run — invisible

$ go test -tags=integration ./... -run TestRoundTrip -v
=== RUN   TestRoundTrip_GoPublishesPythonConsumes
--- PASS: TestRoundTrip_GoPublishesPythonConsumes (7.73s)
```

## Why this file needed one

`docs/IMPLEMENTATION_PLAN.md` §0 splits tests into tiers on purpose: unit tests should be fast and dependency-free (what `go test ./...` runs by default, every time, no setup); integration tests are allowed to be slower and need real infrastructure. The round-trip test spins up an actual Docker container and shells out to a real Python process — completely reasonable for an integration test, completely wrong to run on every `go test ./...` a developer types while iterating on unrelated code. The build tag is what keeps it opt-in.

## Standard use case

Anything needing Docker, a real network call, or another language's toolchain gets `//go:build integration` (or another tag name if you want finer-grained tiers later — `//go:build e2e`, etc.) and its own `make` target, mirroring `docs/BACKEND_BUILD_STEPS.md`'s three-tier testing philosophy (unit → integration → E2E) directly in the build system, not just as a documentation convention.
