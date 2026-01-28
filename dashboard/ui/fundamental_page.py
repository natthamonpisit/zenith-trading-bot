import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from .utils import get_cfg

# CoinGecko API (free, no key required)
COINGECKO_API = "https://api.coingecko.com/api/v3"

def fetch_coingecko_data(symbol_base):
    """
    Fetch coin data from CoinGecko API.
    symbol_base: e.g., 'BTC' from 'BTC/USDT'
    """
    # Map common symbols to CoinGecko IDs
    symbol_map = {
        'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin',
        'SOL': 'solana', 'XRP': 'ripple', 'ADA': 'cardano',
        'DOGE': 'dogecoin', 'DOT': 'polkadot', 'MATIC': 'matic-network',
        'SHIB': 'shiba-inu', 'LTC': 'litecoin', 'AVAX': 'avalanche-2',
        'LINK': 'chainlink', 'UNI': 'uniswap', 'ATOM': 'cosmos',
        'XLM': 'stellar', 'ALGO': 'algorand', 'VET': 'vechain',
        'FIL': 'filecoin', 'NEAR': 'near', 'APT': 'aptos',
        'ARB': 'arbitrum', 'OP': 'optimism', 'INJ': 'injective-protocol',
        'SUI': 'sui', 'SEI': 'sei-network', 'TIA': 'celestia',
        'PEPE': 'pepe', 'WIF': 'dogwifcoin', 'BONK': 'bonk',
    }

    coin_id = symbol_map.get(symbol_base.upper(), symbol_base.lower())

    try:
        url = f"{COINGECKO_API}/coins/{coin_id}"
        params = {
            'localization': 'false',
            'tickers': 'false',
            'community_data': 'false',
            'developer_data': 'false'
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"CoinGecko fetch error for {symbol_base}: {e}")
    return None


def calculate_fundamental_score(data):
    """
    Calculate a fundamental score (0-10) based on CoinGecko data.
    Factors: market cap rank, volume, price change, community size
    """
    if not data:
        return 5, "No data available"

    score = 5.0  # Base score
    factors = []

    # 1. Market Cap Rank (max +2 points)
    rank = data.get('market_cap_rank', 999)
    if rank:
        if rank <= 10:
            score += 2
            factors.append(f"Top 10 by market cap (#{rank})")
        elif rank <= 50:
            score += 1.5
            factors.append(f"Top 50 by market cap (#{rank})")
        elif rank <= 100:
            score += 1
            factors.append(f"Top 100 by market cap (#{rank})")
        elif rank > 500:
            score -= 1
            factors.append(f"Low market cap rank (#{rank})")

    # 2. 24h Volume relative to market cap (liquidity indicator, max +1.5 points)
    market_data = data.get('market_data', {})
    volume_24h = market_data.get('total_volume', {}).get('usd', 0)
    market_cap = market_data.get('market_cap', {}).get('usd', 1)
    if market_cap > 0 and volume_24h > 0:
        vol_ratio = volume_24h / market_cap
        if vol_ratio > 0.2:
            score += 1.5
            factors.append("High liquidity (volume/mcap > 20%)")
        elif vol_ratio > 0.1:
            score += 1
            factors.append("Good liquidity (volume/mcap > 10%)")
        elif vol_ratio < 0.02:
            score -= 1
            factors.append("Low liquidity warning")

    # 3. Price momentum - 7d change (max +1 point)
    price_change_7d = market_data.get('price_change_percentage_7d', 0)
    if price_change_7d:
        if price_change_7d > 10:
            score += 1
            factors.append(f"Strong 7d momentum (+{price_change_7d:.1f}%)")
        elif price_change_7d < -20:
            score -= 0.5
            factors.append(f"Weak 7d performance ({price_change_7d:.1f}%)")

    # 4. All-time high proximity (max +0.5 points)
    ath = market_data.get('ath', {}).get('usd', 0)
    current = market_data.get('current_price', {}).get('usd', 0)
    if ath > 0 and current > 0:
        ath_ratio = current / ath
        if ath_ratio > 0.8:
            score += 0.5
            factors.append("Near all-time high")
        elif ath_ratio < 0.1:
            score -= 0.5
            factors.append("Far from ATH (>90% down)")

    # Clamp score between 0 and 10
    score = max(0, min(10, score))

    reasoning = "; ".join(factors) if factors else "Standard fundamentals"
    return round(score, 1), reasoning


def auto_classify(score):
    """
    Auto-classify coin based on score.
    Score >= 7: WHITELIST
    Score <= 3: BLACKLIST
    Otherwise: NEUTRAL
    """
    if score >= 7:
        return "WHITELIST"
    elif score <= 3:
        return "BLACKLIST"
    else:
        return "NEUTRAL"


def render_fundamental_page(db):
    st.title("🕵️ The Head Hunter Lab")
    st.caption("Manage your Coin Whitelist/Blacklist and Fundamental Scores")

    # Auto-fetch section
    with st.expander("🤖 Auto-Fetch & Score (CoinGecko)", expanded=False):
        st.markdown("Automatically fetch fundamental data and calculate scores using CoinGecko API (free).")

        af1, af2 = st.columns([3, 1])
        with af1:
            auto_symbol = st.text_input("Symbol to analyze (e.g. BTC, ETH, SOL)", key="auto_symbol").upper().strip()
        with af2:
            st.markdown("<br>", unsafe_allow_html=True)
            fetch_btn = st.button("🔍 Fetch & Score", use_container_width=True)

        if fetch_btn and auto_symbol:
            with st.spinner(f"Fetching data for {auto_symbol}..."):
                data = fetch_coingecko_data(auto_symbol)
                if data:
                    score, reasoning = calculate_fundamental_score(data)
                    status = auto_classify(score)

                    st.success(f"Data fetched for {data.get('name', auto_symbol)}")

                    # Display results
                    r1, r2, r3 = st.columns(3)
                    r1.metric("Fundamental Score", f"{score}/10")
                    r2.metric("Auto Classification", status)
                    r3.metric("Market Cap Rank", f"#{data.get('market_cap_rank', 'N/A')}")

                    # Market data
                    market_data = data.get('market_data', {})
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Current Price", f"${market_data.get('current_price', {}).get('usd', 0):,.4f}")
                    m2.metric("24h Volume", f"${market_data.get('total_volume', {}).get('usd', 0):,.0f}")
                    m3.metric("Market Cap", f"${market_data.get('market_cap', {}).get('usd', 0):,.0f}")

                    st.info(f"**Scoring Factors:** {reasoning}")

                    # Save button
                    full_symbol = f"{auto_symbol}/USDT"
                    if st.button(f"💾 Save {full_symbol} to Database", key="save_auto"):
                        try:
                            db.table("fundamental_coins").upsert({
                                "symbol": full_symbol,
                                "status": status,
                                "manual_score": int(score),
                                "notes": f"Auto-scored: {reasoning}"
                            }).execute()
                            st.success(f"Saved {full_symbol} as {status} with score {score}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save error: {e}")
                else:
                    st.error(f"Could not fetch data for {auto_symbol}. Check if the symbol is correct.")

        # Bulk auto-score existing coins
        st.markdown("---")
        st.markdown("##### Bulk Auto-Score")
        if st.button("🔄 Re-score All Existing Coins", help="Fetch fresh data and update scores for all tracked coins"):
            try:
                existing = db.table("fundamental_coins").select("symbol").execute()
                if existing.data:
                    progress = st.progress(0)
                    total = len(existing.data)
                    updated = 0
                    for i, coin in enumerate(existing.data):
                        symbol = coin['symbol'].replace('/USDT', '').replace('/USD', '')
                        data = fetch_coingecko_data(symbol)
                        if data:
                            score, reasoning = calculate_fundamental_score(data)
                            status = auto_classify(score)
                            db.table("fundamental_coins").upsert({
                                "symbol": coin['symbol'],
                                "status": status,
                                "manual_score": int(score),
                                "notes": f"Auto-scored: {reasoning}"
                            }).execute()
                            updated += 1
                        progress.progress((i + 1) / total)
                    st.success(f"Updated {updated}/{total} coins!")
                    st.rerun()
                else:
                    st.info("No coins in database to re-score.")
            except Exception as e:
                st.error(f"Bulk score error: {e}")

    # Manual Add/Update section
    with st.expander("➕ Manual Add / Update Coin", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            symbol = st.text_input("Symbol (e.g. BTC/USDT)", key="manual_symbol").upper().strip()
        with c2:
            status = st.selectbox("Status", ["WHITELIST", "BLACKLIST", "NEUTRAL"])
        with c3:
            score = st.slider("Fundamental Score (0-10)", 0, 10, 5)

        notes = st.text_area("Notes", placeholder="Why this coin?")

        if st.button("Save to Database", key="save_manual"):
            if symbol:
                try:
                    db.table("fundamental_coins").upsert({
                        "symbol": symbol,
                        "status": status,
                        "manual_score": score,
                        "notes": notes
                    }).execute()
                    st.success(f"Saved {symbol}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter a symbol")

    st.markdown("---")

    # 2. View Tables
    try:
        # Fetch all
        rows = db.table("fundamental_coins").select("*").execute()
        if rows.data:
            df = pd.DataFrame(rows.data)

            # Summary Metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Whitelisted", len(df[df['status'] == 'WHITELIST']))
            c2.metric("Blacklisted", len(df[df['status'] == 'BLACKLIST']))
            c3.metric("Neutral", len(df[df['status'] == 'NEUTRAL']))
            c4.metric("Total Tracked", len(df))

            # P&L Correlation section
            with st.expander("📊 Performance by Classification", expanded=False):
                st.markdown("See how your whitelist/blacklist classifications correlate with actual trading P&L.")
                try:
                    # Get closed positions with P&L
                    closed = db.table("positions").select("*, assets(symbol)").eq("is_open", False).execute()
                    if closed.data:
                        # Build symbol -> status map
                        fund_map = {r['symbol']: r['status'] for r in rows.data}

                        # Categorize P&L by fundamental status
                        pnl_by_status = {'WHITELIST': [], 'BLACKLIST': [], 'NEUTRAL': [], 'UNTRACKED': []}
                        for pos in closed.data:
                            symbol = pos['assets']['symbol'] if pos.get('assets') else None
                            pnl = float(pos['pnl']) if pos.get('pnl') else 0
                            if symbol:
                                status = fund_map.get(symbol, 'UNTRACKED')
                                pnl_by_status[status].append(pnl)

                        # Display stats
                        pc1, pc2, pc3, pc4 = st.columns(4)
                        for col, status in zip([pc1, pc2, pc3, pc4], ['WHITELIST', 'BLACKLIST', 'NEUTRAL', 'UNTRACKED']):
                            pnls = pnl_by_status[status]
                            if pnls:
                                total = sum(pnls)
                                color = "#00FF94" if total >= 0 else "#FF4B4B"
                                col.metric(
                                    status,
                                    f"${total:,.2f}",
                                    f"{len(pnls)} trades"
                                )
                            else:
                                col.metric(status, "$0.00", "0 trades")
                    else:
                        st.info("No closed trades yet to analyze.")
                except Exception as e:
                    st.warning(f"Could not load P&L correlation: {e}")

            st.subheader("📋 Coin Database")

            # Filter View
            filter_status = st.radio("Filter:", ["ALL", "WHITELIST", "BLACKLIST", "NEUTRAL"], horizontal=True, key="filter_status")

            filtered_df = df.copy()
            if filter_status != "ALL":
                filtered_df = filtered_df[filtered_df['status'] == filter_status]

            # Sort by score descending
            filtered_df = filtered_df.sort_values('manual_score', ascending=False)

            st.dataframe(
                filtered_df,
                column_config={
                    "symbol": "Symbol",
                    "status": st.column_config.TextColumn("Status", help="WHITELIST=Trade, BLACKLIST=Avoid, NEUTRAL=Default"),
                    "manual_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%d"),
                    "notes": st.column_config.TextColumn("Notes", width="large"),
                    "updated_at": st.column_config.DatetimeColumn("Last Updated", format="YYYY-MM-DD HH:mm")
                },
                use_container_width=True,
                hide_index=True
            )

            # Delete coin option
            with st.expander("🗑️ Remove Coin", expanded=False):
                del_symbol = st.selectbox("Select coin to remove", df['symbol'].tolist())
                if st.button("Delete", type="secondary"):
                    try:
                        db.table("fundamental_coins").delete().eq("symbol", del_symbol).execute()
                        st.success(f"Deleted {del_symbol}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete error: {e}")
        else:
            st.info("No fundamental data found. Add some coins using the forms above!")

    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.info("💡 Hint: Did you run the 'fundamental_coins.sql' migration?")
