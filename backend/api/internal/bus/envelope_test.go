package bus

import (
	"encoding/json"
	"os"
	"testing"
)

func sampleEnvelope() Envelope {
	return Envelope{
		JobID:      "b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f",
		TraceID:    "f1e2d3c4-b5a6-4978-8a1b-2c3d4e5f6789",
		EventType:  "jd.parsed",
		ProducedBy: "scraper-agent",
		Timestamp:  "2026-08-09T14:00:00Z",
		PayloadRef: "working_memory:job:b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f:jd_parsed",
	}
}

func TestEnvelope_RoundTrip(t *testing.T) {
	original := sampleEnvelope()

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	var decoded Envelope
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if decoded != original {
		t.Fatalf("round trip mismatch: got %+v, want %+v", decoded, original)
	}
}

func TestEnvelope_Validate_MissingJobID(t *testing.T) {
	e := sampleEnvelope()
	e.JobID = ""

	if err := e.Validate(); err == nil {
		t.Fatal("expected error for missing job_id, got nil")
	}
}

func TestEnvelope_Validate_MissingTraceID(t *testing.T) {
	e := sampleEnvelope()
	e.TraceID = ""

	if err := e.Validate(); err == nil {
		t.Fatal("expected error for missing trace_id, got nil")
	}
}

func TestEnvelope_Validate_Clean(t *testing.T) {
	if err := sampleEnvelope().Validate(); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestEnvelope_GoldenFixture(t *testing.T) {
	data, err := os.ReadFile("../../../contracts/testdata/envelope_golden.json")
	if err != nil {
		t.Fatalf("failed to read golden fixture: %v", err)
	}

	var decoded Envelope
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal golden fixture: %v", err)
	}

	want := sampleEnvelope()
	if decoded != want {
		t.Fatalf("golden fixture mismatch: got %+v, want %+v", decoded, want)
	}

	if err := decoded.Validate(); err != nil {
		t.Fatalf("golden fixture should validate cleanly, got: %v", err)
	}
}

func TestWorkingMemoryKey(t *testing.T) {
	got := WorkingMemoryKey("b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f", "jd_parsed")
	want := "working_memory:job:b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f:jd_parsed"

	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}
