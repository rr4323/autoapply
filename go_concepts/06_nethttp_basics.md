# `net/http` Basics

## What it is

Go's standard library HTTP server/client, built entirely around the `http.Handler` interface from [04_interfaces.md](04_interfaces.md). `chi` (our router) is a thin layer on top of this — it doesn't replace the handler signature, it adds routing/middleware/URL params around it.

## Verified example — a real running server

```go
func main() {
	http.HandleFunc("/ping", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "pong")
	})
	http.ListenAndServe(":8099", nil)
}
```
```
$ go run server.go &
$ curl http://localhost:8099/ping
pong
```

## The handler signature — you'll write this shape constantly

```go
func(w http.ResponseWriter, r *http.Request)
```
- **`w http.ResponseWriter`** — you *write into* this (headers, status code, body) rather than `return`-ing a value. E.g. `w.WriteHeader(http.StatusServiceUnavailable)` then `w.Write(body)`, or `json.NewEncoder(w).Encode(v)` for JSON.
- **`r *http.Request`** — everything about the incoming request: `r.Method`, `r.URL`, `r.Header`, `r.Body`, and (with `chi`) URL params via `chi.URLParam(r, "id")`.

`http.HandleFunc` is an *adapter*: it takes a plain function with this exact signature and wraps it so it satisfies `http.Handler` (which technically wants a `ServeHTTP(w, r)` method, not a bare function) — you rarely need to think about this distinction day to day, but it's why the signature has to match exactly.

## Standard use case

Every endpoint in `docs/API_REFERENCE.md` / `backend/api/openapi.yaml` — `GET /healthz`, `GET /readyz`, `POST /api/applications`, all of it — is a function with this exact shape, registered on a `chi.Router` instead of the bare stdlib mux, but the signature never changes.
