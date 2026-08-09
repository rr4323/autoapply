package health

import (
	"context"
	"encoding/json"
	"net/http"
	"time"
)

// Pinger is the narrow interface health checks depend on. *pgxpool.Pool
// satisfies it directly; go-redis needs a small adapter (see main.go) since
// its Ping returns *redis.StatusCmd, not a bare error.
type Pinger interface {
	Ping(ctx context.Context) error
}

const pingTimeout = 2 * time.Second

type Checker struct {
	DB    Pinger
	Redis Pinger
}

func NewChecker(db, redis Pinger) *Checker {
	return &Checker{DB: db, Redis: redis}
}

func (c *Checker) Healthz(w http.ResponseWriter, r *http.Request) {
	writeStatus(w, http.StatusOK, "ok")
}

func (c *Checker) Readyz(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), pingTimeout)
	defer cancel()

	if err := c.DB.Ping(ctx); err != nil {
		writeStatus(w, http.StatusServiceUnavailable, "postgres unavailable: "+err.Error())
		return
	}
	if err := c.Redis.Ping(ctx); err != nil {
		writeStatus(w, http.StatusServiceUnavailable, "redis unavailable: "+err.Error())
		return
	}
	writeStatus(w, http.StatusOK, "ok")
}

func writeStatus(w http.ResponseWriter, code int, status string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"status": status})
}
