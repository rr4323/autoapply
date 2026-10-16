package config

import "os"

type Config struct {
	Port                 string
	DatabaseURL          string
	RedisAddr            string
	InternalSharedSecret string
	PolicyRulesPath      string
	MigrationsPath       string
	JWTSigningKey        string
}

func Load() Config {
	return Config{
		Port:                 getEnv("PORT", "8080"),
		DatabaseURL:          getEnv("DATABASE_URL", "postgres://agentos:agentos_dev@localhost:5432/agentos?sslmode=disable"),
		RedisAddr:            getEnv("REDIS_ADDR", "localhost:6379"),
		InternalSharedSecret: getEnv("INTERNAL_SHARED_SECRET", "dev-internal-secret"),
		PolicyRulesPath:      getEnv("POLICY_RULES_PATH", "config/policy_rules.yaml"),
		MigrationsPath:       getEnv("MIGRATIONS_PATH", "migrations"),
		// Dev-only default. Production MUST set a real JWT_SIGNING_KEY via
		// Secret Manager (P4) — every issued token is forgeable otherwise.
		JWTSigningKey: getEnv("JWT_SIGNING_KEY", "dev-insecure-jwt-signing-key-change-me"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
