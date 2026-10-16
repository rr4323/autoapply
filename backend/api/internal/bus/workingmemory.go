package bus

import (
	"context"
	"encoding/json"
	"time"

	"github.com/redis/go-redis/v9"
)

// WorkingMemory is the per-job scratchpad from TDD.md §5 — Redis, keyed by
// WorkingMemoryKey, TTL'd so it clears itself once a job's data is no
// longer needed. This is what an envelope's payload_ref actually points
// at; the envelope itself never carries the payload inline (§4.1).
type WorkingMemory struct {
	Redis *redis.Client
}

func NewWorkingMemory(client *redis.Client) *WorkingMemory {
	return &WorkingMemory{Redis: client}
}

// Set JSON-encodes value and stores it under key with the given TTL.
func (wm *WorkingMemory) Set(ctx context.Context, key string, value any, ttl time.Duration) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return wm.Redis.Set(ctx, key, data, ttl).Err()
}

// Get reads the raw JSON stored at key and decodes it into dest (a
// pointer, same convention as json.Unmarshal). Symmetric with Set —
// added when the first Go-side reader (internal/terminal.Consumer)
// needed to read a working-memory record a Python agent had written,
// not just write one for a Python agent to read.
func (wm *WorkingMemory) Get(ctx context.Context, key string, dest any) error {
	data, err := wm.Redis.Get(ctx, key).Bytes()
	if err != nil {
		return err
	}
	return json.Unmarshal(data, dest)
}
