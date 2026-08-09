.PHONY: lint lint-go lint-py test test-go test-py test-integration build build-go

GO_DIR := backend/api
PY_DIR := backend/agents

lint: lint-go lint-py

lint-go:
	cd $(GO_DIR) && golangci-lint run ./...

lint-py:
	cd $(PY_DIR) && uv run ruff check .

test: test-go test-py

test-go:
	cd $(GO_DIR) && go test ./...

test-py:
	cd $(PY_DIR) && uv run pytest

# Cross-language round-trip (docs/BACKEND_BUILD_STEPS.md Step 7 / M0 exit).
# Needs Docker (spins a real Redis container) and `uv` on PATH (launches the
# Python echo agent as a subprocess) — kept out of the default `test` target
# since it's slower and has more environmental dependencies than a unit test.
test-integration:
	cd $(GO_DIR) && go test -tags=integration ./... -run TestRoundTrip -v

build: build-go

build-go:
	cd $(GO_DIR) && go build -o bin/api ./cmd/api

up:
	docker compose up -d
down:
	docker compose down
