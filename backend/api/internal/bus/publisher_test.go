package bus

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func newTestPublisher(t *testing.T) (*Publisher, *redis.Client) {
	t.Helper()

	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("failed to start miniredis: %v", err)
	}
	t.Cleanup(mr.Close)

	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	return NewPublisher(client), client
}

func TestPublisher_PublishShape(t *testing.T) {
	pub, client := newTestPublisher(t)
	ctx := context.Background()
	env := sampleEnvelope()

	if _, err := pub.Publish(ctx, TopicJDDiscovered, env); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	entries, err := client.XRange(ctx, TopicJDDiscovered, "-", "+").Result()
	if err != nil {
		t.Fatalf("xrange failed: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(entries))
	}

	got := entries[0].Values
	want := map[string]interface{}{
		"job_id":      env.JobID,
		"trace_id":    env.TraceID,
		"event_type":  env.EventType,
		"produced_by": env.ProducedBy,
		"timestamp":   env.Timestamp,
		"payload_ref": env.PayloadRef,
	}
	for field, wantVal := range want {
		if got[field] != wantVal {
			t.Errorf("field %q: got %v, want %v", field, got[field], wantVal)
		}
	}
}

func TestPublisher_KeyCorrectness(t *testing.T) {
	pub, client := newTestPublisher(t)
	ctx := context.Background()

	if _, err := pub.Publish(ctx, TopicJDDiscovered, sampleEnvelope()); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	entries, err := client.XRange(ctx, "jd.discovered", "-", "+").Result()
	if err != nil {
		t.Fatalf("xrange failed: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected entry on stream %q, got %d entries", "jd.discovered", len(entries))
	}

	otherEntries, err := client.XRange(ctx, TopicJDParsed, "-", "+").Result()
	if err != nil {
		t.Fatalf("xrange failed: %v", err)
	}
	if len(otherEntries) != 0 {
		t.Fatalf("expected no entries on %q, got %d", TopicJDParsed, len(otherEntries))
	}
}

func TestPublisher_ValidationShortCircuit(t *testing.T) {
	pub, client := newTestPublisher(t)
	ctx := context.Background()

	invalid := sampleEnvelope()
	invalid.JobID = ""

	if _, err := pub.Publish(ctx, TopicJDDiscovered, invalid); err == nil {
		t.Fatal("expected error for invalid envelope, got nil")
	}

	entries, err := client.XRange(ctx, TopicJDDiscovered, "-", "+").Result()
	if err != nil {
		t.Fatalf("xrange failed: %v", err)
	}
	if len(entries) != 0 {
		t.Fatalf("expected no entries reached redis, got %d", len(entries))
	}
}
