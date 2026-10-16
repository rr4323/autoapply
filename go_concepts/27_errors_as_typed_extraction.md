# `errors.As` — Pulling a Typed Error Back Out of a Wrapped Chain

## What it is

`05_error_handling.md` covered `fmt.Errorf("...: %w", err)` for *wrapping* an error with context. `errors.As` is the other half: given a wrapped chain, recover a specific concrete error type from somewhere inside it, so you can branch on fields that only *that* type has (an error code, a status, a field name) — not just its string message. It's different from `errors.Is`, which only checks "is this (or something it wraps) equal to this specific sentinel value" — `errors.As` asks "is there a value of *this type* anywhere in the chain," and hands it to you if so.

## Verified example

```go
type PgError struct {
	Code    string
	Message string
}
func (e *PgError) Error() string {
	return fmt.Sprintf("pg error %s: %s", e.Code, e.Message)
}

func insertUser(email string) error {
	if email == "taken@example.com" {
		return fmt.Errorf("insert failed: %w", &PgError{Code: "23505", Message: "duplicate key value violates unique constraint"})
	}
	return nil
}

err := insertUser("taken@example.com")
fmt.Println("raw error:", err)

var pgErr *PgError
if errors.As(err, &pgErr) {
	fmt.Println("unwrapped code:", pgErr.Code)
	if pgErr.Code == "23505" {
		fmt.Println("-> this is a duplicate-email conflict, not a generic 500")
	}
}

genericErr := errors.New("something else broke")
fmt.Println("errors.As on unrelated error:", errors.As(genericErr, &pgErr))
```
```
raw error: insert failed: pg error 23505: duplicate key value violates unique constraint
unwrapped code: 23505
-> this is a duplicate-email conflict, not a generic 500
errors.As on unrelated error: false
```

## The shape you always write: a pointer-to-pointer

`errors.As(err, &pgErr)` — `pgErr` is already `*PgError`, and you pass `&pgErr` (a `**PgError`) because `errors.As` needs to *write into* your variable when it finds a match, the same reason `json.Unmarshal` takes a pointer. Forgetting the `&` is a compile error (`errors.As`'s second argument must be a non-nil pointer), not a silent bug — the compiler catches this one for you.

## Standard use case

`internal/handlers/auth.go`'s `Signup`: Postgres returns a generic `error` when the `users.email` unique constraint is violated, but real `*pgconn.PgError` value is wrapped inside it by pgx. `errors.As(err, &pgErr)` recovers it, and checking `pgErr.Code == "23505"` (Postgres's `unique_violation` SQLSTATE) is what turns that into a `409 email_taken` response instead of a generic `500 internal_error` — the caller gets a response they can actually act on ("pick a different email") instead of an opaque failure.
