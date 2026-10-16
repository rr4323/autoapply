.PHONY: lint lint-go lint-py lint-web test test-go test-py test-integration test-e2e build build-go build-web dev-web migrate-up migrate-down

GO_DIR := backend/api
PY_DIR := backend/agents
WEB_DIR := frontend
DB_URL ?= postgresql://agentos:agentos_dev@localhost:5432/agentos?sslmode=disable

lint: lint-go lint-py lint-web

lint-go:
	cd $(GO_DIR) && golangci-lint run ./...

lint-py:
	cd $(PY_DIR) && uv run ruff check .

lint-web:
	cd $(WEB_DIR) && npm run lint

test: test-go test-py

test-go:
	cd $(GO_DIR) && go test ./...

test-py:
	cd $(PY_DIR) && uv run pytest -m "not integration and not e2e"

# Cross-language round-trip (docs/BACKEND_BUILD_STEPS.md Step 7 / M0 exit)
# plus the Python-side Postgres/Redis-testcontainer suite (Step 21 onward).
# Needs Docker and `uv` on PATH — kept out of the default `test` target
# since it's slower and has more environmental dependencies than a unit test.
test-integration: test-integration-go test-integration-py

test-integration-go:
	cd $(GO_DIR) && go test -tags=integration ./... -v

test-integration-py:
	cd $(PY_DIR) && uv run pytest -m integration -v

# M6 exit (docs/BACKEND_BUILD_STEPS.md Step 45) — the 3-scenario backend
# E2E against the full docker-compose stack. Needs `make up` already
# running (this doesn't start it — a cold-start proof is `make up` then
# this, not one target doing both, so failures are attributable to one
# or the other).
test-e2e:
	cd $(PY_DIR) && uv run pytest -m e2e -v -s

build: build-go build-web

build-go:
	cd $(GO_DIR) && go build -o bin/api ./cmd/api

build-web:
	cd $(WEB_DIR) && npm run build

# Vite dev server against a locally running API (`make up`, or `go run`
# straight from backend/api) — proxies /api/* per vite.config.ts, so the
# frontend never needs CORS or a base-URL env var in dev.
dev-web:
	cd $(WEB_DIR) && npm run dev

up:
	docker compose up -d --build
down:
	docker compose down

migrate-up:
	migrate -path $(GO_DIR)/migrations -database "$(DB_URL)" up

migrate-down:
	migrate -path $(GO_DIR)/migrations -database "$(DB_URL)" down 1
