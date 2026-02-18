-- Migration: Seed config defaults for P5/P6/P7 rollout
-- Purpose: Enable tiering/hardening/cutover knobs in bot_config

INSERT INTO bot_config (key, value, description)
VALUES
  ('ENABLE_AI_TIERING', 'false', 'Enable P5 tiered AI pipeline'),
  ('DUAL_RUN_MODE', '"ENABLED"', 'P6 dual-run mode (ENABLED|DISABLED)'),
  ('PRIMARY_DASHBOARD', '"STREAMLIT"', 'P7 primary dashboard target (STREAMLIT|REACT)'),
  ('STREAMLIT_FALLBACK_ENABLED', 'true', 'Keep Streamlit fallback available during cutover'),
  ('CUTOVER_COMPLETED_AT', 'null', 'Timestamp when React cutover completed'),
  ('ALERT_HEARTBEAT_STALE_SEC', '120', 'Heartbeat stale threshold for alerts'),
  ('ALERT_ERROR_COUNT_THRESHOLD', '10', 'Recent ERROR count threshold for critical alert')
ON CONFLICT (key) DO NOTHING;
