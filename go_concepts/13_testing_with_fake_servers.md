# Two Ways to Fake a Dependency: Interface Fakes vs. Protocol Fakes

## What it is

[08_testable_interfaces.md](08_testable_interfaces.md) covered faking a dependency by defining a narrow Go interface (`Pinger`) and swapping in a fake implementation of it. That's not the only way to test against something that isn't the real production Postgres/Redis — the other way is a **protocol-level fake**: a real server, speaking the real wire protocol, just running in-memory instead of as a separate process.

## `miniredis` — a real Redis server, in-process

```go
mr, err := miniredis.Run()
defer mr.Close()

client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
```
`miniredis.Run()` starts an actual TCP server implementing the Redis protocol, in the same process as your test, and hands you back its address. Then you construct a completely normal `*redis.Client` pointed at it — **the exact same client type your production code uses**, no custom interface, no adapter, no fake struct to write.

## Why this is the better choice specifically for the bus publisher

The `Pinger` pattern (interface fake) is right when you only care about *the outcome* — did `Ping` return an error or not. It's wrong here, because the whole point of testing `Publish` is to verify **the actual shape of what got written** — which stream, which fields, in what format. An interface fake (`type fakeStreamer struct{}`) would have to reimplement `XAdd` well enough to fake that shape back at you, which means you'd partly be testing your fake instead of your code. `miniredis` sidesteps this entirely: real `XADD` semantics, real `XRANGE` reads back what was actually written, using the actual `go-redis` client — so a passing test is real evidence the wire format is right, not just that some interface method got called.

## Rule of thumb

| Fake type | Use when | Example |
|---|---|---|
| Interface fake (`Pinger`) | You only care about success/failure of an operation, and reimplementing the real thing would be pure boilerplate | Health checks (Step 3) |
| Protocol fake (`miniredis`, `testcontainers`) | You need to verify the actual data/shape that got written or read, or the real client's behavior matters (encoding, ordering, expiry) | Bus publishing (Step 5), anything reading back what it wrote |

`testcontainers-go` (named in `docs/BACKEND_BUILD_STEPS.md`'s testing philosophy, `IMPLEMENTATION_PLAN.md` §0) is the same idea taken further — a real Postgres/Redis in an actual Docker container instead of an in-process fake — reserved for integration tests specifically because spinning up a container is slower than `miniredis`'s in-memory server. `miniredis` gets you real-protocol confidence at unit-test speed, which is exactly the tier Step 5 needs.

## Standard use case

Any test where "did the fake behave the same as the real dependency" is itself the thing worth doubting — stream/queue publishing, cache read-after-write behavior, anything with a wire format precise enough that a hand-rolled fake could quietly diverge from reality.
