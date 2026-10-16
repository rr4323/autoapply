# Go API image (docs/BACKEND_BUILD_STEPS.md Step 45 — a cold `make up`
# needs a real image to run, not just `go run` from a dev shell).
FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/api ./cmd/api

# A plain, small base (not distroless) — the runtime needs migrations/
# and config/ available as real files on disk at the paths
# internal/config.Config's MigrationsPath/PolicyRulesPath resolve
# relative to the working directory, and alpine's shell is genuinely
# useful for debugging a container that won't come up cleanly.
FROM alpine:3.20
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /out/api ./api
COPY migrations ./migrations
COPY config ./config
EXPOSE 8080
ENTRYPOINT ["./api"]
