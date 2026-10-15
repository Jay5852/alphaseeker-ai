"""Market Regime Classifier.

Determines the broader macro-market environment:
- TRENDING_BULLISH: High breakout success rate. Full position sizes.
- TRENDING_BEARISH: Suppress long breakout signals. Cash or short bias.
- CHOPPY_SIDEWAYS: Breakouts tend to fail. Favor mean-reversion & tight trailing stops.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
from data.provider import data_provider
from config.universes import BENCHMARK_TICKERS
from ml.features import compute_moving_averages, compute_atr, compute_rsi


@dataclass
class MarketRegime:
    benchmark: str
    status: str              # 'TRENDING_BULLISH', 'TRENDING_BEARISH', 'CHOPPY_SIDEWAYS'
    current_price: float
    sma_50: float
    sma_200: float
    rsi_14: float
    guidance: str


class RegimeClassifier:
    def classify_market(self, market: str = "US") -> MarketRegime:
        """Classifies the market regime using the benchmark index."""
        ticker = BENCHMARK_TICKERS.get(market.upper(), "^GSPC")
        df = data_provider.get_historical_daily(ticker, period="1y")

        if df.empty or len(df) < 50:
            return MarketRegime(
                benchmark=ticker,
                status="UNKNOWN",
                current_price=0.0,
                sma_50=0.0,
                sma_200=0.0,
                rsi_14=50.0,
                guidance="Insufficient benchmark data to determine regime."
            )

        df = compute_moving_averages(df)
        df = compute_rsi(df, period=14)
        last = df.iloc[-1]

        c = float(last["Close"])
        sma50 = float(last.get("SMA_50", c))
        sma200 = float(last.get("SMA_200", c)) if not pd.isna(last.get("SMA_200")) else sma50
        rsi = float(last.get("RSI_14", 50.0))

        # Regime determination logic
        if c > sma50 and sma50 > sma200 and rsi > 50:
            status = "TRENDING_BULLISH"
            guidance = "Market is in confirmed uptrend. High probability for Stage 2 breakouts & momentum continuation."
        elif c < sma50 and c < sma200:
            status = "TRENDING_BEARISH"
            guidance = "Market is in downtrend. Long breakouts have high failure rate. Preserve capital or trade defensive."
        else:
            status = "CHOPPY_SIDEWAYS"
            guidance = "Market is in rangebound/choppy consolidation. Reduce position sizes and take profits quickly."

        return MarketRegime(
            benchmark=ticker,
            status=status,
            current_price=round(c, 2),
            sma_50=round(sma50, 2),
            sma_200=round(sma200, 2),
            rsi_14=round(rsi, 2),
            guidance=guidance
        )


regime_classifier = RegimeClassifier()
