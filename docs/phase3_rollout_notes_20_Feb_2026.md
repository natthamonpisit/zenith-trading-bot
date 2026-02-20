# Phase 3 Rollout Notes (20 Feb 2026)

## Scope
- Walk-forward validation engine
- Tuning advisor (manual approval required)
- Explainability and replay endpoints
- Phase3 metrics monitoring

## Prerequisites
- Migration applied:
  - `migrations/create_phase3_validation_tuning.sql`
- Config keys present in `bot_config`:
  - `ENABLE_PHASE3_WALK_FORWARD`
  - `ENABLE_TUNING_ADVISOR`
  - `ENABLE_EXPLAINABILITY_PHASE3`
  - `PHASE3_MIN_SAMPLE_SIZE`
  - `PHASE3_MAX_ALLOWED_DRAWDOWN`

## Rollout Steps
1. Keep all phase3 flags OFF (default state).
2. Enable `ENABLE_PHASE3_WALK_FORWARD=true` only.
3. Run walk-forward from `Phase 3 Lab` and verify fold metrics persisted.
4. Enable `ENABLE_EXPLAINABILITY_PHASE3=true` after replay checks pass.
5. Enable `ENABLE_TUNING_ADVISOR=true` after governance path validated:
   - `DRAFT -> VALIDATED -> APPROVED_MANUAL -> APPLIED`
6. Keep manual approval gate mandatory for proposal apply.

## Post-Deploy Checks
- API check:
  - `/api/replay/walk-forward-runs`
  - `/api/replay/tuning-proposals`
  - `/api/replay/score-decomposition`
  - `/api/replay/phase3-metrics`
- Dashboard check:
  - `Phase 3 Lab` page loads and displays runs/proposals/validations.
- Runtime safety check:
  - `phase3_query_error_count` remains stable.
  - `phase3_run_duration_ms.avg` is acceptable for dataset size.
  - Trading loop remains healthy (no stop in main execution loop).

## Acceptance
- Targeted phase3 tests pass.
- API regression tests pass for replay endpoints.
- No runtime degradation observed during normal trading cycle.
