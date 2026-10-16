package bus

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func newTestConsumerClient(t *testing.T) *redis.Client {
	t.Helper()

	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("failed to start miniredis: %v", err)
	}
	t.Cleanup(mr.Close)

	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	return client
}

// recordingHandler collects every envelope it's called with, safely
// across goroutines (Run() executes on its own goroutine in every test
// here).
type recordingHandler struct {
	mu       sync.Mutex
	received []Envelope
}

func (r *recordingHandler) handle(_ context.Context, _ string, env Envelope) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.received = append(r.received, env)
	return nil
}

func (r *recordingHandler) count() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.received)
}

func runBriefly(t *testing.T, c *Consumer, d time.Duration) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- c.Run(ctx) }()

	time.Sleep(d)
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("Run returned error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Run did not exit after context cancellation")
	}
}

func TestConsumer_AckPath(t *testing.T) {
	client := newTestConsumerClient(t)
	ctx := context.Background()
	env := sampleEnvelope()
	if _, err := NewPublisher(client).Publish(ctx, "test.topic", env); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	handler := &recordingHandler{}
	consumer := &Consumer{
		Redis: client, Topic: "test.topic", Group: "test-group", ConsumerName: "c1",
		BlockDuration: 100 * time.Millisecond, Handle: handler.handle,
	}
	runBriefly(t, consumer, 300*time.Millisecond)

	if handler.count() != 1 {
		t.Fatalf("received %d messages, want 1", handler.count())
	}
	pending, err := client.XPending(ctx, "test.topic", "test-group").Result()
	if err != nil {
		t.Fatalf("xpending failed: %v", err)
	}
	if pending.Count != 0 {
		t.Fatalf("pending count = %d, want 0 (message should be acked)", pending.Count)
	}
}

func TestConsumer_RedeliveryPath(t *testing.T) {
	client := newTestConsumerClient(t)
	ctx := context.Background()
	env := sampleEnvelope()
	if _, err := NewPublisher(client).Publish(ctx, "test.topic", env); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	// Simulate a consumer that read the message and crashed before acking.
	if err := client.XGroupCreateMkStream(ctx, "test.topic", "test-group", "0").Err(); err != nil {
		t.Fatalf("group create failed: %v", err)
	}
	if _, err := client.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group: "test-group", Consumer: "crashed-consumer", Streams: []string{"test.topic", ">"}, Count: 10,
	}).Result(); err != nil {
		t.Fatalf("xreadgroup (crashed consumer) failed: %v", err)
	}
	pendingBefore, err := client.XPending(ctx, "test.topic", "test-group").Result()
	if err != nil {
		t.Fatalf("xpending failed: %v", err)
	}
	if pendingBefore.Count != 1 {
		t.Fatalf("pending count = %d, want 1", pendingBefore.Count)
	}

	handler := &recordingHandler{}
	consumer := &Consumer{
		Redis: client, Topic: "test.topic", Group: "test-group", ConsumerName: "c1",
		BlockDuration: 100 * time.Millisecond, ReclaimIdle: 0, // reclaim immediately
		Handle: handler.handle,
	}
	runBriefly(t, consumer, 300*time.Millisecond)

	if handler.count() != 1 {
		t.Fatalf("received %d messages, want 1 (reclaimed)", handler.count())
	}
	pendingAfter, err := client.XPending(ctx, "test.topic", "test-group").Result()
	if err != nil {
		t.Fatalf("xpending failed: %v", err)
	}
	if pendingAfter.Count != 0 {
		t.Fatalf("pending count after = %d, want 0", pendingAfter.Count)
	}
}

func TestConsumer_ShutdownMidLoop(t *testing.T) {
	client := newTestConsumerClient(t)
	handler := &recordingHandler{}
	consumer := &Consumer{
		Redis: client, Topic: "empty.topic", Group: "test-group", ConsumerName: "c1",
		BlockDuration: 300 * time.Millisecond, Handle: handler.handle,
	}

	start := time.Now()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- consumer.Run(ctx) }()

	time.Sleep(50 * time.Millisecond) // let it enter the blocking xreadgroup call
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("Run returned error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Run did not exit after context cancellation")
	}
	if elapsed := time.Since(start); elapsed >= time.Second {
		t.Fatalf("shutdown took %v, expected to be bounded by BlockDuration", elapsed)
	}
}

func TestConsumer_IdempotencyHookSkipsHandle(t *testing.T) {
	client := newTestConsumerClient(t)
	ctx := context.Background()
	env := sampleEnvelope()
	if _, err := NewPublisher(client).Publish(ctx, "test.topic", env); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	handler := &recordingHandler{}
	consumer := &Consumer{
		Redis: client, Topic: "test.topic", Group: "test-group", ConsumerName: "c1",
		BlockDuration: 100 * time.Millisecond, Handle: handler.handle,
		IsDuplicate: func(_ context.Context, _ Envelope) (bool, error) { return true, nil },
	}
	runBriefly(t, consumer, 300*time.Millisecond)

	if handler.count() != 0 {
		t.Fatalf("received %d messages, want 0 (duplicate should skip handle)", handler.count())
	}
	pending, err := client.XPending(ctx, "test.topic", "test-group").Result()
	if err != nil {
		t.Fatalf("xpending failed: %v", err)
	}
	if pending.Count != 0 {
		t.Fatalf("pending count = %d, want 0 (still acked despite being a duplicate)", pending.Count)
	}
}

func TestConsumer_HandlerErrorLeavesMessageUnacked(t *testing.T) {
	client := newTestConsumerClient(t)
	ctx := context.Background()
	env := sampleEnvelope()
	if _, err := NewPublisher(client).Publish(ctx, "test.topic", env); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	consumer := &Consumer{
		Redis: client, Topic: "test.topic", Group: "test-group", ConsumerName: "c1",
		BlockDuration: 100 * time.Millisecond,
		Handle: func(_ context.Context, _ string, _ Envelope) error {
			return errors.New("boom")
		},
	}
	runBriefly(t, consumer, 300*time.Millisecond)

	pending, err := client.XPending(ctx, "test.topic", "test-group").Result()
	if err != nil {
		t.Fatalf("xpending failed: %v", err)
	}
	if pending.Count != 1 {
		t.Fatalf("pending count = %d, want 1 (failed handler must not ack)", pending.Count)
	}
}
