package bus

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

// Handler processes one message. Returning an error leaves the message
// unacked (redelivered later via reclaimStale) rather than acking a
// message the handler never actually finished — the same "don't lose
// data on a partial failure" instinct as the Python Consumer, but Go's
// explicit error return makes this a deliberate branch here instead of
// depending on an uncaught exception happening to behave the same way.
type Handler func(ctx context.Context, entryID string, env Envelope) error

// IsDuplicate is the idempotency hook (TDD.md §4.2) — nil means "never
// duplicate," matching the Python Consumer's default-False stub.
type IsDuplicate func(ctx context.Context, env Envelope) (bool, error)

// Consumer is the Go counterpart to
// backend/agents/src/agentos_agents/common/consumer.py's Consumer — same
// group-create/read/reclaim/ack loop mechanics, mirrored across the
// language boundary since the Policy Engine (Step 32) is the first Go
// component that needs to consume from the bus instead of only publishing.
type Consumer struct {
	Redis         *redis.Client
	Topic         string
	Group         string
	ConsumerName  string
	BlockDuration time.Duration
	ReclaimIdle   time.Duration
	Handle        Handler
	IsDuplicate   IsDuplicate
}

// Run blocks until ctx is canceled. Callers typically run this in its own
// goroutine and cancel ctx for graceful shutdown (the same
// signal.NotifyContext pattern main.go already uses).
func (c *Consumer) Run(ctx context.Context) error {
	if err := c.ensureGroup(ctx); err != nil {
		return fmt.Errorf("bus: failed to ensure consumer group: %w", err)
	}

	for {
		if ctx.Err() != nil {
			return nil
		}

		if err := c.reclaimStale(ctx); err != nil && ctx.Err() == nil {
			slog.Error("bus: reclaim stale messages failed", "topic", c.Topic, "error", err)
		}

		streams, err := c.Redis.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    c.Group,
			Consumer: c.ConsumerName,
			Streams:  []string{c.Topic, ">"},
			Count:    10,
			Block:    c.BlockDuration,
		}).Result()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			if errors.Is(err, redis.Nil) {
				continue // block timeout, no new messages — normal, not an error
			}
			slog.Error("bus: xreadgroup failed", "topic", c.Topic, "error", err)
			continue
		}

		for _, stream := range streams {
			for _, msg := range stream.Messages {
				c.process(ctx, msg)
			}
		}
	}
}

func (c *Consumer) ensureGroup(ctx context.Context) error {
	err := c.Redis.XGroupCreateMkStream(ctx, c.Topic, c.Group, "0").Err()
	if err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		return err
	}
	return nil
}

func (c *Consumer) reclaimStale(ctx context.Context) error {
	messages, _, err := c.Redis.XAutoClaim(ctx, &redis.XAutoClaimArgs{
		Stream:   c.Topic,
		Group:    c.Group,
		Consumer: c.ConsumerName,
		MinIdle:  c.ReclaimIdle,
		Start:    "0",
	}).Result()
	if err != nil {
		return err
	}
	for _, msg := range messages {
		c.process(ctx, msg)
	}
	return nil
}

func (c *Consumer) process(ctx context.Context, msg redis.XMessage) {
	env, err := envelopeFromValues(msg.Values)
	if err != nil {
		// A malformed envelope will never parse correctly on retry either
		// — acking it rather than leaving it stuck in the PEL forever is
		// the better failure mode until a dead-letter queue exists.
		slog.Error("bus: failed to parse envelope, acking and dropping", "entry_id", msg.ID, "error", err)
		c.ack(ctx, msg.ID)
		return
	}

	if c.IsDuplicate != nil {
		dup, err := c.IsDuplicate(ctx, env)
		if err != nil {
			slog.Error("bus: idempotency check failed", "entry_id", msg.ID, "error", err)
		} else if dup {
			c.ack(ctx, msg.ID)
			return
		}
	}

	if err := c.Handle(ctx, msg.ID, env); err != nil {
		slog.Error("bus: handler failed, message left unacked for redelivery", "entry_id", msg.ID, "error", err)
		return
	}

	c.ack(ctx, msg.ID)
}

func (c *Consumer) ack(ctx context.Context, entryID string) {
	if err := c.Redis.XAck(ctx, c.Topic, c.Group, entryID).Err(); err != nil {
		slog.Error("bus: failed to ack message", "entry_id", entryID, "error", err)
	}
}

func envelopeFromValues(values map[string]interface{}) (Envelope, error) {
	field := func(key string) (string, error) {
		v, ok := values[key]
		if !ok {
			return "", fmt.Errorf("envelope missing field %q", key)
		}
		s, ok := v.(string)
		if !ok {
			return "", fmt.Errorf("envelope field %q is not a string (got %T)", key, v)
		}
		return s, nil
	}

	jobID, err := field("job_id")
	if err != nil {
		return Envelope{}, err
	}
	traceID, err := field("trace_id")
	if err != nil {
		return Envelope{}, err
	}
	eventType, err := field("event_type")
	if err != nil {
		return Envelope{}, err
	}
	producedBy, err := field("produced_by")
	if err != nil {
		return Envelope{}, err
	}
	timestamp, err := field("timestamp")
	if err != nil {
		return Envelope{}, err
	}
	payloadRef, err := field("payload_ref")
	if err != nil {
		return Envelope{}, err
	}

	env := Envelope{
		JobID:      jobID,
		TraceID:    traceID,
		EventType:  eventType,
		ProducedBy: producedBy,
		Timestamp:  timestamp,
		PayloadRef: payloadRef,
	}
	if err := env.Validate(); err != nil {
		return Envelope{}, err
	}
	return env, nil
}
