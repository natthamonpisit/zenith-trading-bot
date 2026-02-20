import pandas as pd
import streamlit as st

from .utils import to_local_time


def _to_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def render_order_plan_page(db):
    st.markdown("### 📐 Order Plan Monitor")
    st.caption("Track planned entries, TP ladder progression, and execution lifecycle.")

    try:
        plans_res = db.table("order_plans").select("*").order("created_at", desc=True).limit(400).execute()
        plan_rows = plans_res.data or []
    except Exception as e:
        st.warning(f"Order plan table unavailable or query failed: {e}")
        st.info("Run Phase 2 migration before using this monitor.")
        return

    if not plan_rows:
        st.info("No order plans found yet.")
        return

    df = pd.DataFrame(plan_rows)
    df["symbol"] = df["symbol"].fillna("UNKNOWN")
    df["status"] = df["status"].fillna("UNKNOWN").str.upper()
    df["side"] = df["side"].fillna("UNKNOWN").str.upper()
    df["timeframe"] = df["timeframe"].fillna("-")
    df["created_time"] = df["created_at"].apply(lambda x: to_local_time(x, "%Y-%m-%d %H:%M:%S"))

    numeric_cols = ["entry_price", "stop_loss", "take_profit_1", "take_profit_2", "risk_per_unit", "tp1_partial_pct"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_float)
        else:
            df[col] = 0.0

    m1, m2, m3, m4 = st.columns(4)
    total = len(df)
    active = int(df["status"].isin(["ACTIVE", "PLANNED", "PARTIALLY_FILLED"]).sum())
    closed = int(df["status"].isin(["CLOSED"]).sum())
    failed = int(df["status"].isin(["FAILED", "CANCELLED"]).sum())
    m1.metric("Total Plans", total)
    m2.metric("Active/Planned", active)
    m3.metric("Closed", closed)
    m4.metric("Failed/Cancelled", failed)

    f1, f2, f3, f4 = st.columns(4)
    symbols = ["All"] + sorted(df["symbol"].dropna().unique().tolist())
    statuses = ["All"] + sorted(df["status"].dropna().unique().tolist())
    sides = ["All"] + sorted(df["side"].dropna().unique().tolist())
    tfs = ["All"] + sorted(df["timeframe"].dropna().unique().tolist())

    symbol_filter = f1.selectbox("Symbol", symbols)
    status_filter = f2.selectbox("Status", statuses)
    side_filter = f3.selectbox("Side", sides)
    tf_filter = f4.selectbox("Timeframe", tfs)

    filtered = df.copy()
    if symbol_filter != "All":
        filtered = filtered[filtered["symbol"] == symbol_filter]
    if status_filter != "All":
        filtered = filtered[filtered["status"] == status_filter]
    if side_filter != "All":
        filtered = filtered[filtered["side"] == side_filter]
    if tf_filter != "All":
        filtered = filtered[filtered["timeframe"] == tf_filter]

    if filtered.empty:
        st.warning("No plans match selected filters.")
    else:
        display_cols = [
            "created_time",
            "symbol",
            "side",
            "timeframe",
            "status",
            "entry_price",
            "stop_loss",
            "take_profit_1",
            "take_profit_2",
            "tp1_partial_pct",
            "risk_per_unit",
        ]
        st.dataframe(
            filtered[display_cols].rename(
                columns={
                    "created_time": "Created",
                    "symbol": "Symbol",
                    "side": "Side",
                    "timeframe": "TF",
                    "status": "Status",
                    "entry_price": "Entry",
                    "stop_loss": "SL",
                    "take_profit_1": "TP1",
                    "take_profit_2": "TP2",
                    "tp1_partial_pct": "TP1 Partial %",
                    "risk_per_unit": "Risk/Unit",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.markdown("#### 🔗 Open Positions Linked to Plan")
    try:
        pos_rows = (
            db.table("positions")
            .select("id,asset_id,entry_avg,quantity,is_sim,is_open,order_plan_id,tp1_hit,break_even_armed,current_stop_loss,take_profit_1,take_profit_2,assets(symbol)")
            .eq("is_open", True)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
            .data
            or []
        )
    except Exception as e:
        st.warning(f"Could not load open positions: {e}")
        return

    if not pos_rows:
        st.info("No open positions.")
        return

    p_df = pd.DataFrame(pos_rows)
    p_df["symbol"] = p_df["assets"].apply(lambda x: x.get("symbol") if isinstance(x, dict) else "UNKNOWN")
    p_df["mode"] = p_df["is_sim"].apply(lambda x: "PAPER" if bool(x) else "LIVE")
    p_df["entry_avg"] = p_df["entry_avg"].apply(_to_float)
    p_df["quantity"] = p_df["quantity"].apply(_to_float)
    p_df["current_stop_loss"] = p_df["current_stop_loss"].apply(_to_float)
    p_df["take_profit_1"] = p_df["take_profit_1"].apply(_to_float)
    p_df["take_profit_2"] = p_df["take_profit_2"].apply(_to_float)

    st.dataframe(
        p_df[
            [
                "symbol",
                "mode",
                "order_plan_id",
                "entry_avg",
                "quantity",
                "current_stop_loss",
                "take_profit_1",
                "take_profit_2",
                "tp1_hit",
                "break_even_armed",
            ]
        ].rename(
            columns={
                "symbol": "Symbol",
                "mode": "Mode",
                "order_plan_id": "Order Plan ID",
                "entry_avg": "Entry",
                "quantity": "Qty",
                "current_stop_loss": "Current SL",
                "take_profit_1": "TP1",
                "take_profit_2": "TP2",
                "tp1_hit": "TP1 Hit",
                "break_even_armed": "Breakeven Armed",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
