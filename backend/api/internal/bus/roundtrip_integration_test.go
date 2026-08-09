//go:build integration

// Package bus's round-trip integration test — the M0 exit criterion
// (docs/BACKEND_BUILD_STEPS.md Step 7): Go publishes onto a real
// containerized Redis, a real Python echo-agent subprocess consumes and
// acks it. Requires Docker and `uv` on PATH; run via `make test-integration`,
// not part of the default `go test ./...`.
package bus

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	tcredis "github.com/testcontainers/testcontainers-go/modules/redis"
)

func TestRoundTrip_GoPublishesPythonConsumes(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	container, err := tcredis.Run(ctx, "redis:7-alpine")
	if err != nil {
		t.Fatalf("failed to start redis container: %v", err)
	}
	t.Cleanup(func() {
		if err := container.Terminate(context.Background()); err != nil {
			t.Logf("failed to terminate container: %v", err)
		}
	})

	addr, err := container.PortEndpoint(ctx, "6379/tcp", "")
	if err != nil {
		t.Fatalf("failed to get redis endpoint: %v", err)
	}

	client := redis.NewClient(&redis.Options{Addr: addr})
	t.Cleanup(func() { _ = client.Close() })

	pub := NewPublisher(client)
	if _, err := pub.Publish(ctx, TopicJDDiscovered, sampleEnvelope()); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	cmd := exec.CommandContext(ctx, "uv", "run", "python", "-m", "agentos_agents.common.echo_agent")
	cmd.Dir = agentsDir(t)
	cmd.Env = append(os.Environ(),
		"REDIS_ADDR="+addr,
		"BUS_TOPIC="+TopicJDDiscovered,
		"BUS_GROUP=roundtrip-group",
		"BUS_CONSUMER_NAME=roundtrip-consumer-1",
		"ECHO_MAX_MESSAGES=1",
		"ECHO_TIMEOUT_SECONDS=20",
	)

	output, err := cmd.CombinedOutput()
	t.Logf("python echo agent output:\n%s", output)
	if err != nil {
		t.Fatalf("python echo agent failed: %v", err)
	}

	// Don't just trust the subprocess's exit code — independently verify
	// against Redis itself that the message was actually acked.
	pending, err := client.XPending(ctx, TopicJDDiscovered, "roundtrip-group").Result()
	if err != nil {
		t.Fatalf("xpending failed: %v", err)
	}
	if pending.Count != 0 {
		t.Fatalf("expected 0 pending entries after python ack, got %d", pending.Count)
	}
}

func agentsDir(t *testing.T) string {
	t.Helper()
	dir, err := filepath.Abs("../../../agents")
	if err != nil {
		t.Fatalf("failed to resolve agents dir: %v", err)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Fatalf("agents dir not found at %s: %v", dir, err)
	}
	return dir
}
