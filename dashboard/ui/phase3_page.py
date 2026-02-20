import streamlit as st

from src.ops.phase3_metrics import snapshot_metrics
from src.roles.tuning_advisor import TuningAdvisor
from src.roles.walk_forward import WalkForwardEngine


def _get_cfg(db, key, default):
    try:
        res = db.table("bot_config").select("value").eq("key", key).limit(1).execute()
        if res.data:
            return str(res.data[0]["value"]).replace('"', "").strip()
    except Exception:
        pass
    return default


def _bool_cfg(db, key, default=False):
    raw = str(_get_cfg(db, key, "true" if default else "false")).lower()
    return raw in {"1", "true", "yes", "on"}


def render_phase3_page(db):
    st.markdown("### 🧪 Phase 3 Lab (Validation + Tuning)")
    st.caption("Walk-forward validation, tuning advisor governance, and explainability monitor.")

    with st.container(border=True):
        st.markdown("#### Feature Flags")
        c1, c2, c3 = st.columns(3)
        enable_wf = c1.checkbox(
            "Enable Walk Forward",
            value=_bool_cfg(db, "ENABLE_PHASE3_WALK_FORWARD", False),
        )
        enable_advisor = c2.checkbox(
            "Enable Tuning Advisor",
            value=_bool_cfg(db, "ENABLE_TUNING_ADVISOR", False),
        )
        enable_explain = c3.checkbox(
            "Enable Explainability",
            value=_bool_cfg(db, "ENABLE_EXPLAINABILITY_PHASE3", False),
        )
        c4, c5 = st.columns(2)
        min_sample_size = c4.number_input(
            "Phase3 Min Sample Size",
            min_value=10,
            max_value=5000,
            value=int(float(_get_cfg(db, "PHASE3_MIN_SAMPLE_SIZE", 50))),
            step=10,
        )
        max_dd = c5.number_input(
            "Phase3 Max Allowed Drawdown (%)",
            min_value=1.0,
            max_value=80.0,
            value=float(_get_cfg(db, "PHASE3_MAX_ALLOWED_DRAWDOWN", 20)),
            step=1.0,
        )

        if st.button("💾 Save Phase 3 Flags", use_container_width=True):
            db.table("bot_config").upsert({"key": "ENABLE_PHASE3_WALK_FORWARD", "value": str(enable_wf).lower()}).execute()
            db.table("bot_config").upsert({"key": "ENABLE_TUNING_ADVISOR", "value": str(enable_advisor).lower()}).execute()
            db.table("bot_config").upsert({"key": "ENABLE_EXPLAINABILITY_PHASE3", "value": str(enable_explain).lower()}).execute()
            db.table("bot_config").upsert({"key": "PHASE3_MIN_SAMPLE_SIZE", "value": str(min_sample_size)}).execute()
            db.table("bot_config").upsert({"key": "PHASE3_MAX_ALLOWED_DRAWDOWN", "value": str(max_dd)}).execute()
            st.success("Phase 3 config saved.")

    with st.container(border=True):
        st.markdown("#### Walk-Forward Runner")
        rc1, rc2, rc3, rc4 = st.columns(4)
        run_id = rc1.text_input("Run ID (optional)", value="")
        timeframe = rc2.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
        fold_count = rc3.number_input("Fold Count", min_value=1, max_value=20, value=5, step=1)
        row_limit = rc4.number_input("Row Limit", min_value=50, max_value=5000, value=3000, step=50)

        if st.button("▶️ Run Walk-Forward Validation", use_container_width=True):
            engine = WalkForwardEngine(db=db)
            result = engine.run_validation(
                run_id=run_id or None,
                timeframe=timeframe,
                dataset_scope="GLOBAL",
                fold_count=int(fold_count),
                min_sample_size=int(min_sample_size),
                row_limit=int(row_limit),
            )
            if result.get("ok"):
                st.success(f"Walk-forward completed: {result.get('phase3_run_key')}")
                st.json(result.get("summary"))
            else:
                st.error(f"Walk-forward failed: {result.get('error')}")

        runs = (
            db.table("walk_forward_runs")
            .select("id,phase3_run_key,status,sample_size,fold_count,metrics_json,created_at,completed_at")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
            or []
        )
        if runs:
            st.dataframe(runs, use_container_width=True, hide_index=True)
        else:
            st.info("No walk-forward runs yet.")

        run_options = [row["id"] for row in runs if row.get("id")]
        selected_run_id = (
            st.selectbox("Selected Walk-Forward Run ID", options=run_options, index=0)
            if run_options
            else None
        )
        if selected_run_id:
            folds = (
                db.table("walk_forward_fold_results")
                .select("fold_index,train_from,train_to,test_from,test_to,sample_size,metrics_json,created_at")
                .eq("walk_forward_run_id", selected_run_id)
                .order("fold_index", desc=False)
                .limit(300)
                .execute()
                .data
                or []
            )
            st.markdown("##### Fold Details")
            st.dataframe(folds, use_container_width=True, hide_index=True)

    with st.container(border=True):
        st.markdown("#### Tuning Advisor Governance")
        advisor = TuningAdvisor(db=db)
        t1, t2, t3 = st.columns(3)

        run_rows = (
            db.table("walk_forward_runs")
            .select("id,phase3_run_key,status,created_at")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
            or []
        )
        run_ids = [row["id"] for row in run_rows if row.get("id")]
        selected_run_for_proposal = (
            t1.selectbox(
                "Run for Proposal",
                options=run_ids,
                index=0,
                key="phase3_run_for_proposal",
            )
            if run_ids
            else None
        )
        proposal_actor = t2.text_input("Proposal Actor", value="AI_ADVISOR")

        if t3.button("🧠 Generate Proposal", use_container_width=True, disabled=not selected_run_for_proposal):
            payload = advisor.create_proposal_for_walk_forward_run(
                walk_forward_run_id=selected_run_for_proposal,
                proposed_by=proposal_actor,
            )
            if payload.get("ok"):
                st.success(f"Proposal created: {payload.get('tuning_proposal_id')} ({payload.get('status')})")
                st.json(payload.get("proposal_payload"))
            else:
                st.error(f"Proposal failed: {payload.get('error')}")

        proposals = (
            db.table("tuning_proposals")
            .select("id,walk_forward_run_id,status,proposed_by,notes,created_at")
            .order("created_at", desc=True)
            .limit(200)
            .execute()
            .data
            or []
        )
        if proposals:
            st.dataframe(proposals, use_container_width=True, hide_index=True)
        else:
            st.info("No tuning proposals yet.")

        proposal_ids = [row["id"] for row in proposals if row.get("id")]
        selected_proposal_id = (
            st.selectbox(
                "Selected Proposal ID",
                options=proposal_ids,
                index=0,
                key="phase3_selected_proposal",
            )
            if proposal_ids
            else None
        )
        if selected_proposal_id:
            v1, v2, v3, v4 = st.columns(4)
            if v1.button("✅ Approve Manual", use_container_width=True):
                st.write(advisor.transition_proposal_status(selected_proposal_id, "APPROVED_MANUAL", actor="dashboard"))
            if v2.button("⛔ Reject", use_container_width=True):
                st.write(advisor.transition_proposal_status(selected_proposal_id, "REJECTED", actor="dashboard"))
            if v3.button("🧪 Apply Dry Run", use_container_width=True):
                st.write(advisor.apply_proposal(selected_proposal_id, actor="dashboard", dry_run=True))
            if v4.button("🚀 Apply Real", use_container_width=True):
                st.write(advisor.apply_proposal(selected_proposal_id, actor="dashboard", dry_run=False))

            validations = (
                db.table("tuning_proposal_validations")
                .select("validator,passed,severity,rule_code,message,details,created_at")
                .eq("tuning_proposal_id", selected_proposal_id)
                .order("created_at", desc=True)
                .limit(300)
                .execute()
                .data
                or []
            )
            st.markdown("##### Validation Details")
            st.dataframe(validations, use_container_width=True, hide_index=True)

    with st.container(border=True):
        st.markdown("#### Phase 3 Runtime Metrics")
        st.json(snapshot_metrics())
