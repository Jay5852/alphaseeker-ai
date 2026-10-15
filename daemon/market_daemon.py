"""Autonomous 24/7 Market Daemon & Execution Clock (Upgrade A.2).

Runs continuously in the background with zero local intervention:
1. Hourly & Real-time: Updates active positions, auto-trails stop-loss to Break-Even at Target 1,
   and notifies Telegram when targets/stops fire.
2. Market Open (9:30 AM): Scans Opening Range Breakouts (ORB) on volume leaders.
3. Market Close (4:00 PM): Runs EOD Minervini Stage 2 swing scan and logs daily portfolio snapshot.
4. Post-Market: Dispatches daily performance digest to Telegram.
"""

import time
import logging
from datetime import datetime, time as dtime
from typing import Optional

from ledger.virtual_broker import virtual_broker
from alerts.telegram_bot import telegram_notifier
from data.live_scrapers import live_scraper
from engines.swing_engine import SwingEngine
from engines.intraday_engine import IntradayEngine
from risk.manager import RiskManager
from ml.regime import regime_classifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("MarketDaemon")


class AutonomousMarketDaemon:
    def __init__(
        self,
        market: str = "US",
        check_interval_seconds: int = 60,
        enable_telegram: bool = True
    ):
        self.market = market.upper()
        self.check_interval = check_interval_seconds
        self.enable_telegram = enable_telegram
        self.running = False
        self._last_open_scan_date: Optional[str] = None
        self._last_eod_scan_date: Optional[str] = None

    def start(self):
        """Starts the 24/7 autonomous loop."""
        self.running = True
        logger.info(f"⚡ AlphaSeeker Autonomous Daemon started for {self.market} market.")
        logger.info(f"Loop interval: {self.check_interval}s. Press Ctrl+C to terminate.")

        if self.enable_telegram:
            telegram_notifier.send_message(
                f"🤖 **AlphaSeeker 24/7 Market Daemon Started**\n"
                f"• Market: `{self.market}`\n"
                f"• Active Positions Monitored: `{len(virtual_broker.get_active_positions())}`\n"
                f"• Auto Break-Even Trailing: `ENABLED`\n"
                f"• Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )

        while self.running:
            try:
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")

                # 1. Continuous Routine: Update Active Positions & Trailing Stops
                self._routine_update_positions()

                # 2. Market Open Routine (9:30 AM - 10:00 AM on weekdays)
                if now.weekday() < 5 and dtime(9, 30) <= now.time() <= dtime(10, 0):
                    if self._last_open_scan_date != today_str:
                        self._routine_market_open_scan()
                        self._last_open_scan_date = today_str

                # 3. Market Close Routine (4:00 PM - 4:30 PM on weekdays)
                if now.weekday() < 5 and dtime(16, 0) <= now.time() <= dtime(16, 30):
                    if self._last_eod_scan_date != today_str:
                        self._routine_market_close_eod()
                        self._last_eod_scan_date = today_str

                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                logger.info("Daemon interrupted by user. Shutting down gracefully...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in daemon main loop: {e}", exc_info=True)
                time.sleep(10)

    def _routine_update_positions(self):
        """Polls prices and executes automated trailing stops and profit booking."""
        active = virtual_broker.get_active_positions()
        if not active:
            return

        events = virtual_broker.update_all_positions()
        for ev in events:
            logger.info(f"[{ev['type']}] {ev['ticker']}: {ev['message']}")
            if self.enable_telegram:
                telegram_notifier.send_message(f"🔔 **DESK ALERT: {ev['type']}**\n{ev['message']}")

    def _routine_market_open_scan(self):
        """Executes Opening Range Breakout scans on live active movers."""
        logger.info("⏰ Running Market Open Momentum Scan (15m ORB)...")
        try:
            if self.market == "US":
                movers = live_scraper.scrape_us_most_actives(count=25)
            else:
                movers = live_scraper.scrape_india_nifty50()[:25]

            engine = IntradayEngine()
            results = engine.scan_universe(movers)

            if results:
                top = results[0]
                logger.info(f"Found {len(results)} intraday setups. Top pick: {top.ticker}")
                if self.enable_telegram:
                    telegram_notifier.send_trade_ticket(
                        top.ticket,
                        pattern_name=top.pattern,
                        notes=f"Autonomous 9:30 AM ORB Scan | Score: {top.confidence_score:.0f}%",
                        time_prediction=top.time_prediction
                    )
        except Exception as e:
            logger.error(f"Error in market open scan: {e}")

    def _routine_market_close_eod(self):
        """Executes End-Of-Day swing scans and records daily portfolio snapshot."""
        logger.info("🌆 Running Market Close EOD Swing Scan...")
        try:
            if self.market == "US":
                universe = live_scraper.scrape_sp500_live()[:35]
            else:
                universe = live_scraper.scrape_india_nifty50()

            engine = SwingEngine()
            results = engine.scan_universe(universe)

            summary = virtual_broker.get_portfolio_summary()
            if self.enable_telegram:
                top_tag = results[0].ticker if results else "None"
                if results and getattr(results[0], "confluence", None):
                    top_tag = f"{top_tag} | {results[0].confluence.summary()}"
                telegram_notifier.send_message(
                    f"📊 **DAILY PORTFOLIO DIGEST**\n"
                    f"• Total Equity: `${summary['current_equity']:,.2f}`\n"
                    f"• Realized P&L: `${summary['realized_pnl']:+,.2f}`\n"
                    f"• Win Rate: `{summary['win_rate']:.1f}%` ({summary['winning_trades']}W / {summary['losing_trades']}L)\n"
                    f"• Active Trades: `{summary['active_positions_count']}`\n"
                    f"• Top EOD Swing Setup: `{top_tag}`"
                )
        except Exception as e:
            logger.error(f"Error in EOD scan: {e}")


market_daemon = AutonomousMarketDaemon()
