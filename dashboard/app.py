import sys
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import os

# Streamlit Cloud exposes secrets via st.secrets, but settings.py reads os.getenv.
# Bridge them so Telegram works on Streamlit Cloud without breaking local .env usage.
if hasattr(st, "secrets"):
    for _key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        try:
            if _key in st.secrets and not os.getenv(_key):
                os.environ[_key] = str(st.secrets[_key])
        except Exception:
            pass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import risk_config, telegram_config
from config.universes import (
    US_CORE_UNIVERSE, US_HIGH_MOMENTUM_WATCHLIST,
    INDIA_NSE_CORE_UNIVERSE, INDIA_NSE_MOMENTUM_WATCHLIST
)
from risk.manager import RiskManager
from ml.regime import regime_classifier
from ml.features import compute_all_swing_features, compute_all_intraday_features
from engines.swing_engine import SwingEngine
from engines.intraday_engine import IntradayEngine
from alerts.telegram_bot import telegram_notifier
from data.provider import data_provider
from backtest.engine import backtest_engine
from engines.value_growth_engine import value_growth_engine
from nlp.news_analyzer import news_analyzer
from data.live_scrapers import live_scraper
from intelligence.macro_and_smart_money import macro_smart_money
from ledger.virtual_broker import virtual_broker
from intelligence.options_darkpool import options_analyzer

# Page layout configuration
st.set_page_config(
    page_title="AlphaSeeker AI | Stock Finder",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1E293B;
        border-radius: 10px;
        padding: 16px;
        border: 1px solid #334155;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------- SIDEBAR CONTROLS ----------------
st.sidebar.title("⚡ AlphaSeeker AI")
st.sidebar.caption("Dual-Engine Quantitative Stock Finder")

market_choice = st.sidebar.selectbox(
    "Target Market",
    ["US Equities (NYSE / NASDAQ)", "Indian Equities (NSE)"],
    index=0
)
is_us = "US" in market_choice
currency_symbol = "$" if is_us else "₹"
default_cap = 10000.0 if is_us else 200000.0

scan_engine_type = st.sidebar.radio(
    "Trading Timeframe",
    ["📈 Multi-Month Swing (Positional)", "⚡ Intraday Momentum (5-Min)"]
)
is_swing = "Swing" in scan_engine_type

universe_source = st.sidebar.selectbox(
    "📡 Stock Universe Source",
    [
        "🔥 Live Scraped: Most Active Movers (Today)",
        "🚀 Live Scraped: Top Day Gainers (Today)",
        "🌐 Live Scraped: S&P 500 / Nifty 50 Constituents",
        "⭐ Curated Momentum Watchlist"
    ],
    index=0
)

st.sidebar.divider()
st.sidebar.subheader("🛡️ Risk Parameters")

capital_input = st.sidebar.number_input(
    f"Portfolio Capital ({currency_symbol})",
    min_value=500.0,
    max_value=10_000_000.0,
    value=default_cap,
    step=1000.0
)

risk_pct_input = st.sidebar.slider(
    "Max Risk per Trade (%)",
    min_value=0.5,
    max_value=3.0,
    value=1.5,
    step=0.1
) / 100.0

min_rr_input = st.sidebar.slider(
    "Minimum Risk-to-Reward Ratio",
    min_value=1.5,
    max_value=4.0,
    value=2.0,
    step=0.5
)

# Initialize Risk and Strategy Engines
risk_mgr = RiskManager(total_capital=capital_input, max_risk_pct=risk_pct_input)
risk_mgr.min_rr = min_rr_input
swing_engine = SwingEngine(risk_manager=risk_mgr)
intraday_engine = IntradayEngine(risk_manager=risk_mgr)

st.sidebar.divider()
st.sidebar.subheader("📱 Telegram Alerts")
if telegram_config.enabled:
    st.sidebar.success("✅ Telegram Connected")
else:
    st.sidebar.info("ℹ️ Telegram disabled (Add tokens to .env to activate push alerts)")


# ---------------- MAIN CONTENT ----------------
market_code = "US" if is_us else "INDIA"
regime = regime_classifier.classify_market(market_code)

# Market Regime Banner
col_reg1, col_reg2, col_reg3, col_reg4 = st.columns([2, 1, 1, 2])
with col_reg1:
    status_color = "🟢" if regime.status == "TRENDING_BULLISH" else ("🔴" if regime.status == "TRENDING_BEARISH" else "🟡")
    st.markdown(f"### {status_color} Market Regime: `{regime.status}`")
    st.caption(f"Benchmark: **{regime.benchmark}** ({currency_symbol}{regime.current_price:,.2f})")
with col_reg2:
    st.metric("50-Day SMA", f"{currency_symbol}{regime.sma_50:,.2f}")
with col_reg3:
    st.metric("RSI (14)", f"{regime.rsi_14:.1f}")
with col_reg4:
    st.info(f"💡 **Macro Guidance:** {regime.guidance}")

st.divider()

# Tab Navigation: Screener vs Virtual Desk vs Backtester vs Undervalued Multi-Baggers vs Smart Money & Macro
tab_screener, tab_ledger, tab_backtest, tab_value, tab_macro = st.tabs([
    "🚀 Live Screener & Signal Radar",
    "💼 Virtual Portfolio & Active Desk",
    "🧪 Strategy Backtester & Simulator",
    "💎 Undervalued Growth & News Catalysts",
    "🏛️ Smart Money, Politician Trades & Macro Cycles"
])

with tab_screener:
    # Dynamic universe resolution from live scrapers
    if is_us:
        if "Most Active" in universe_source:
            selected_universe = live_scraper.scrape_us_most_actives(count=35)
        elif "Day Gainers" in universe_source:
            selected_universe = live_scraper.scrape_us_day_gainers(count=35)
        elif "Constituents" in universe_source:
            selected_universe = live_scraper.scrape_sp500_live()[:50]
        else:
            selected_universe = US_CORE_UNIVERSE if is_swing else US_HIGH_MOMENTUM_WATCHLIST
    else:
        if "Constituents" in universe_source or "Active" in universe_source:
            selected_universe = live_scraper.scrape_nifty50_live()
        else:
            selected_universe = INDIA_NSE_CORE_UNIVERSE if is_swing else INDIA_NSE_MOMENTUM_WATCHLIST

    st.write(f"Live Universe ({universe_source}): **{len(selected_universe)} stocks** (`{', '.join(selected_universe[:8])}...`)")

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        run_scan = st.button("🚀 Run AI Screener", type="primary", use_container_width=True)

    if run_scan or "last_results" not in st.session_state:
        with st.spinner("Analyzing multi-timeframe charts and calculating risk models..."):
            if is_swing:
                results = swing_engine.scan_universe(selected_universe)
            else:
                results = intraday_engine.scan_universe(selected_universe)
            st.session_state["last_results"] = results
            st.session_state["last_type"] = "SWING" if is_swing else "INTRADAY"

    results = st.session_state.get("last_results", [])

    if not results:
        st.warning("No setups met the criteria right now. Market may be consolidated or filtered out by strict R:R requirements.")
    else:
        st.success(f"Found **{len(results)} high-conviction trade setups** matching institutional risk criteria.")

        # Results Table
        table_data = []
        for c in results:
            t_row = {
                "Ticker": c.ticker,
                "Pattern": c.pattern,
                "AI Score": f"{c.confidence_score:.0f}%",
                "Price": f"{currency_symbol}{c.last_price:.2f}",
                "Stop Loss": f"{currency_symbol}{c.stop_loss:.2f}",
                "Target 1 (2R)": f"{currency_symbol}{c.target_1:.2f}",
                "Target 2 (3.5R)": f"{currency_symbol}{c.target_2:.2f}",
                "R:R": f"{c.ticket.risk_reward_ratio_t1:.1f} : 1",
                "Shares": c.ticket.recommended_shares,
                "Risk ($)": f"{currency_symbol}{c.ticket.dollar_risk_amount:.2f}",
                "RVOL": f"{c.rvol:.1f}x"
            }
            if getattr(c, "meta_label", None):
                t_row["ML Win Prob"] = f"{c.meta_label.win_probability:.1%}"
            if getattr(c, "confluence", None):
                t_row["Confluence"] = c.confluence.summary()
            if c.time_prediction:
                t_row["Timeline ETA"] = c.time_prediction.summary_badge()
            table_data.append(t_row)

        df_table = pd.DataFrame(table_data)
        st.dataframe(df_table, use_container_width=True)

        # Candidate Detail & Interactive Chart Viewer
        st.divider()
        st.subheader("🔍 Detailed Trade Ticket & Interactive Chart")

        candidate_tickers = [c.ticker for c in results]
        selected_candidate_ticker = st.selectbox("Select Candidate to Inspect", candidate_tickers)

        selected_c = next(c for c in results if c.ticker == selected_candidate_ticker)
        ticket = selected_c.ticket

        col_t1, col_t2, col_t3, col_t4, col_t5 = st.columns(5)
        col_t1.metric("Recommended Entry", f"{currency_symbol}{ticket.entry_price:.2f}")
        col_t2.metric("Stop Loss", f"{currency_symbol}{ticket.stop_loss:.2f}", delta=f"-{ticket.risk_per_share:.2f}", delta_color="inverse")
        col_t3.metric("Target 1 (2.0R)", f"{currency_symbol}{ticket.target_1:.2f}", delta=f"+{ticket.reward_per_share_t1:.2f}")
        col_t4.metric("Position Size", f"{ticket.recommended_shares} shares")
        col_t5.metric("Capital Required", f"{currency_symbol}{ticket.capital_required:,.2f}")

        # Upgrade B: ML Meta-Label Banner
        if getattr(selected_c, "meta_label", None):
            ml_meta = selected_c.meta_label
            badge = "🟢 HIGH CONVICTION" if ml_meta.confidence_tier == "HIGH_CONVICTION" else "🔵 APPROVED"
            edge_txt = f" | **Edge:** {', '.join(ml_meta.top_positive_factors)}" if ml_meta.top_positive_factors else ""
            st.info(f"🤖 **Quant ML Meta-Label (Upgrade B):** `{ml_meta.win_probability:.1%}` [{badge}]{edge_txt}")

        # Improvement G: Multi-Timeframe Confluence Banner
        if getattr(selected_c, "confluence", None):
            conf = selected_c.confluence
            st.info(f"📊 **Multi-Timeframe Confluence (Improvement G):** `{conf.score}/{conf.max_score}` — {conf.badge}")
            conf_cols = st.columns(4)
            for i, chk in enumerate(conf.checks[:4]):
                icon = "✅" if chk.aligned else "❌"
                conf_cols[i].markdown(f"**{icon} {chk.timeframe}**\n\n{chk.reason}")

        # Upgrade D: Temporal Intelligence Display
        if selected_c.time_prediction:
            tp = selected_c.time_prediction
            st.markdown("##### ⏱️ Target Arrival Forecast & Holding Period (Upgrade D)")
            c_tp1, c_tp2, c_tp3, c_tp4 = st.columns(4)
            c_tp1.metric("Est. Holding Period", f"{tp.hold_median} {tp.unit}", f"Range: {tp.hold_q25} – {tp.hold_q75} {tp.unit}")
            c_tp2.metric("Target 1 ETA", tp.target_1_eta, f"Window: {tp.target_1_eta_range}")
            c_tp3.metric("Target 2 ETA", tp.target_2_eta, f"Window: {tp.target_2_eta_range}")
            c_tp4.metric("Time-Stop Threshold", tp.time_stop_date, f"P(T1 Hit): {tp.survival_prob_t1:.0%}")

        # Upgrade C.1: Options Flow & Gamma Wall Intelligence
        with st.expander(f"🐋 Live Options Flow & Gamma Wall Intelligence for {selected_c.ticker}"):
            with st.spinner(f"Parsing live options chain for {selected_c.ticker}..."):
                opt_report = options_analyzer.analyze_ticker_options(selected_c.ticker)
            if opt_report.has_options:
                col_o1, col_o2, col_o3, col_o4 = st.columns(4)
                col_o1.metric("Call / Put Volume", f"{opt_report.total_call_volume:,} / {opt_report.total_put_volume:,}")
                col_o2.metric("Put-Call Ratio (PCR)", f"{opt_report.put_call_ratio:.2f}", opt_report.sentiment_verdict)
                col_o3.metric("Gamma Wall Strike", f"${opt_report.gamma_wall_strike:.2f}")
                col_o4.metric("Gamma Squeeze Risk", "🔥 HIGH" if opt_report.is_gamma_squeeze_candidate else "MODERATE")

                if opt_report.unusual_strikes:
                    st.write("##### ⚡ Unusual Strike Activity (Volume > 1.8x Open Interest)")
                    uo_list = []
                    for u in opt_report.unusual_strikes:
                        uo_list.append({
                            "Strike": f"${u.strike:.2f}",
                            "Call Volume": f"{u.call_volume:,}",
                            "Open Interest": f"{u.open_interest:,}",
                            "Vol / OI Ratio": f"{u.volume_to_oi_ratio:.1f}x",
                            "Implied Vol": f"{u.implied_volatility:.1f}%",
                            "In The Money": "✅ ITM" if u.in_the_money else "OTM"
                        })
                    st.dataframe(pd.DataFrame(uo_list), use_container_width=True)
            else:
                st.info(opt_report.summary)

        # Interactive Plotly Chart
        with st.spinner(f"Rendering technical chart for {selected_c.ticker}..."):
            if is_swing:
                raw_df = data_provider.get_historical_daily(selected_c.ticker, period="6mo")
                raw_df = compute_all_swing_features(raw_df)
            else:
                raw_df = data_provider.get_intraday_bars(selected_c.ticker, interval="5m", period="3d")
                raw_df = compute_all_intraday_features(raw_df)

            if not raw_df.empty:
                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.08,
                    row_heights=[0.75, 0.25],
                    subplot_titles=(f"{selected_c.ticker} Price Action & Risk Levels", "Volume & RVOL")
                )

                # Candlestick
                fig.add_trace(go.Candlestick(
                    x=raw_df.index,
                    open=raw_df["Open"],
                    high=raw_df["High"],
                    low=raw_df["Low"],
                    close=raw_df["Close"],
                    name="OHLC"
                ), row=1, col=1)

                # Moving Averages / VWAP
                if is_swing:
                    if "SMA_50" in raw_df.columns:
                        fig.add_trace(go.Scatter(x=raw_df.index, y=raw_df["SMA_50"], line=dict(color="#3B82F6", width=1.5), name="50 SMA"), row=1, col=1)
                    if "SMA_150" in raw_df.columns:
                        fig.add_trace(go.Scatter(x=raw_df.index, y=raw_df["SMA_150"], line=dict(color="#F59E0B", width=1.5), name="150 SMA"), row=1, col=1)
                    if "SMA_200" in raw_df.columns:
                        fig.add_trace(go.Scatter(x=raw_df.index, y=raw_df["SMA_200"], line=dict(color="#EC4899", width=2), name="200 SMA"), row=1, col=1)
                else:
                    if "VWAP" in raw_df.columns:
                        fig.add_trace(go.Scatter(x=raw_df.index, y=raw_df["VWAP"], line=dict(color="#A855F7", width=2), name="VWAP"), row=1, col=1)

                # Horizontal Risk Overlays
                fig.add_hline(y=ticket.entry_price, line_dash="solid", line_color="#10B981", annotation_text="ENTRY", row=1, col=1)
                fig.add_hline(y=ticket.stop_loss, line_dash="dash", line_color="#EF4444", annotation_text="STOP LOSS", row=1, col=1)
                fig.add_hline(y=ticket.target_1, line_dash="dash", line_color="#3B82F6", annotation_text="TARGET 1 (2R)", row=1, col=1)
                fig.add_hline(y=ticket.target_2, line_dash="dash", line_color="#8B5CF6", annotation_text="TARGET 2 (3.5R)", row=1, col=1)

                # Volume
                vol_colors = ["#10B981" if raw_df["Close"].iloc[i] >= raw_df["Open"].iloc[i] else "#EF4444" for i in range(len(raw_df))]
                fig.add_trace(go.Bar(
                    x=raw_df.index,
                    y=raw_df["Volume"],
                    marker_color=vol_colors,
                    name="Volume"
                ), row=2, col=1)

                fig.update_layout(
                    height=600,
                    template="plotly_dark",
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=20, r=20, t=40, b=20)
                )

                st.plotly_chart(fig, use_container_width=True)

        # Action dispatch buttons
        col_act1, col_act2, col_act3 = st.columns([1, 1, 2])
        with col_act1:
            if st.button("📥 Track in Portfolio", type="primary", use_container_width=True):
                res = virtual_broker.open_position(
                    ticker=selected_c.ticker,
                    entry_price=ticket.entry_price,
                    shares=ticket.recommended_shares,
                    stop_loss=ticket.stop_loss,
                    target_1=ticket.target_1,
                    target_2=ticket.target_2,
                    market="US" if is_us else "INDIA",
                    timeframe="SWING" if is_swing else "INTRADAY",
                    pattern=selected_c.pattern,
                    notes=selected_c.summary
                )
                if res["success"]:
                    st.success(f"✅ {selected_c.ticker} added to Active Portfolio! Monitoring trailing stops.")
                else:
                    st.warning(res["message"])

        with col_act2:
            if st.button("📤 Dispatch to Telegram", use_container_width=True):
                sent = telegram_notifier.send_trade_ticket(
                    selected_c.ticket,
                    pattern_name=selected_c.pattern,
                    notes=selected_c.summary,
                    time_prediction=selected_c.time_prediction,
                    meta_label=getattr(selected_c, "meta_label", None),
                    confluence=getattr(selected_c, "confluence", None)
                )
                if sent:
                    st.success("Alert pushed to Telegram!")
                else:
                    st.info("Simulated alert logged (Configure TELEGRAM_BOT_TOKEN in .env to send real messages).")


with tab_backtest:
    st.subheader("🧪 Historical Strategy Simulator")
    st.caption("Simulate the Minervini Stage 2 Swing Strategy across multi-year historical data.")

    col_bt1, col_bt2, col_bt3 = st.columns([2, 1, 1])
    with col_bt1:
        default_ticker = "NVDA" if is_us else "RELIANCE.NS"
        test_ticker = st.text_input("Enter Ticker to Backtest", value=default_ticker)
    with col_bt2:
        test_period = st.selectbox("Lookback Window", ["1y", "2y", "5y"], index=1)
    with col_bt3:
        st.write("")
        st.write("")
        run_bt = st.button("Run Simulation", type="primary", use_container_width=True)

    if run_bt or "last_bt" not in st.session_state:
        with st.spinner(f"Simulating trade executions on {test_ticker}..."):
            bt_res = backtest_engine.backtest_swing_ticker(test_ticker, period=test_period)
            st.session_state["last_bt"] = bt_res

    bt = st.session_state.get("last_bt")
    if bt and bt.total_trades > 0:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Trades", bt.total_trades)
        c2.metric("Win Rate", f"{bt.win_rate_pct}%")
        c3.metric("Profit Factor", f"{bt.profit_factor:.2f}")
        c4.metric("Strategy Return", f"{bt.total_return_pct}%", delta=f"{currency_symbol}{bt.total_pnl:,.2f}")
        c5.metric("Max Drawdown", f"{bt.max_drawdown_pct}%", delta_color="inverse")

        st.write("#### Trade Execution Log")
        trades_list = []
        for t in bt.trades:
            trades_list.append({
                "Entry Date": t.entry_date,
                "Exit Date": t.exit_date,
                "Entry Price": f"{currency_symbol}{t.entry_price:.2f}",
                "Exit Price": f"{currency_symbol}{t.exit_price:.2f}",
                "Shares": t.shares,
                "P&L ($)": f"{currency_symbol}{t.pnl:.2f}",
                "P&L (%)": f"{t.pnl_pct}%",
                "Outcome": t.outcome,
                "Holding Days": t.holding_days
            })
        st.dataframe(pd.DataFrame(trades_list), use_container_width=True)
    elif bt:
        st.info(f"No trades triggered on {test_ticker} during the {test_period} window under these specific entry rules.")


with tab_value:
    st.subheader("💎 Peter Lynch & Warren Buffett Multi-Bagger Finder")
    st.caption("Scans for companies with high Return on Equity (ROE > 15%), low Debt/Equity, and low PEG ratios (< 1.2) representing undervalued hyper-growth.")

    col_vg1, col_vg2 = st.columns([1, 4])
    with col_vg1:
        run_value_scan = st.button("🔍 Scan for Value-Growth", type="primary", use_container_width=True)

    if run_value_scan or "last_vg_results" not in st.session_state:
        with st.spinner("Analyzing balance sheets, PEG ratios, and cash flows..."):
            vg_universe = US_CORE_UNIVERSE if is_us else INDIA_NSE_CORE_UNIVERSE
            vg_results = value_growth_engine.scan_universe(vg_universe[:20])
            st.session_state["last_vg_results"] = vg_results

    vg_results = st.session_state.get("last_vg_results", [])
    if vg_results:
        st.success(f"Found **{len(vg_results)} deeply undervalued growth stocks** matching Peter Lynch & Buffett metrics.")

        vg_table = []
        for v in vg_results:
            vg_table.append({
                "Ticker": v.ticker,
                "Company": v.company_name,
                "Price": f"{currency_symbol}{v.current_price:.2f}",
                "Forward P/E": v.forward_pe,
                "PEG Ratio": v.peg_ratio,
                "ROE (%)": f"{v.roe_pct}%",
                "Debt / Equity": v.debt_to_equity,
                "Lynch Score": f"{v.peter_lynch_score:.0f}/100",
                "Verdict": v.valuation_verdict
            })
        st.dataframe(pd.DataFrame(vg_table), use_container_width=True)

        st.divider()
        st.subheader("📰 Live Financial News & Catalyst Analyzer")
        selected_vg_ticker = st.selectbox("Select Stock to Inspect News & Catalysts", [v.ticker for v in vg_results])

        with st.spinner(f"Scraping and analyzing recent headlines for {selected_vg_ticker}..."):
            news_res = news_analyzer.analyze_ticker_news(selected_vg_ticker, max_articles=8)

        st.markdown(f"### {news_res.overall_sentiment}")
        st.caption(f"Net Catalyst Score: **{news_res.net_sentiment_score:+0.1f}%** (Bullish: {news_res.bullish_count} | Bearish: {news_res.bearish_count})")

        if news_res.articles:
            for art in news_res.articles:
                badge = "🟢 BULLISH" if art.sentiment_tag == "BULLISH" else ("🔴 BEARISH" if art.sentiment_tag == "BEARISH" else "⚪ NEUTRAL")
                with st.expander(f"{badge} | {art.title}"):
                    st.write(f"**Publisher:** {art.publisher}")
                    st.markdown(f"[Read Full Article]({art.link})")
        else:
            st.info(f"No recent news articles found for {selected_vg_ticker} right now.")
    else:
        st.info("Run the scan to evaluate fundamentals across the selected universe.")


with tab_macro:
    st.subheader("🏛️ Institutional Macro Cycles & Smart Money Intelligence")
    st.caption("Synthesizes Ray Dalio's Macroeconomic Machine, Howard Marks' Market Cycles, US Congressional disclosures, and secular future megatrends.")

    # 1. Macro Economic Quadrant
    macro_data = macro_smart_money.get_macro_economic_regime()

    st.markdown(f"### {macro_data.phase_name}")
    st.caption(f"Status: **{macro_data.status}**")

    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
    m_col1.metric("10-Year Yield", f"{macro_data.ten_year_yield:.2f}%")
    m_col2.metric("US Dollar (DXY)", f"{macro_data.dollar_index:.2f}")
    m_col3.metric("Crude Oil (WTI)", f"${macro_data.crude_oil:.2f}")
    m_col4.metric("Gold Futures", f"${macro_data.gold_price:,.2f}")
    m_col5.metric("CBOE VIX", f"{macro_data.vix:.2f}")

    col_fav, col_def = st.columns(2)
    with col_fav:
        st.success(f"🟢 **Favored Sectors in this Cycle:** {', '.join(macro_data.favored_sectors)}")
    with col_def:
        st.warning(f"🛡️ **Defensive / Vulnerable Sectors:** {', '.join(macro_data.defensive_sectors)}")

    st.info(f"💡 **Macro Execution Thesis:** {macro_data.guidance}")

    st.divider()

    # 2. Congressional & Politician Trades Tracker (STOCK Act)
    st.subheader("🇺🇸 US Congressional & Politician Trades (STOCK Act Disclosures)")
    st.caption("Tracks stock disclosures by members of Congress and key committee chairs preceding major legislative, defense, or regulatory shifts.")

    pol_trades = macro_smart_money.get_prominent_politician_trades()
    pol_table = []
    for pt in pol_trades:
        pol_table.append({
            "Politician": pt.politician,
            "Chamber / Party": f"{pt.chamber} ({pt.party})",
            "Action": f"🟢 {pt.trade_type}" if pt.trade_type == "PURCHASE" else f"🔴 {pt.trade_type}",
            "Ticker": pt.ticker,
            "Company": pt.company_name,
            "Est. Amount": pt.estimated_amount,
            "Filing Date": pt.filing_date,
            "Committee Context / Catalyst": pt.rationale_context
        })
    st.dataframe(pd.DataFrame(pol_table), use_container_width=True)

    st.divider()

    # 3. Live Corporate Insider Activity (Form 4)
    st.subheader("👔 Corporate Insider Transactions (SEC Form 4)")
    st.caption("Tracks open-market buying and selling by CEOs, CFOs, and Board Directors.")

    insider_search_ticker = st.text_input("Inspect Insider Activity for Ticker", value="NVDA")
    if insider_search_ticker:
        with st.spinner(f"Fetching recent SEC Form 4 filings for {insider_search_ticker}..."):
            insider_res = macro_smart_money.get_sec_insider_activity(insider_search_ticker)

        if insider_res["has_data"] and insider_res["records"]:
            st.dataframe(pd.DataFrame(insider_res["records"]), use_container_width=True)
        else:
            st.info(f"No recent Form 4 insider filings found for {insider_search_ticker} via the active feed.")

    st.divider()

    # 4. Secular Future Megatrends Baskets (2026 - 2038)
    st.subheader("🚀 Secular Future Megatrends (Multi-Year Thematic Compounders)")
    st.caption("Structural macroeconomic shifts poised to create multi-bagger compounders over the next decade.")

    megatrends = macro_smart_money.get_future_megatrends()
    for mt in megatrends:
        with st.expander(f"{mt.theme} [{mt.horizon_years}]"):
            st.write(f"**Catalyst & Growth Thesis:** {mt.catalyst_thesis}")
            st.markdown(f"**Leading Thematic Stocks:** `{', '.join(mt.leading_stocks)}`")


with tab_ledger:
    st.subheader("💼 Virtual Trading Desk & Active Portfolio")
    st.caption("100% Free paper execution ledger. Tracks active positions, automatically books 50% profit at Target 1, trails stop-loss to Break-Even, and records your official equity curve.")

    # 1. Top Metrics Banner
    summary = virtual_broker.get_portfolio_summary()

    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    col_m1.metric("Total Equity", f"{currency_symbol}{summary['current_equity']:,.2f}")
    col_m2.metric("Available Cash", f"{currency_symbol}{summary['cash_balance']:,.2f}")
    col_m3.metric("Invested Capital", f"{currency_symbol}{summary['invested_capital']:,.2f}")
    col_m4.metric("Realized P&L", f"{currency_symbol}{summary['realized_pnl']:+,.2f}")
    col_m5.metric("Unrealized P&L", f"{currency_symbol}{summary['unrealized_pnl']:+,.2f}")
    col_m6.metric(
        "Win Rate",
        f"{summary['win_rate']:.1f}%",
        delta=f"PF: {summary['profit_factor']:.2f}"
    )

    # P0 Circuit Breaker Shield Status
    cb_status = virtual_broker.risk_manager.evaluate_circuit_breaker(
        peak_equity=max(summary["initial_cash"], summary["current_equity"]),
        current_equity=summary["current_equity"]
    )
    if cb_status.level == "RED_15PCT_LOCKOUT":
        st.error(f"🚨 **CIRCUIT BREAKER LOCKOUT:** {cb_status.message} (Drawdown: {cb_status.drawdown_pct:.1f}%)")
    elif cb_status.level == "ORANGE_10PCT":
        st.warning(f"⚠️ **CIRCUIT BREAKER ORANGE:** {cb_status.message} (Drawdown: {cb_status.drawdown_pct:.1f}%)")
    elif cb_status.level == "YELLOW_5PCT":
        st.warning(f"🟡 **CIRCUIT BREAKER YELLOW:** {cb_status.message} (Drawdown: {cb_status.drawdown_pct:.1f}%)")
    else:
        st.success(f"🛡️ **Institutional Risk Armor:** {cb_status.message} | Drawdown: {cb_status.drawdown_pct:.1f}% | Risk Sizing Multiplier: {cb_status.risk_multiplier * 100:.0f}%")

    st.divider()

    # 2. Controls & Auto-Update
    col_ctrl1, col_ctrl2 = st.columns([2, 3])
    with col_ctrl1:
        if st.button("🔄 Check Live Prices & Auto-Trail Stops", type="primary", use_container_width=True):
            with st.spinner("Polling live market quotes and evaluating stop/target triggers..."):
                events = virtual_broker.update_all_positions()
                if events:
                    for ev in events:
                        if ev["type"] == "T1_HIT":
                            st.success(f"🎯 **Target 1 Achieved:** {ev['message']}")
                        elif ev["type"] == "T2_HIT":
                            st.balloons()
                            st.success(f"🏆 **Target 2 Achieved:** {ev['message']}")
                        else:
                            st.warning(f"🛑 **Stop-Loss Triggered:** {ev['message']}")
                else:
                    st.info("Quotes refreshed. All active positions are within normal target/stop ranges.")

    st.divider()

    # 3. Active Positions
    st.subheader(f"📍 Active Open Positions ({summary['active_positions_count']})")
    active_positions = virtual_broker.get_active_positions()

    if not active_positions:
        st.info("No active positions currently open. Scan stocks in Tab 1 and click '📥 Track in Portfolio', or manually add a trade below.")
    else:
        active_table = []
        for p in active_positions:
            status_badge = "🛡️ Break-Even Active" if p["is_breakeven"] else "🟢 Active"
            if p["status"] == "PARTIAL_T1":
                status_badge = "🎯 T1 Booked (Running 50%)"

            active_table.append({
                "ID": p["id"],
                "Ticker": p["ticker"],
                "Status": status_badge,
                "Shares Left": p["remaining_shares"],
                "Entry Price": f"{currency_symbol}{p['entry_price']:.2f}",
                "Live Price": f"{currency_symbol}{p['current_price']:.2f}",
                "Trailing Stop": f"{currency_symbol}{p['current_stop']:.2f}",
                "Target 1": f"{currency_symbol}{p['target_1']:.2f}",
                "Target 2": f"{currency_symbol}{p['target_2']:.2f}",
                "Unrealized P&L": f"{currency_symbol}{p['unrealized_pnl']:+,.2f} ({p['unrealized_pct']:+.2f}%)",
                "Entry Date": p["entry_date"]
            })
        st.dataframe(pd.DataFrame(active_table), use_container_width=True)

        # Quick close manual selector
        col_cl1, col_cl2 = st.columns([2, 1])
        with col_cl1:
            trade_to_close = st.selectbox(
                "Select Position to Close Manually at Current Market Price",
                [f"#{p['id']} - {p['ticker']} ({p['remaining_shares']} shares)" for p in active_positions]
            )
        with col_cl2:
            st.write("")
            st.write("")
            if st.button("Close Position", type="secondary", use_container_width=True):
                trade_id_val = int(trade_to_close.split(" - ")[0].replace("#", ""))
                res = virtual_broker.close_position_manually(trade_id_val)
                if res["success"]:
                    st.success(res["message"])
                    st.rerun()
                else:
                    st.error(res["message"])

    st.divider()

    # 4. Manual Order Entry Form
    with st.expander("➕ Manually Add a Tracked Position (For Trades Placed in Your Real Broker App)"):
        st.caption("Use this to track trades you execute on your personal broker app (e.g. Zerodha, Groww, Robinhood, Schwab).")
        col_m_f1, col_m_f2, col_m_f3 = st.columns(3)
        with col_m_f1:
            m_ticker = st.text_input("Ticker Symbol", value="NVDA").upper()
            m_shares = st.number_input("Shares Quantity", min_value=1, value=10, step=1)
        with col_m_f2:
            m_entry = st.number_input("Entry Price", min_value=0.01, value=120.0, step=0.5)
            m_stop = st.number_input("Stop Loss Price", min_value=0.01, value=112.0, step=0.5)
        with col_m_f3:
            m_t1 = st.number_input("Target 1 Price", min_value=0.01, value=136.0, step=0.5)
            m_t2 = st.number_input("Target 2 Price", min_value=0.01, value=148.0, step=0.5)

        m_pattern = st.selectbox("Setup Type", ["Minervini Stage 2", "15m ORB Breakout", "VCP Consolidation", "Peter Lynch Value", "Manual Discretionary"])
        if st.button("📥 Add to Active Portfolio Tracker", use_container_width=True):
            res = virtual_broker.open_position(
                ticker=m_ticker,
                entry_price=m_entry,
                shares=m_shares,
                stop_loss=m_stop,
                target_1=m_t1,
                target_2=m_t2,
                market="US" if is_us else "INDIA",
                timeframe="SWING",
                pattern=m_pattern,
                notes="Manually logged broker trade"
            )
            if res["success"]:
                st.success(res["message"])
                st.rerun()
            else:
                st.warning(res["message"])

    st.divider()

    # 5. Closed Trades History & System Logs
    col_hist, col_logs = st.columns([3, 2])
    with col_hist:
        st.subheader("📜 Closed Trades Track Record")
        closed_trades = virtual_broker.get_closed_trades()
        if not closed_trades:
            st.caption("No closed trades recorded yet.")
        else:
            cl_table = []
            for ct in closed_trades:
                cl_table.append({
                    "Ticker": ct["ticker"],
                    "Entry Date": ct["entry_date"][:10],
                    "Exit Date": ct["exit_date"][:10] if ct["exit_date"] else "-",
                    "Entry": f"{currency_symbol}{ct['entry_price']:.2f}",
                    "Exit": f"{currency_symbol}{ct['exit_price']:.2f}" if ct["exit_price"] else "-",
                    "P&L ($)": f"{currency_symbol}{ct['realized_pnl']:+,.2f}",
                    "Return (%)": f"{ct['return_pct']:+.2f}%",
                    "Exit Reason": ct["exit_reason"]
                })
            st.dataframe(pd.DataFrame(cl_table), use_container_width=True)

    with col_logs:
        st.subheader("📋 Trailing Stop & Action Logs")
        logs = virtual_broker.get_recent_logs(limit=15)
        if not logs:
            st.caption("No audit logs recorded yet.")
        else:
            for lg in logs:
                st.write(f"`{lg['timestamp']}` **[{lg['event_type']}]** {lg['ticker'] or ''}: {lg['message']}")
