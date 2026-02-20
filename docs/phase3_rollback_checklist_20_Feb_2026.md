# Phase 3 Rollback Checklist (20 Feb 2026)

## Trigger Conditions
- API phase3 endpoints fail repeatedly
- phase3 metrics show abnormal query error growth
- operator cannot validate/trace decision path reliably
- any impact to main trading loop stability

## Immediate Actions (Safe Rollback)
1. Set all flags to OFF:
   - `ENABLE_PHASE3_WALK_FORWARD=false`
   - `ENABLE_TUNING_ADVISOR=false`
   - `ENABLE_EXPLAINABILITY_PHASE3=false`
2. Stop running walk-forward/tuning jobs.
3. Keep existing phase1/phase2 execution path unchanged.

## Verification After Rollback
- Dashboard still functional for non-phase3 pages.
- Replay endpoints from phase1/phase2 still healthy.
- Trading loop continues without phase3 dependency.
- `phase3_query_error_count` no longer increases.

## Data Policy
- Keep phase3 tables for audit unless explicit cleanup is requested.
- Do not drop tables during incident response unless necessary.

## Optional Cleanup (Only When Approved)
- Archive rows in:
  - `walk_forward_runs`
  - `walk_forward_fold_results`
  - `tuning_proposals`
  - `tuning_proposal_validations`
- Drop phase3 tables only in planned maintenance window.
