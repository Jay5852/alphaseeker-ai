"""Swing Trading Engine (Positional Multi-Month Horizon).

Implements:
- Mark Minervini 8-Point Trend Template (Stage 2 Uptrend)
- Volatility Contraction Pattern (VCP) Detection
- 50-day SMA Pullback Bounces
- Risk-Reward & Position Sizing validation
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import pandas as pd
from config.settings import swing_config, confluence_config
from data.provider import data_provider
from ml.features import compute_all_swing_features
from ml.time_predictor import timeline_predictor, HoldingPrediction
from ml.meta_labeler import meta_labeler, MetaLabelResult
from engines.confluence_scorer import confluence_scorer, ConfluenceResult
from risk.manager import RiskManager, TradeOrderTicket

logger = logging.getLogger(__name__)


@dataclass
class SwingCandidate:
    ticker: str
    last_price: float
    pattern: str
    confidence_score: float  # 0 to 100
    stop_loss: float
    target_1: float
    target_2: float
    trend_template_passed: bool
    pct_from_52w_high: float
    rvol: float
    ticket: TradeOrderTicket
    summary: str
    time_prediction: Optional[HoldingPrediction] = None
    meta_label: Optional[MetaLabelResult] = None
    confluence: Optional[ConfluenceResult] = None


class SwingEngine:
    def __init__(self, risk_manager: Optional[RiskManager] = None):
        self.risk_manager = risk_manager or RiskManager()

    def check_minervini_trend_template(self, row: pd.Series, prev_20_row: Optional[pd.Series] = None) -> Tuple[bool, List[str]]:
        """
        Validates Mark Minervini's Stage 2 Trend criteria:
        1. Price > 150 SMA and 200 SMA
        2. 150 SMA > 200 SMA
        3. 200 SMA is trending up (current > 20-40 days ago)
        4. 50 SMA > 150 SMA and 200 SMA
        5. Price > 50 SMA
        6. Price >= 30% above 52-week low
        7. Price within 25% of 52-week high
        """
        reasons = []
        c = row["Close"]
        sma50 = row.get("SMA_50")
        sma150 = row.get("SMA_150")
        sma200 = row.get("SMA_200")
        pct_high = row.get("Pct_From_52W_High", 100)
        pct_low = row.get("Pct_Above_52W_Low", 0)

        if pd.isna(sma50) or pd.isna(sma150) or pd.isna(sma200):
            return False, ["Insufficient data for SMAs"]

        # 1. Price > 150 and 200 SMA
        if not (c > sma150 and c > sma200):
            return False, ["Price below 150 or 200 SMA"]

        # 2. 150 SMA > 200 SMA
        if not (sma150 > sma200):
            return False, ["150 SMA below 200 SMA"]

        # 3. 200 SMA trending up
        if prev_20_row is not None and not pd.isna(prev_20_row.get("SMA_200")):
            if sma200 < prev_20_row["SMA_200"]:
                return False, ["200 SMA sloping downward"]

        # 4. 50 SMA > 150 and 200 SMA
        if not (sma50 > sma150 and sma50 > sma200):
            return False, ["50 SMA not leading longer SMAs"]

        # 5. Price > 50 SMA
        if not (c > sma50):
            return False, ["Price below 50 SMA"]

        # 6. Price within 25% of 52W High
        if pct_high > swing_config.max_pct_from_52w_high:
            return False, [f"Too far from 52-week high ({pct_high:.1f}%)"]

        # 7. Price at least 30% above 52W Low
        if pct_low < swing_config.min_pct_above_52w_low:
            return False, [f"Not enough distance from 52-week low ({pct_low:.1f}%)"]

        return True, ["Passed all 7 Minervini Stage-2 Criteria"]

    def analyze_ticker(self, ticker: str, df: Optional[pd.DataFrame] = None) -> Optional[SwingCandidate]:
        """Runs full swing analysis on a ticker."""
        if df is None:
            df = data_provider.get_historical_daily(ticker, period="1y")

        if df.empty or len(df) < 200:
            return None

        df = compute_all_swing_features(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev_20 = df.iloc[-21] if len(df) >= 21 else None

        passed_trend, notes = self.check_minervini_trend_template(last, prev_20)
        if not passed_trend:
            return None

        last_close = float(last["Close"])
        atr = float(last["ATR_14"]) if not pd.isna(last["ATR_14"]) else (last_close * 0.02)
        rvol = float(last["RVOL"]) if not pd.isna(last["RVOL"]) else 1.0

        pattern = "Stage 2 Momentum Continuation"
        score = 70.0

        # Pattern 1: Volatility Contraction Pattern (VCP) Breakout
        contract_ratio = last.get("ATR_Contract_Ratio", 1.0)
        if contract_ratio < 0.75 and rvol >= 1.2:
            pattern = "VCP Volatility Contraction Breakout"
            score += 15.0

        # Pattern 2: 50 SMA Bounce (Price touched near 50 SMA and closed strong)
        sma50 = last.get("SMA_50", 0)
        if 0 <= (last_close - sma50) / sma50 <= 0.03 and last_close > prev["Close"]:
            pattern = "50-Day SMA Pullback Bounce"
            score += 10.0

        # Pattern 3: Fresh 52-Week High Breakout
        pct_from_high = float(last.get("Pct_From_52W_High", 10.0))
        if pct_from_high <= 2.0 and rvol >= 1.3:
            pattern = "52-Week High Volume Breakout"
            score += 15.0

        # Calculate Stop Loss using recent swing structure or 1.5x ATR
        lowest_recent = df["Low"].iloc[-10:].min()
        atr_stop = last_close - (1.5 * atr)
        stop_loss = max(lowest_recent, atr_stop)

        # Ensure stop is at least 2% below but not more than 8% below entry for swing
        if (last_close - stop_loss) / last_close > 0.08:
            stop_loss = last_close * 0.93  # 7% max swing stop
        elif (last_close - stop_loss) / last_close < 0.025:
            stop_loss = last_close - (1.5 * atr)

        # Generate trade order ticket through RiskManager
        ticket = self.risk_manager.calculate_trade_ticket(
            ticker=ticker,
            entry_price=last_close,
            stop_loss=stop_loss,
            timeframe="SWING",
            direction="LONG"
        )

        if not ticket.is_valid_risk:
            return None

        confidence = min(98.0, score)

        # Upgrade D: Intelligent Holding Period & Timeline Prediction
        time_pred = timeline_predictor.predict(
            ticker=ticker,
            entry_price=last_close,
            stop_loss=ticket.stop_loss,
            target_1=ticket.target_1,
            target_2=ticket.target_2,
            timeframe="SWING",
            atr=atr,
            rvol=rvol,
            pattern=pattern
        )

        # Upgrade B: Marcos López de Prado Quantitative Meta-Labeling
        feats = meta_labeler.extract_features(
            df=df,
            last_price=last_close,
            stop_loss=ticket.stop_loss,
            target_1=ticket.target_1,
            rvol=rvol,
            pattern=pattern,
            market_regime_code=2
        )
        meta_res = meta_labeler.predict_trade_probability(feats)

        # Improvement G: Multi-Timeframe Confluence Scoring (Monthly/Weekly/Daily/4H)
        conf_res = confluence_scorer.score(ticker, already_passed_minervini=True)

        if confluence_config.enabled and conf_res.score < confluence_config.min_trade_score:
            logger.info(
                f"Confluence filter rejected {ticker}: "
                f"{conf_res.score}/{conf_res.max_score} "
                f"(min {confluence_config.min_trade_score}/4 required)"
            )
            return None

        # Perfect 4/4 alignment earns a conviction bonus
        if conf_res.score == conf_res.max_score:
            confidence = min(98.0, confidence + confluence_config.perfect_score_bonus)

        return SwingCandidate(
            ticker=ticker,
            last_price=last_close,
            pattern=pattern,
            confidence_score=confidence,
            stop_loss=ticket.stop_loss,
            target_1=ticket.target_1,
            target_2=ticket.target_2,
            trend_template_passed=True,
            pct_from_52w_high=pct_from_high,
            rvol=round(rvol, 2),
            ticket=ticket,
            summary=f"{pattern} | RVOL: {rvol:.1f}x | Minervini Stage 2 Confirmed | Confluence {conf_res.score}/4",
            time_prediction=time_pred,
            meta_label=meta_res,
            confluence=conf_res
        )

    def scan_universe(self, tickers: List[str]) -> List[SwingCandidate]:
        """Scans a list of tickers and returns candidates ranked by confidence score."""
        candidates = []
        for ticker in tickers:
            try:
                candidate = self.analyze_ticker(ticker)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.error(f"Error analyzing swing candidate {ticker}: {e}")

        # Rank descending by confidence score
        candidates.sort(key=lambda x: x.confidence_score, reverse=True)
        return candidates
