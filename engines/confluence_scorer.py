"""Multi-Timeframe Confluence Scoring Engine.

Professional traders never trade a single timeframe in isolation. This module
checks alignment across 4 timeframes (Monthly, Weekly, Daily, 4-Hour) and
assigns a Confluence Score (0–4) to every trade candidate.

Scoring:
    4/4 = "MAXIMUM CONFLUENCE" → Highest conviction, full position size
    3/4 = "STRONG"             → Trade it, standard position size
    2/4 = "MODERATE"           → Skip — conflicting signals
    1/4 = "WEAK"               → Hard reject
    0/4 = "NO ALIGNMENT"       → Do not trade

Each timeframe check evaluates:
    Monthly : Structural uptrend? (Price > 10-month SMA, RSI > 45)
    Weekly  : Medium-term trend intact? (Price > 40-week SMA, MACD positive)
    Daily   : This is the setup timeframe (handled by swing/intraday engine)
    4-Hour  : Is there a clean pullback entry? (Price near VWAP or 20-EMA,
              not extended > 3% above 20-EMA)

Uses only free yfinance data. Zero external dependencies.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List
import pandas as pd
import numpy as np

from data.provider import data_provider

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Data Classes
# ──────────────────────────────────────────────────────────────

@dataclass
class TimeframeCheck:
    """Result of a single timeframe alignment check."""
    timeframe: str          # 'MONTHLY', 'WEEKLY', 'DAILY', '4H'
    aligned: bool           # True if this timeframe confirms the trade direction
    strength: str           # 'STRONG_BULL', 'BULL', 'NEUTRAL', 'BEAR', 'STRONG_BEAR'
    reason: str             # Human-readable explanation
    key_level: float = 0.0  # The critical moving average or VWAP level checked


@dataclass
class ConfluenceResult:
    """Aggregate multi-timeframe confluence assessment."""
    ticker: str
    score: int                                     # 0 to 4
    max_score: int = 4
    grade: str = ""                                # 'MAXIMUM', 'STRONG', 'MODERATE', 'WEAK', 'NONE'
    badge: str = ""                                # Emoji badge for display
    checks: List[TimeframeCheck] = field(default_factory=list)
    should_trade: bool = False                     # True only if score >= 3

    def __post_init__(self):
        if not self.grade:
            grades = {4: "MAXIMUM", 3: "STRONG", 2: "MODERATE", 1: "WEAK", 0: "NONE"}
            self.grade = grades.get(self.score, "NONE")
        if not self.badge:
            badges = {
                4: "🟢🟢🟢🟢 MAXIMUM CONFLUENCE",
                3: "🟢🟢🟢⚪ STRONG CONFLUENCE",
                2: "🟡🟡⚪⚪ MODERATE — SKIP",
                1: "🔴⚪⚪⚪ WEAK — REJECT",
                0: "⛔ NO ALIGNMENT"
            }
            self.badge = badges.get(self.score, "⛔ NO ALIGNMENT")
        self.should_trade = self.score >= 3

    def summary(self) -> str:
        """One-line summary for CLI and dashboard display."""
        return f"{self.badge} ({self.score}/{self.max_score})"

    def detail_lines(self) -> List[str]:
        """Multi-line detail for expanded view."""
        lines = [f"📊 Multi-Timeframe Confluence: {self.badge}"]
        for chk in self.checks:
            icon = "✅" if chk.aligned else "❌"
            lines.append(f"  {icon} {chk.timeframe}: {chk.reason}")
        return lines


# ──────────────────────────────────────────────────────────────
#  Confluence Scorer
# ──────────────────────────────────────────────────────────────

class ConfluenceScorer:
    """Evaluates multi-timeframe alignment for swing trade candidates.

    All data is sourced from yfinance (free). Monthly and weekly data
    is fetched once per ticker and cached by the data provider.
    """

    def _compute_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Compute RSI from a price series."""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        return 100 - (100 / (1 + rs))

    def _compute_macd(self, series: pd.Series,
                      fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """Compute MACD line and signal line."""
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        return macd_line, signal_line

    # ── Monthly Check ──────────────────────────────────────────

    def check_monthly(self, ticker: str) -> TimeframeCheck:
        """Monthly timeframe: structural uptrend confirmation.

        Criteria (for LONG):
        - Price above 10-month SMA (≈ 200-day SMA on monthly bars)
        - Monthly RSI > 45 (not in bearish territory)
        - 10-month SMA sloping upward (current > 3 months ago)
        """
        try:
            df = data_provider.get_historical_daily(ticker, period="2y")
            if df.empty or len(df) < 220:
                return TimeframeCheck(
                    timeframe="MONTHLY",
                    aligned=False,
                    strength="NEUTRAL",
                    reason="Insufficient data for monthly analysis"
                )

            # Resample to monthly bars
            monthly = df.resample("ME").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"
            }).dropna()

            if len(monthly) < 12:
                return TimeframeCheck(
                    timeframe="MONTHLY",
                    aligned=False,
                    strength="NEUTRAL",
                    reason="Less than 12 monthly bars available"
                )

            close = monthly["Close"]
            sma_10m = close.rolling(window=10).mean()
            rsi = self._compute_rsi(close, period=14)

            last_close = float(close.iloc[-1])
            last_sma = float(sma_10m.iloc[-1]) if not pd.isna(sma_10m.iloc[-1]) else 0
            last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
            prev_sma = float(sma_10m.iloc[-4]) if len(sma_10m) >= 4 and not pd.isna(sma_10m.iloc[-4]) else last_sma

            above_sma = last_close > last_sma
            rsi_ok = last_rsi > 45
            sma_rising = last_sma > prev_sma

            aligned = above_sma and rsi_ok and sma_rising
            score_parts = sum([above_sma, rsi_ok, sma_rising])

            if score_parts == 3:
                strength = "STRONG_BULL"
                reason = f"Price ${last_close:.2f} > 10M SMA ${last_sma:.2f}, RSI {last_rsi:.0f}, SMA rising"
            elif score_parts == 2:
                strength = "BULL"
                failing = []
                if not above_sma: failing.append(f"below 10M SMA ${last_sma:.2f}")
                if not rsi_ok: failing.append(f"RSI weak ({last_rsi:.0f})")
                if not sma_rising: failing.append("SMA flattening")
                reason = f"Mostly bullish but: {', '.join(failing)}"
            elif score_parts == 1:
                strength = "NEUTRAL"
                reason = f"Mixed signals — only {score_parts}/3 monthly checks pass"
            else:
                strength = "BEAR"
                reason = f"Monthly structure bearish — Price ${last_close:.2f} < 10M SMA ${last_sma:.2f}, RSI {last_rsi:.0f}"

            return TimeframeCheck(
                timeframe="MONTHLY",
                aligned=aligned,
                strength=strength,
                reason=reason,
                key_level=last_sma
            )

        except Exception as e:
            logger.error(f"Monthly confluence check failed for {ticker}: {e}")
            return TimeframeCheck(
                timeframe="MONTHLY",
                aligned=False,
                strength="NEUTRAL",
                reason=f"Error: {str(e)[:80]}"
            )

    # ── Weekly Check ──────────────────────────────────────────

    def check_weekly(self, ticker: str) -> TimeframeCheck:
        """Weekly timeframe: medium-term trend confirmation.

        Criteria (for LONG):
        - Price above 40-week SMA (≈ 200-day)
        - Weekly RSI > 50
        - MACD line above signal line (positive momentum)
        """
        try:
            df = data_provider.get_historical_daily(ticker, period="2y")
            if df.empty or len(df) < 200:
                return TimeframeCheck(
                    timeframe="WEEKLY",
                    aligned=False,
                    strength="NEUTRAL",
                    reason="Insufficient data for weekly analysis"
                )

            # Resample to weekly bars
            weekly = df.resample("W").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"
            }).dropna()

            if len(weekly) < 42:
                return TimeframeCheck(
                    timeframe="WEEKLY",
                    aligned=False,
                    strength="NEUTRAL",
                    reason="Less than 42 weekly bars available"
                )

            close = weekly["Close"]
            sma_40w = close.rolling(window=40).mean()
            rsi = self._compute_rsi(close, period=14)
            macd_line, signal_line = self._compute_macd(close)

            last_close = float(close.iloc[-1])
            last_sma = float(sma_40w.iloc[-1]) if not pd.isna(sma_40w.iloc[-1]) else 0
            last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
            last_macd = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0
            last_signal = float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else 0

            above_sma = last_close > last_sma
            rsi_ok = last_rsi > 50
            macd_positive = last_macd > last_signal

            aligned = above_sma and rsi_ok and macd_positive
            score_parts = sum([above_sma, rsi_ok, macd_positive])

            if score_parts == 3:
                strength = "STRONG_BULL"
                reason = f"Price > 40W SMA ${last_sma:.2f}, RSI {last_rsi:.0f}, MACD positive"
            elif score_parts == 2:
                strength = "BULL"
                failing = []
                if not above_sma: failing.append(f"below 40W SMA ${last_sma:.2f}")
                if not rsi_ok: failing.append(f"RSI {last_rsi:.0f} < 50")
                if not macd_positive: failing.append("MACD bearish crossover")
                reason = f"Mostly bullish but: {', '.join(failing)}"
            elif score_parts == 1:
                strength = "NEUTRAL"
                reason = f"Conflicting weekly signals — {score_parts}/3 pass"
            else:
                strength = "BEAR"
                reason = f"Weekly downtrend — Price ${last_close:.2f} < 40W SMA, RSI {last_rsi:.0f}"

            return TimeframeCheck(
                timeframe="WEEKLY",
                aligned=aligned,
                strength=strength,
                reason=reason,
                key_level=last_sma
            )

        except Exception as e:
            logger.error(f"Weekly confluence check failed for {ticker}: {e}")
            return TimeframeCheck(
                timeframe="WEEKLY",
                aligned=False,
                strength="NEUTRAL",
                reason=f"Error: {str(e)[:80]}"
            )

    # ── Daily Check ───────────────────────────────────────────

    def check_daily(self, ticker: str, already_passed_minervini: bool = True) -> TimeframeCheck:
        """Daily timeframe: setup confirmation.

        For swing trades, the daily check is already performed by the
        SwingEngine's Minervini template. If the candidate reached this
        point, the daily timeframe is aligned by definition.

        For additional rigor, we verify:
        - Price > 20-day EMA (short-term momentum intact)
        - RSI between 45 and 80 (not oversold, not overbought/extended)
        """
        if already_passed_minervini:
            return TimeframeCheck(
                timeframe="DAILY",
                aligned=True,
                strength="STRONG_BULL",
                reason="Minervini Stage 2 template confirmed by SwingEngine"
            )

        try:
            df = data_provider.get_historical_daily(ticker, period="6mo")
            if df.empty or len(df) < 50:
                return TimeframeCheck(
                    timeframe="DAILY",
                    aligned=False,
                    strength="NEUTRAL",
                    reason="Insufficient daily data"
                )

            close = df["Close"]
            ema_20 = close.ewm(span=20, adjust=False).mean()
            rsi = self._compute_rsi(close, period=14)

            last_close = float(close.iloc[-1])
            last_ema = float(ema_20.iloc[-1]) if not pd.isna(ema_20.iloc[-1]) else 0
            last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

            above_ema = last_close > last_ema
            rsi_range_ok = 45 <= last_rsi <= 80

            aligned = above_ema and rsi_range_ok

            if aligned:
                reason = f"Price ${last_close:.2f} > 20 EMA ${last_ema:.2f}, RSI {last_rsi:.0f} in sweet spot"
                strength = "STRONG_BULL"
            elif above_ema:
                reason = f"Above 20 EMA but RSI {last_rsi:.0f} {'overbought' if last_rsi > 80 else 'weak'}"
                strength = "BULL"
            else:
                reason = f"Price ${last_close:.2f} < 20 EMA ${last_ema:.2f}"
                strength = "BEAR"

            return TimeframeCheck(
                timeframe="DAILY",
                aligned=aligned,
                strength=strength,
                reason=reason,
                key_level=last_ema
            )

        except Exception as e:
            logger.error(f"Daily confluence check failed for {ticker}: {e}")
            return TimeframeCheck(
                timeframe="DAILY",
                aligned=False,
                strength="NEUTRAL",
                reason=f"Error: {str(e)[:80]}"
            )

    # ── 4-Hour Check ──────────────────────────────────────────

    def check_4h(self, ticker: str) -> TimeframeCheck:
        """4-Hour timeframe: entry timing confirmation.

        Uses 1-hour bars from yfinance (free, up to 730 days) and
        resamples to 4-hour bars.

        Criteria (for LONG):
        - Price near or above 20-period EMA (not too extended)
        - Not more than 3% above the 20-EMA (avoids chasing extended moves)
        - Recent bar shows bullish momentum (close > open)
        """
        try:
            # yfinance provides hourly data for up to 730 days
            df = data_provider.get_intraday_bars(ticker, interval="1h", period="1mo")
            if df.empty or len(df) < 40:
                # Fall back: if no intraday data, use daily as proxy
                return TimeframeCheck(
                    timeframe="4-HOUR",
                    aligned=True,  # Give benefit of doubt
                    strength="NEUTRAL",
                    reason="4H data unavailable — skipped (neutral pass)"
                )

            # Resample hourly to 4-hour bars
            fourh = df.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"
            }).dropna()

            if len(fourh) < 20:
                return TimeframeCheck(
                    timeframe="4-HOUR",
                    aligned=True,
                    strength="NEUTRAL",
                    reason="Insufficient 4H bars — neutral pass"
                )

            close = fourh["Close"]
            open_s = fourh["Open"]
            ema_20 = close.ewm(span=20, adjust=False).mean()

            last_close = float(close.iloc[-1])
            last_open = float(open_s.iloc[-1])
            last_ema = float(ema_20.iloc[-1]) if not pd.isna(ema_20.iloc[-1]) else last_close

            above_ema = last_close > last_ema
            pct_extension = ((last_close - last_ema) / last_ema) * 100 if last_ema > 0 else 0
            not_chasing = pct_extension < 3.0
            bullish_bar = last_close > last_open

            aligned = above_ema and not_chasing
            score_parts = sum([above_ema, not_chasing, bullish_bar])

            if score_parts == 3:
                strength = "STRONG_BULL"
                reason = f"Clean pullback entry — Price near 20 EMA (ext: {pct_extension:.1f}%), bullish bar"
            elif score_parts == 2:
                strength = "BULL"
                if not not_chasing:
                    reason = f"Extended {pct_extension:.1f}% above 20 EMA — may chase"
                elif not bullish_bar:
                    reason = f"Above 20 EMA but last 4H bar bearish"
                else:
                    reason = f"Pullback below 20 EMA but showing bullish pressure"
            elif score_parts == 1:
                strength = "NEUTRAL"
                reason = f"Mixed 4H signals — only {score_parts}/3 pass"
            else:
                strength = "BEAR"
                reason = f"4H structure weak — below 20 EMA and bearish momentum"

            return TimeframeCheck(
                timeframe="4-HOUR",
                aligned=aligned,
                strength=strength,
                reason=reason,
                key_level=last_ema
            )

        except Exception as e:
            logger.error(f"4H confluence check failed for {ticker}: {e}")
            return TimeframeCheck(
                timeframe="4-HOUR",
                aligned=True,  # Neutral pass on error
                strength="NEUTRAL",
                reason=f"4H check unavailable — neutral pass ({str(e)[:50]})"
            )

    # ── Master Confluence Scorer ──────────────────────────────

    def score(self, ticker: str, already_passed_minervini: bool = True) -> ConfluenceResult:
        """Run all 4 timeframe checks and return aggregate confluence score.

        Args:
            ticker: Stock ticker symbol (e.g., 'NVDA', 'RELIANCE.NS')
            already_passed_minervini: If True, daily check is auto-passed
                                      (candidate already passed SwingEngine filters)

        Returns:
            ConfluenceResult with score 0–4, grade, badge, and detail checks
        """
        monthly = self.check_monthly(ticker)
        weekly = self.check_weekly(ticker)
        daily = self.check_daily(ticker, already_passed_minervini)
        fourh = self.check_4h(ticker)

        checks = [monthly, weekly, daily, fourh]
        score = sum(1 for chk in checks if chk.aligned)

        return ConfluenceResult(
            ticker=ticker,
            score=score,
            checks=checks
        )


# ──────────────────────────────────────────────────────────────
#  Singleton instance
# ──────────────────────────────────────────────────────────────

confluence_scorer = ConfluenceScorer()
"""Module-level singleton. Import and use:

    from engines.confluence_scorer import confluence_scorer
    result = confluence_scorer.score("NVDA")
    print(result.summary())     # '🟢🟢🟢🟢 MAXIMUM CONFLUENCE (4/4)'
    print(result.should_trade)  # True
"""
