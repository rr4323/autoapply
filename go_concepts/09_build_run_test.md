# `go run` vs `go build` vs `go test` vs `go install`

## The commands, what each actually does

| Command | What it does | When to use it |
|---|---|---|
| `go run ./cmd/api` | Compiles to a temp location, executes, **throws the binary away after** | Fast local iteration while writing code |
| `go build -o bin/api ./cmd/api` | Produces a real, standalone, statically-linked binary on disk | What actually ships / runs in Docker |
| `go test ./...` | Compiles and runs every `*_test.go` file in the module | CI, and locally before every commit |
| `go install ./cmd/api` | Like `go build`, but installs the binary into `$GOPATH/bin` (or `$GOBIN`) instead of the current directory | Installing a CLI tool you want on your `PATH` — how we installed `golangci-lint` itself in Step 1 |

## Verified

```
$ go run ./cmd/api
2026/08/09 00:58:09 INFO agentos api starting
```
No file left behind afterward — `go run` compiled to a temp dir and cleaned up.

```
$ go build -o bin/api ./cmd/api && file bin/api
bin/api: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, ...
```
**Statically linked** is the key detail — no runtime, no interpreter needed on the machine that eventually runs this binary. That's the concrete reason `TDD.md` §2 picked Go for the control plane: "a static binary that's trivial to deploy" — `docker run` this file on a bare `scratch`/`distroless` image and it just works.

## A trap worth knowing about

`go build ./...` (three dots — "everything in this module") writes a compiled binary to disk for **every** `main` package it finds, named after that package's directory. Running it from `backend/api/` produces `backend/api/api` (named after the `cmd/api` directory) sitting right there, easy to accidentally `git add`. That's why `Makefile`'s `build-go` target is explicit: `go build -o bin/api ./cmd/api` — one named output path, no surprises, and `bin/` is already in `.gitignore`.

## Standard use case

- Day-to-day coding: `go run ./cmd/api`, iterate, `Ctrl+C`, repeat.
- Before committing: `make lint && make test` (wraps `go test ./...` and `golangci-lint run ./...`).
- Shipping: `make build` (wraps the explicit `go build -o bin/api ./cmd/api`), then that binary goes into a container.
