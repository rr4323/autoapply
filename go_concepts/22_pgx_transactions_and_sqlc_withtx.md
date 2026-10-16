# `pgx` Transactions + sqlc's `WithTx` — and the Limits of "Same Transaction"

## What it is

`pgx.Tx` is a database transaction: a group of writes that either all commit together or all roll back together. sqlc generates `(q *Queries) WithTx(tx pgx.Tx) *Queries` on every `Queries` struct — a second `*Queries` bound to the transaction instead of the pool, so the exact same generated query methods (`CreateApplication`, `AppendApplicationEvent`, ...) work identically whether you're inside a transaction or not.

## Verified example (from `backend/api/internal/handlers/applications.go`)

```go
tx, err := h.Pool.Begin(ctx)
if err != nil { /* ... */ }
defer func() { _ = tx.Rollback(ctx) }() // no-op once committed below

qtx := h.Queries.WithTx(tx)

app, err := qtx.CreateApplication(ctx, store.CreateApplicationParams{...})
// ...
_, err = qtx.AppendApplicationEvent(ctx, store.AppendApplicationEventParams{...})
// ...
if err := tx.Commit(ctx); err != nil { /* ... */ }
```
Both writes go through `qtx` (the transaction-bound `Queries`), so either both land or neither does — verified by the M1 exit integration test asserting exactly one `application_events` row exists for the application that was created.

## The `defer tx.Rollback(ctx)` idiom — verified, not assumed

```go
tx, _ := pool.Begin(ctx)
defer func() {
	err := tx.Rollback(ctx)
	fmt.Println("rollback after commit returned:", err)
}()
// ... tx.Commit(ctx) succeeds ...
```
```
commit succeeded
rollback after commit returned: tx is closed
```
Calling `Rollback` on an already-committed transaction doesn't undo the commit or panic — it just returns `pgx.ErrTxClosed`, safely discarded. This is *the* standard pgx pattern: `defer tx.Rollback(ctx)` immediately after `Begin`, unconditionally — if the function returns early on an error before `Commit` runs, the deferred rollback cleans up; if `Commit` already ran, the deferred rollback is a harmless no-op.

## The limit this pattern has: it only covers Postgres

`WithTx` gives atomicity **within Postgres** — the `applications` row and the `application_events` row. It does **not** extend to the Redis publish that happens afterward. A single transaction spanning two different systems (Postgres + Redis) needs infrastructure this project doesn't have (two-phase commit, or a transactional outbox table + a separate poller process) — genuinely more machinery than a Phase 1 single-user demo justifies.

The resulting design, in `applications.go`'s `Create` handler:
1. Postgres transaction commits first (the two Postgres writes are atomic together).
2. **Then** the bus publish happens, outside any transaction.
3. If the publish fails after a successful commit, that's logged as an operational problem (`slog.Error`) — the create has still genuinely succeeded, so the client still gets `202`, not an error for something that actually worked.

This is a deliberate, named tradeoff, not an oversight: "the two Postgres writes are atomic" is a real, achievable guarantee; "the Postgres writes and the Redis publish are atomic together" is not, without infrastructure this system doesn't build.

## Standard use case

Any handler that needs to write more than one related row and have both succeed or both fail together — `CreateApplication` + `AppendApplicationEvent` here, and the same shape will recur anywhere else in the codebase that pairs a primary write with its own audit-log row.
