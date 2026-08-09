# `os/exec` — Launching Another Process (and Another Language)

## What it is

`os/exec` runs external commands from Go — the mechanism behind the round-trip integration test's most unusual move: a Go test launching a real Python subprocess, waiting for it, and checking how it exited.

## Verified example

```go
cmd := exec.CommandContext(ctx, "uv", "run", "python", "-m", "agentos_agents.common.echo_agent")
cmd.Dir = agentsDir(t)               // working directory the command runs in
cmd.Env = append(os.Environ(),        // inherit the parent's env, plus overrides
	"REDIS_ADDR="+addr,
	"BUS_TOPIC="+TopicJDDiscovered,
	"ECHO_MAX_MESSAGES=1",
	"ECHO_TIMEOUT_SECONDS=20",
)

output, err := cmd.CombinedOutput()   // runs it, blocks until it exits
t.Logf("python echo agent output:\n%s", output)
if err != nil {
	t.Fatalf("python echo agent failed: %v", err)
}
```
Real captured output from the actual run:
```
ECHO_RECEIVED 1786296526586-0 job_id=b7e6c2b4-3f1a-4c9e-9d2a-1a2b3c4d5e6f
ECHO_SUCCESS received=1
```

## Reading the pieces

- **`exec.CommandContext(ctx, name, args...)`** — like `exec.Command`, but tied to a `context.Context` ([go_concepts/07_context.md](07_context.md)): if `ctx` is cancelled or times out, the subprocess gets killed automatically. This is why the test wraps everything in a 60-second `context.WithTimeout` — a hung Python process can't hang the test forever.
- **`cmd.Dir`** — the subprocess's working directory. Needed here because `uv run` has to execute from inside `backend/agents/` to find its `pyproject.toml`/virtual environment; the Go test process itself is running from `backend/api/`.
- **`cmd.Env = append(os.Environ(), ...)`** — the subprocess's environment variables. Starting from `os.Environ()` (the current process's own env — so `PATH`, etc. are inherited and `uv`/`python` can still be found) and appending overrides, rather than replacing the environment wholesale.
- **`cmd.CombinedOutput()`** — runs the command, blocks until it exits, and returns stdout+stderr merged together plus an error if the exit code was non-zero. There's also `cmd.Output()` (stdout only) and `cmd.Run()` (discards output entirely) for when you don't need to inspect what was printed.

## The "don't just trust the subprocess" principle

The test doesn't stop at checking the Python process's exit code — it makes an **independent** check afterward, straight against Redis:
```go
pending, err := client.XPending(ctx, TopicJDDiscovered, "roundtrip-group").Result()
if pending.Count != 0 {
	t.Fatalf("expected 0 pending entries after python ack, got %d", pending.Count)
}
```
A subprocess claiming success (exit code 0) and the message actually being acked in Redis are two different facts. Checking both is what makes this a real round-trip proof rather than "the Python script printed a happy message."

## Standard use case

Any test (or tool) that needs to orchestrate across language boundaries where the message bus itself is the only real integration point — exactly `TDD.md` §4.5's claim that Go and Python "coordinate purely through published events," now verified by an actual test that launches both sides for real.
