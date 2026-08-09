// Package bus implements the message envelope contract shared with the
// Python agent fleet — see ../../../contracts/envelope.md.
package bus

import (
	"errors"
	"fmt"
)

// Envelope is the fixed shape of every message on the Redis Streams bus
// (TDD.md §4.1). Payloads are references into working memory, never inline.
type Envelope struct {
	JobID      string `json:"job_id"`
	TraceID    string `json:"trace_id"`
	EventType  string `json:"event_type"`
	ProducedBy string `json:"produced_by"`
	Timestamp  string `json:"timestamp"`
	PayloadRef string `json:"payload_ref"`
}

// Validate rejects an envelope missing any required field. encoding/json
// has no built-in "required" concept (see go_concepts/11_json_marshaling.md),
// so this check has to be explicit.
func (e Envelope) Validate() error {
	switch {
	case e.JobID == "":
		return errors.New("envelope: job_id is required")
	case e.TraceID == "":
		return errors.New("envelope: trace_id is required")
	case e.EventType == "":
		return errors.New("envelope: event_type is required")
	case e.ProducedBy == "":
		return errors.New("envelope: produced_by is required")
	case e.Timestamp == "":
		return errors.New("envelope: timestamp is required")
	case e.PayloadRef == "":
		return errors.New("envelope: payload_ref is required")
	}
	return nil
}

// WorkingMemoryKey builds the working-memory key scheme from TDD.md §5:
// working_memory:job:{job_id}:{stage}.
func WorkingMemoryKey(jobID, stage string) string {
	return fmt.Sprintf("working_memory:job:%s:%s", jobID, stage)
}
