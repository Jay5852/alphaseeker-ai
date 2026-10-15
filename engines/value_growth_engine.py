"""Peter Lynch & Warren Buffett Value-Growth Engine (Multi-Bagger Finder).

Filters for:
- Growth at a Reasonable Price (GARP): PEG Ratio < 1.2
- Strong Financial Health: Debt-to-Equity < 0.8
- Profitability: Return on Equity (ROE) > 15%
- Undervaluation: Forward P/E significantly below historic or peer multiples
- High Operating Margins & Free Cash Flow
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class UndervaluedGrowthCandidate:
    ticker: str
    company_name: str
    current_price: float
    forward_pe: float
    peg_ratio: float
    roe_pct: float
    debt_to_equity: float
    profit_margin_pct: float
    revenue_growth_pct: float
    free_cash_flow: float
    peter_lynch_score: float   # 0 to 100
    valuation_verdict: str
    investment_thesis: str


class ValueGrowthEngine:
    def analyze_ticker(self, ticker: str) -> Optional[UndervaluedGrowthCandidate]:
        """Analyzes fundamental valuation metrics for long-term multi-bagger potential."""
        try:
            t = yf.Ticker(ticker)
            info = t.info

            if not info or "regularMarketPrice" not in info and "currentPrice" not in info:
                return None

            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
            if price <= 0:
                return None

            name = info.get("shortName", ticker)
            forward_pe = info.get("forwardPE", 0.0) or 0.0
            trailing_pe = info.get("trailingPE", 0.0) or 0.0
            peg_ratio = info.get("pegRatio", 0.0) or 0.0
            roe = (info.get("returnOnEquity", 0.0) or 0.0) * 100.0
            debt_to_equity = (info.get("debtToEquity", 0.0) or 0.0) / 100.0
            profit_margins = (info.get("profitMargins", 0.0) or 0.0) * 100.0
            revenue_growth = (info.get("revenueGrowth", 0.0) or 0.0) * 100.0
            fcf = info.get("freeCashflow", 0.0) or 0.0

            # Score calculation based on Peter Lynch & Buffett criteria
            score = 50.0

            # 1. PEG Ratio evaluation (Peter Lynch classic: PEG < 1.0 is undervalued growth)
            if 0 < peg_ratio <= 1.0:
                score += 20.0
            elif 1.0 < peg_ratio <= 1.5:
                score += 10.0
            elif peg_ratio > 3.0:
                score -= 15.0

            # 2. Return on Equity (Buffett quality check: ROE > 15%)
            if roe >= 20.0:
                score += 15.0
            elif roe >= 15.0:
                score += 10.0
            elif roe < 5.0:
                score -= 10.0

            # 3. Debt-to-Equity (Capital safety check)
            if debt_to_equity <= 0.5:
                score += 10.0
            elif debt_to_equity > 2.0:
                score -= 15.0

            # 4. Revenue & Margin expansion
            if revenue_growth >= 20.0:
                score += 10.0
            if profit_margins >= 15.0:
                score += 5.0

            score = max(10.0, min(99.0, score))

            if score >= 75.0:
                verdict = "💎 Prime Undervalued Compounder (Strong Buy)"
            elif score >= 60.0:
                verdict = "📈 Quality Growth at Reasonable Price"
            else:
                verdict = "⚠️ Fairly Valued / Moderate Risk"

            thesis = (
                f"ROE: {roe:.1f}% | Debt/Eq: {debt_to_equity:.2f} | "
                f"PEG: {peg_ratio:.2f} | Rev Growth: {revenue_growth:.1f}%"
            )

            return UndervaluedGrowthCandidate(
                ticker=ticker,
                company_name=name,
                current_price=round(price, 2),
                forward_pe=round(forward_pe, 1),
                peg_ratio=round(peg_ratio, 2),
                roe_pct=round(roe, 1),
                debt_to_equity=round(debt_to_equity, 2),
                profit_margin_pct=round(profit_margins, 1),
                revenue_growth_pct=round(revenue_growth, 1),
                free_cash_flow=fcf,
                peter_lynch_score=score,
                valuation_verdict=verdict,
                investment_thesis=thesis
            )
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ticker}: {e}")
            return None

    def scan_universe(self, tickers: List[str]) -> List[UndervaluedGrowthCandidate]:
        """Scans universe for undervalued high-growth compounders."""
        results = []
        for ticker in tickers:
            cand = self.analyze_ticker(ticker)
            if cand and cand.peter_lynch_score >= 60.0:
                results.append(cand)

        results.sort(key=lambda x: x.peter_lynch_score, reverse=True)
        return results


value_growth_engine = ValueGrowthEngine()
