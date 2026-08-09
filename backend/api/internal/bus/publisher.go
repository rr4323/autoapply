package bus

import (
	"context"

	"github.com/redis/go-redis/v9"
)

// Publisher writes envelopes onto Redis Streams topics.
type Publisher struct {
	Redis *redis.Client
}

func NewPublisher(client *redis.Client) *Publisher {
	return &Publisher{Redis: client}
}

// Publish validates env, then XADDs it onto topic as a set of stream
// fields (one per envelope field, matching its json tag name) rather
// than a single marshaled JSON blob — see go_concepts/12_redis_streams_basics.md.
// It returns the Redis-assigned entry ID.
func (p *Publisher) Publish(ctx context.Context, topic string, env Envelope) (string, error) {
	if err := env.Validate(); err != nil {
		return "", err
	}

	id, err := p.Redis.XAdd(ctx, &redis.XAddArgs{
		Stream: topic,
		Values: map[string]interface{}{
			"job_id":      env.JobID,
			"trace_id":    env.TraceID,
			"event_type":  env.EventType,
			"produced_by": env.ProducedBy,
			"timestamp":   env.Timestamp,
			"payload_ref": env.PayloadRef,
		},
	}).Result()
	if err != nil {
		return "", err
	}

	return id, nil
}
