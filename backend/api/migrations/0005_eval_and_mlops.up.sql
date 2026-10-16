-- TDD.md §8: eval_runs/eval_results (§10 evaluation), model_versions (thin
-- pointer into MLflow's Model Registry, §11.3), drift_checks (§11.2).

CREATE TABLE eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    sample_id TEXT
);
CREATE INDEX idx_eval_results_eval_run_id ON eval_results(eval_run_id);

-- Mirrors MLflow's own stage names exactly (TDD.md §11.3) — not
-- reinvented casing, since this value round-trips with the MLflow API.
CREATE TYPE model_stage AS ENUM ('None', 'Staging', 'Production', 'Archived');

CREATE TABLE model_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mlflow_model_name TEXT NOT NULL,
    mlflow_version TEXT NOT NULL,
    current_stage model_stage NOT NULL DEFAULT 'None',
    promoted_at TIMESTAMPTZ,
    promoted_by TEXT,
    UNIQUE (mlflow_model_name, mlflow_version)
);

CREATE TABLE drift_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    baseline_value DOUBLE PRECISION,
    breached BOOLEAN NOT NULL DEFAULT false,
    eval_run_id UUID REFERENCES eval_runs(id) ON DELETE SET NULL
);
CREATE INDEX idx_drift_checks_eval_run_id ON drift_checks(eval_run_id);
