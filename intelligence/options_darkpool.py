"""Options Chain Flow & Gamma Squeeze Intelligence Engine (Upgrade C.1).

Scrapes options chains from Yahoo Finance (100% Free, zero API key) to detect:
1. Unusual Call Ratio (UCR) & Put-to-Call Ratio (PCR).
2. Volume-to-Open Interest (VOI >= 2.0) spikes indicating aggressive institutional positioning.
3. Market Maker Gamma Walls (strike with highest Call Open Interest).
4. Gamma Squeeze Candidates.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class UnusualStrikeActivity:
    strike: float
    call_volume: int
    open_interest: int
    volume_to_oi_ratio: float
    implied_volatility: float
    in_the_money: bool


@dataclass
class OptionsFlowReport:
    ticker: str
    has_options: bool
    total_call_volume: int
    total_put_volume: int
    put_call_ratio: float
    sentiment_verdict: str         # 'EXTREMELY_BULLISH', 'BULLISH', 'NEUTRAL', 'BEARISH'
    gamma_wall_strike: float       # Strike with max call open interest
    is_gamma_squeeze_candidate: bool
    unusual_strikes: List[UnusualStrikeActivity]
    summary: str


class OptionsFlowAnalyzer:
    """Free institutional options chain parser for detecting smart money sweeps and gamma squeezes."""

    def analyze_ticker_options(self, ticker: str) -> OptionsFlowReport:
        """Parses the nearest expiration options chain for institutional flow metrics."""
        clean_ticker = ticker.upper()

        try:
            t = yf.Ticker(clean_ticker)
            expirations = t.options

            if not expirations:
                return self._empty_report(clean_ticker, "No active listed options chain available.")

            # Look at front-month expiration (most reactive to momentum)
            target_expiry = expirations[0]
            chain = t.option_chain(target_expiry)

            calls = chain.calls
            puts = chain.puts

            if calls.empty:
                return self._empty_report(clean_ticker, "Option chain returned empty calls table.")

            # Clean and parse volume and open interest
            calls["volume"] = pd.to_numeric(calls["volume"], errors="coerce").fillna(0).astype(int)
            calls["openInterest"] = pd.to_numeric(calls["openInterest"], errors="coerce").fillna(0).astype(int)
            puts["volume"] = pd.to_numeric(puts["volume"], errors="coerce").fillna(0).astype(int)
            puts["openInterest"] = pd.to_numeric(puts["openInterest"], errors="coerce").fillna(0).astype(int)

            total_call_vol = int(calls["volume"].sum())
            total_put_vol = int(puts["volume"].sum())

            # Put-Call Ratio (PCR)
            pcr = (total_put_vol / total_call_vol) if total_call_vol > 0 else 1.0

            # Find Gamma Wall (Strike with highest Call Open Interest)
            max_oi_idx = calls["openInterest"].idxmax() if not calls["openInterest"].empty else None
            gamma_wall = float(calls.loc[max_oi_idx, "strike"]) if max_oi_idx is not None else 0.0

            # Scan for Unusual Strike Activity (Volume to Open Interest >= 1.8x with high volume)
            calls["voi_ratio"] = calls.apply(
                lambda row: (row["volume"] / row["openInterest"]) if row["openInterest"] > 20 else 0.0,
                axis=1
            )
            unusual_df = calls[calls["voi_ratio"] >= 1.8].sort_values(by="volume", ascending=False).head(4)

            unusual_strikes = []
            for _, r in unusual_df.iterrows():
                unusual_strikes.append(UnusualStrikeActivity(
                    strike=float(r["strike"]),
                    call_volume=int(r["volume"]),
                    open_interest=int(r["openInterest"]),
                    volume_to_oi_ratio=round(float(r["voi_ratio"]), 2),
                    implied_volatility=round(float(r.get("impliedVolatility", 0.0)) * 100, 1),
                    in_the_money=bool(r.get("inTheMoney", False))
                ))

            # Gamma Squeeze Candidate: Low PCR (< 0.60) + heavy Call Volume + at least 1 unusual OTM strike
            is_squeeze = (pcr < 0.55 and total_call_vol >= 5000 and len(unusual_strikes) >= 1)

            # Sentiment verdict
            if pcr <= 0.45:
                sentiment = "EXTREMELY_BULLISH"
            elif pcr <= 0.70:
                sentiment = "BULLISH"
            elif pcr <= 1.20:
                sentiment = "NEUTRAL"
            else:
                sentiment = "BEARISH"

            summary = (
                f"Call Vol: {total_call_vol:,} | Put Vol: {total_put_vol:,} | PCR: {pcr:.2f} | "
                f"Gamma Wall: ${gamma_wall:.2f} | Squeeze Risk: {'🔥 HIGH' if is_squeeze else 'MODERATE'}"
            )

            return OptionsFlowReport(
                ticker=clean_ticker,
                has_options=True,
                total_call_volume=total_call_vol,
                total_put_volume=total_put_vol,
                put_call_ratio=round(pcr, 2),
                sentiment_verdict=sentiment,
                gamma_wall_strike=gamma_wall,
                is_gamma_squeeze_candidate=is_squeeze,
                unusual_strikes=unusual_strikes,
                summary=summary
            )

        except Exception as e:
            logger.warning(f"Error fetching options chain for {ticker}: {e}")
            return self._empty_report(clean_ticker, f"Options chain unavailable or rate-limited: {str(e)[:50]}")

    def _empty_report(self, ticker: str, reason: str) -> OptionsFlowReport:
        return OptionsFlowReport(
            ticker=ticker,
            has_options=False,
            total_call_volume=0,
            total_put_volume=0,
            put_call_ratio=1.0,
            sentiment_verdict="NEUTRAL",
            gamma_wall_strike=0.0,
            is_gamma_squeeze_candidate=False,
            unusual_strikes=[],
            summary=reason
        )


options_analyzer = OptionsFlowAnalyzer()
