-- Migration: Phase 3 validation + tuning telemetry foundation
-- Purpose: Persist walk-forward runs/folds and tuning proposal validation trails.

CREATE TABLE IF NOT EXISTS walk_forward_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT,
    phase3_run_key TEXT NOT NULL,
    timeframe TEXT,
    dataset_scope TEXT,
    sample_size INT NOT NULL DEFAULT 0,
    fold_count INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_walk_forward_runs_phase3_run_key ON walk_forward_runs(phase3_run_key);
CREATE INDEX IF NOT EXISTS idx_walk_forward_runs_run_id ON walk_forward_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_walk_forward_runs_status_created ON walk_forward_runs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_walk_forward_runs_timeframe ON walk_forward_runs(timeframe);

CREATE TABLE IF NOT EXISTS walk_forward_fold_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    walk_forward_run_id UUID NOT NULL REFERENCES walk_forward_runs(id) ON DELETE CASCADE,
    fold_index INT NOT NULL,
    train_from TIMESTAMPTZ,
    train_to TIMESTAMPTZ,
    test_from TIMESTAMPTZ,
    test_to TIMESTAMPTZ,
    sample_size INT NOT NULL DEFAULT 0,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_walk_forward_folds_run_id ON walk_forward_fold_results(walk_forward_run_id);
CREATE INDEX IF NOT EXISTS idx_walk_forward_folds_fold_idx ON walk_forward_fold_results(walk_forward_run_id, fold_index);
CREATE INDEX IF NOT EXISTS idx_walk_forward_folds_created ON walk_forward_fold_results(created_at DESC);

CREATE TABLE IF NOT EXISTS tuning_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    walk_forward_run_id UUID REFERENCES walk_forward_runs(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (
        status IN ('DRAFT', 'VALIDATED', 'REJECTED', 'APPROVED_MANUAL', 'APPLIED', 'EXPIRED')
    ),
    proposed_by TEXT NOT NULL DEFAULT 'AI_ADVISOR',
    proposal_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_hash TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tuning_proposals_run_id ON tuning_proposals(walk_forward_run_id);
CREATE INDEX IF NOT EXISTS idx_tuning_proposals_status_created ON tuning_proposals(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tuning_proposals_created ON tuning_proposals(created_at DESC);

CREATE TABLE IF NOT EXISTS tuning_proposal_validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tuning_proposal_id UUID NOT NULL REFERENCES tuning_proposals(id) ON DELETE CASCADE,
    validator TEXT NOT NULL DEFAULT 'DETERMINISTIC_GUARD',
    passed BOOLEAN NOT NULL DEFAULT FALSE,
    severity TEXT NOT NULL DEFAULT 'ERROR' CHECK (severity IN ('INFO', 'WARN', 'ERROR')),
    rule_code TEXT,
    message TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tuning_validations_proposal_id ON tuning_proposal_validations(tuning_proposal_id);
CREATE INDEX IF NOT EXISTS idx_tuning_validations_passed ON tuning_proposal_validations(passed);
CREATE INDEX IF NOT EXISTS idx_tuning_validations_created ON tuning_proposal_validations(created_at DESC);

INSERT INTO bot_config (key, value, description)
VALUES
  ('ENABLE_PHASE3_WALK_FORWARD', 'false', 'Enable phase3 walk-forward validation pipeline'),
  ('ENABLE_TUNING_ADVISOR', 'false', 'Enable phase3 tuning advisor suggestions (manual approval required)'),
  ('ENABLE_EXPLAINABILITY_PHASE3', 'false', 'Enable phase3 explainability endpoints/panels'),
  ('PHASE3_MIN_SAMPLE_SIZE', '"50"', 'Minimum sample size required before tuning suggestion can be trusted'),
  ('PHASE3_MAX_ALLOWED_DRAWDOWN', '"20"', 'Maximum allowed drawdown (%) for tuning package validation')
ON CONFLICT (key) DO NOTHING;
