"""Intraday Trading Engine.

Implements:
- 15-Minute Opening Range Breakout (ORB)
- VWAP Pullback & Momentum Continuation
- Relative Volume (RVOL > 1.8) Surge Filter
- Bollinger Volatility Squeeze Breakouts
- Automatic Intraday Stop Loss & Target calculations
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
import pandas as pd
from config.settings import intraday_config
from data.provider import data_provider
from ml.features import compute_all_intraday_features
from ml.time_predictor import timeline_predictor, HoldingPrediction
from risk.manager import RiskManager, TradeOrderTicket

logger = logging.getLogger(__name__)


@dataclass
class IntradayCandidate:
    ticker: str
    last_price: float
    direction: str          # 'LONG' or 'SHORT'
    pattern: str
    confidence_score: float # 0 to 100
    stop_loss: float
    target_1: float
    target_2: float
    rvol: float
    ticket: TradeOrderTicket
    summary: str
    time_prediction: Optional[HoldingPrediction] = None


class IntradayEngine:
    def __init__(self, risk_manager: Optional[RiskManager] = None):
        self.risk_manager = risk_manager or RiskManager()

    def analyze_ticker(self, ticker: str, df: Optional[pd.DataFrame] = None) -> Optional[IntradayCandidate]:
        """Runs intraday screening logic on 5-minute bars."""
        if df is None:
            df = data_provider.get_intraday_bars(ticker, interval="5m", period="5d")

        if df.empty or len(df) < 15:
            return None

        df = compute_all_intraday_features(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        last_price = float(last["Close"])
        rvol = float(last.get("RVOL", 1.0))
        vwap = float(last.get("VWAP", last_price))
        atr = float(last.get("ATR_14", last_price * 0.005))
        orb_high = float(last.get("ORB_High_15m", 0.0))
        orb_low = float(last.get("ORB_Low_15m", 0.0))

        # Check for trade setups
        direction = None
        pattern = None
        score = 65.0
        stop_loss = 0.0

        # Strategy 1: Opening Range Breakout (ORB 15-min) Long
        if orb_high > 0 and last_price > orb_high and prev["Close"] <= orb_high and rvol >= intraday_config.min_rvol:
            direction = "LONG"
            pattern = "15m Opening Range Breakout (ORB) Long"
            score = 85.0
            stop_loss = orb_high - (1.0 * atr)

        # Strategy 2: VWAP Pullback Bounce Long
        elif last_price > vwap and abs(last_price - vwap) / vwap <= 0.006 and last_price > last["Open"] and rvol >= 1.3:
            direction = "LONG"
            pattern = "VWAP Trend Pullback Bounce"
            score = 80.0
            stop_loss = min(vwap - (0.8 * atr), float(last["Low"]))

        # Strategy 3: Bollinger Band Squeeze Expansion Long
        elif last.get("BB_Bandwidth", 1.0) < 0.015 and last_price > last.get("BB_Upper", last_price) and rvol >= 1.5:
            direction = "LONG"
            pattern = "Volatility Squeeze Breakout"
            score = 82.0
            stop_loss = last_price - (1.2 * atr)

        # Strategy 4: Opening Range Breakdown (ORB Short)
        elif orb_low > 0 and last_price < orb_low and prev["Close"] >= orb_low and rvol >= intraday_config.min_rvol:
            direction = "SHORT"
            pattern = "15m Opening Range Breakdown (ORB) Short"
            score = 85.0
            stop_loss = orb_low + (1.0 * atr)

        if not direction or not pattern:
            return None

        # Intraday risk protection: Stop must be within 0.4% - 2.5% of entry
        pct_risk = abs(last_price - stop_loss) / last_price
        if pct_risk > 0.025:
            stop_loss = last_price * (0.98 if direction == "LONG" else 1.02)
        elif pct_risk < 0.003:
            stop_loss = last_price - (1.2 * atr) if direction == "LONG" else last_price + (1.2 * atr)

        # Calculate trade ticket
        ticket = self.risk_manager.calculate_trade_ticket(
            ticker=ticker,
            entry_price=last_price,
            stop_loss=stop_loss,
            timeframe="INTRADAY",
            direction=direction
        )

        if not ticket.is_valid_risk:
            return None

        time_pred = timeline_predictor.predict(
            ticker=ticker,
            entry_price=last_price,
            stop_loss=ticket.stop_loss,
            target_1=ticket.target_1,
            target_2=ticket.target_2,
            timeframe="INTRADAY",
            atr=atr,
            rvol=rvol,
            pattern=pattern
        )

        return IntradayCandidate(
            ticker=ticker,
            last_price=last_price,
            direction=direction,
            pattern=pattern,
            confidence_score=min(95.0, score),
            stop_loss=ticket.stop_loss,
            target_1=ticket.target_1,
            target_2=ticket.target_2,
            rvol=round(rvol, 2),
            ticket=ticket,
            summary=f"{pattern} | RVOL: {rvol:.1f}x | Stop: {ticket.stop_loss:.2f}",
            time_prediction=time_pred
        )

    def scan_universe(self, tickers: List[str]) -> List[IntradayCandidate]:
        """Scans a list of liquid tickers for intraday setups."""
        candidates = []
        for ticker in tickers:
            try:
                candidate = self.analyze_ticker(ticker)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.error(f"Error analyzing intraday candidate {ticker}: {e}")

        candidates.sort(key=lambda x: x.confidence_score, reverse=True)
        return candidates
