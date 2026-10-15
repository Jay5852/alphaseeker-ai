"""Main Entry Point for AlphaSeeker AI Stock Finder.

Usage:
    python main.py --market US --timeframe swing
    python main.py --market INDIA --timeframe swing
    python main.py --market US --timeframe intraday
    python main.py --dashboard
"""

import argparse
import sys
import subprocess
from config.universes import (
    US_CORE_UNIVERSE, US_HIGH_MOMENTUM_WATCHLIST,
    INDIA_NSE_CORE_UNIVERSE, INDIA_NSE_MOMENTUM_WATCHLIST
)
from engines.swing_engine import SwingEngine
from engines.intraday_engine import IntradayEngine
from ml.regime import regime_classifier
from alerts.formatter import format_trade_ticket_text
from alerts.telegram_bot import telegram_notifier
from risk.manager import RiskManager
from data.live_scrapers import live_scraper
from ledger.virtual_broker import virtual_broker


def run_cli_scan(market: str, timeframe: str, source: str = "live_active", auto_track: bool = False):
    print("\n" + "="*60)
    print(f"🚀 ALPHASEEKER AI: SCANNING {market.upper()} [{timeframe.upper()}] (Source: {source})")
    print("="*60)

    # 1. Macro Regime Check
    regime = regime_classifier.classify_market(market)
    print(f"📊 Market Regime: {regime.status} ({regime.benchmark}: {regime.current_price})")
    print(f"💡 Guidance: {regime.guidance}\n")

    # 2. Select universe and capital
    is_us = market.upper() == "US"
    currency = "$" if is_us else "₹"
    capital = 10000.0 if is_us else 200000.0

    risk_mgr = RiskManager(total_capital=capital, max_risk_pct=0.015)

    # Resolve universe dynamically via live scrapers
    if is_us:
        if source == "live_active":
            print("🌐 Scraping real-time most active movers from market feeds...")
            universe = live_scraper.scrape_us_most_actives(count=35)
        elif source == "live_gainers":
            print("🌐 Scraping real-time top day gainers from market feeds...")
            universe = live_scraper.scrape_us_day_gainers(count=35)
        elif source == "live_sp500":
            print("🌐 Scraping live S&P 500 index constituents...")
            universe = live_scraper.scrape_sp500_live()[:50]
        else:
            universe = US_CORE_UNIVERSE if timeframe.lower() == "swing" else US_HIGH_MOMENTUM_WATCHLIST
    else:
        if source in ["live_active", "live_nifty"]:
            print("🌐 Scraping live Nifty 50 index constituents...")
            universe = live_scraper.scrape_nifty50_live()
        else:
            universe = INDIA_NSE_CORE_UNIVERSE if timeframe.lower() == "swing" else INDIA_NSE_MOMENTUM_WATCHLIST

    if timeframe.lower() == "swing":
        engine = SwingEngine(risk_manager=risk_mgr)
        print(f"Scanning {len(universe)} stocks with Minervini Trend Template & VCP...")
        results = engine.scan_universe(universe)
    else:
        engine = IntradayEngine(risk_manager=risk_mgr)
        print(f"Scanning {len(universe)} stocks with 15m ORB & VWAP Momentum...")
        results = engine.scan_universe(universe)

    if not results:
        print("❌ No trade setups currently meet all technical and strict Risk:Reward filters.")
        return

    print(f"\n✅ Found {len(results)} high-conviction trade setups:\n")
    for i, candidate in enumerate(results, start=1):
        ticket = candidate.ticket
        print(f"[{i}] {candidate.ticker} | Score: {candidate.confidence_score:.0f}% | Setup: {candidate.pattern}")
        print(f"    Entry: {currency}{ticket.entry_price:.2f} | Stop Loss: {currency}{ticket.stop_loss:.2f}")
        print(f"    Target 1: {currency}{ticket.target_1:.2f} (2.0R) | Target 2: {currency}{ticket.target_2:.2f} (3.5R)")
        print(f"    Qty: {ticket.recommended_shares} shares | Capital: {currency}{ticket.capital_required:,.2f} | Risk: {currency}{ticket.dollar_risk_amount:.2f}")
        if candidate.time_prediction:
            print(f"    ⏱️  Timeline: {candidate.time_prediction.summary_badge()}")
        if getattr(candidate, "meta_label", None):
            print(f"    🤖 ML Win Prob: {candidate.meta_label.win_probability:.1%} [{candidate.meta_label.confidence_tier}]")
        if getattr(candidate, "confluence", None):
            print(f"    📊 Confluence: {candidate.confluence.summary()}")
        print(f"    RVOL: {candidate.rvol}x\n")

    top_pick = results[0]
    print("="*60)
    print(f"🏆 TOP OPPORTUNITY CARD:\n")
    ticket_msg = format_trade_ticket_text(
        top_pick.ticket,
        top_pick.pattern,
        top_pick.summary,
        time_prediction=top_pick.time_prediction,
        meta_label=getattr(top_pick, "meta_label", None),
        confluence=getattr(top_pick, "confluence", None)
    )
    print(ticket_msg)
    print("="*60)

    if auto_track:
        res = virtual_broker.open_position(
            ticker=top_pick.ticker,
            entry_price=top_pick.ticket.entry_price,
            shares=top_pick.ticket.recommended_shares,
            stop_loss=top_pick.ticket.stop_loss,
            target_1=top_pick.ticket.target_1,
            target_2=top_pick.ticket.target_2,
            market=market.upper(),
            timeframe=timeframe.upper(),
            pattern=top_pick.pattern,
            notes=top_pick.summary
        )
        print(f"\n💼 Portfolio Update: {res['message']}")


def show_cli_portfolio():
    """Prints the current active positions and portfolio summary to the terminal."""
    print("\n" + "="*60)
    print("💼 ALPHASEEKER AI: VIRTUAL PORTFOLIO & DESK SUMMARY")
    print("="*60)

    summary = virtual_broker.get_portfolio_summary()
    print(f"💰 Equity: ${summary['current_equity']:,.2f} | Cash: ${summary['cash_balance']:,.2f} | Invested: ${summary['invested_capital']:,.2f}")
    print(f"📈 Realized P&L: ${summary['realized_pnl']:+,.2f} | Unrealized P&L: ${summary['unrealized_pnl']:+,.2f}")
    print(f"🏆 Win Rate: {summary['win_rate']:.1f}% ({summary['winning_trades']}W / {summary['losing_trades']}L) | Profit Factor: {summary['profit_factor']:.2f}")

    active = virtual_broker.get_active_positions()
    print(f"\n📍 ACTIVE POSITIONS ({len(active)}):")
    if not active:
        print("  (No active open positions. Run with --auto-track or use web dashboard to add positions)")
    else:
        for p in active:
            be_tag = "[BREAK-EVEN]" if p["is_breakeven"] else ""
            print(f"  • #{p['id']} {p['ticker']} ({p['remaining_shares']} shs) | Entry: ${p['entry_price']:.2f} | Live: ${p['current_price']:.2f} | Stop: ${p['current_stop']:.2f} {be_tag}")
            print(f"    T1: ${p['target_1']:.2f} | T2: ${p['target_2']:.2f} | PnL: ${p['unrealized_pnl']:+,.2f} ({p['unrealized_pct']:+.2f}%)")

    logs = virtual_broker.get_recent_logs(limit=5)
    if logs:
        print("\n📋 RECENT ACTIONS:")
        for lg in logs:
            print(f"  [{lg['timestamp'][:16]}] {lg['event_type']}: {lg['message']}")
    print("="*60 + "\n")


def run_cli_update_ledger():
    """Polls live market prices for all open positions and triggers stops/targets."""
    print("\n🔄 Updating active positions and checking trailing stops...")
    events = virtual_broker.update_all_positions()
    if not events:
        print("✅ All open positions updated. No stop or target triggers fired.")
    else:
        for ev in events:
            print(f"🔔 [{ev['type']}] {ev['ticker']}: {ev['message']}")
    show_cli_portfolio()


def start_dashboard():
    """Launches the Streamlit Web Application."""
    print("🌐 Launching AlphaSeeker AI Web Dashboard on http://localhost:8501 ...")
    cmd = [sys.executable, "-m", "streamlit", "run", "dashboard/app.py"]
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="AlphaSeeker AI Stock Finder")
    parser.add_argument("--market", type=str, default="US", choices=["US", "INDIA", "us", "india"], help="Target market")
    parser.add_argument("--timeframe", type=str, default="swing", choices=["swing", "intraday"], help="Trading timeframe")
    parser.add_argument("--source", type=str, default="live_active", choices=["live_active", "live_gainers", "live_sp500", "live_nifty", "watchlist"], help="Stock universe source")
    parser.add_argument("--auto-track", action="store_true", help="Automatically track top candidate in virtual portfolio")
    parser.add_argument("--portfolio", action="store_true", help="Display virtual portfolio track record and active positions")
    parser.add_argument("--update-ledger", action="store_true", help="Update live prices and check trailing stops for open positions")
    parser.add_argument("--daemon", action="store_true", help="Launch 24/7 autonomous background market daemon")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit Web Dashboard")

    args = parser.parse_args()

    if args.dashboard:
        start_dashboard()
    elif args.daemon:
        from daemon.market_daemon import market_daemon
        market_daemon.market = args.market.upper()
        market_daemon.start()
    elif args.portfolio:
        show_cli_portfolio()
    elif args.update_ledger:
        run_cli_update_ledger()
    else:
        run_cli_scan(market=args.market, timeframe=args.timeframe, source=args.source, auto_track=args.auto_track)


if __name__ == "__main__":
    main()
