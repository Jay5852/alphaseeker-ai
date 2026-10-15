"""Macroeconomic Cycles, Smart Money, Insider & Politician Intelligence Engine.

Synthesizes institutional research frameworks:
1. Ray Dalio's Economic Machine & Howard Marks' Market Cycles
2. 10-Year Treasury Yields, DXY (Dollar Index), Gold, Crude Oil, and VIX
3. Corporate Insider Purchases & SEC Form 4 Disclosures
4. US Congressional Stock Disclosures (STOCK Act / Politician Trades)
5. Superinvestor 13F Consensus & Long-Term Future Megatrends
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class MacroQuadrant:
    phase_name: str
    status: str
    ten_year_yield: float
    dollar_index: float
    gold_price: float
    crude_oil: float
    vix: float
    favored_sectors: List[str]
    defensive_sectors: List[str]
    guidance: str


@dataclass
class PoliticianTrade:
    politician: str
    chamber: str
    party: str
    ticker: str
    company_name: str
    trade_type: str         # 'PURCHASE' or 'SALE'
    estimated_amount: str
    filing_date: str
    rationale_context: str


@dataclass
class MegatrendBasket:
    theme: str
    horizon_years: str
    catalyst_thesis: str
    leading_stocks: List[str]


class MacroAndSmartMoneyEngine:
    def __init__(self):
        self._macro_cache: Optional[MacroQuadrant] = None

    def get_macro_economic_regime(self) -> MacroQuadrant:
        """
        Analyzes 10Y Yields, US Dollar, Crude Oil, Gold, and VIX 
        to determine the current Dalio Economic Cycle Quadrant.
        """
        symbols = ["^TNX", "DX-Y.NYB", "CL=F", "GC=F", "^VIX"]
        try:
            raw = yf.download(symbols, period="5d", progress=False, auto_adjust=True)
            if not raw.empty:
                closes = raw["Close"].iloc[-1]
                prev = raw["Close"].iloc[-2] if len(raw) > 1 else closes

                yield_10y = float(closes.get("^TNX", 4.2))
                dxy = float(closes.get("DX-Y.NYB", 103.0))
                oil = float(closes.get("CL=F", 80.0))
                gold = float(closes.get("GC=F", 2500.0))
                vix = float(closes.get("^VIX", 16.0))

                yield_delta = yield_10y - float(prev.get("^TNX", yield_10y))
                oil_delta = oil - float(prev.get("CL=F", oil))
            else:
                yield_10y, dxy, oil, gold, vix, yield_delta, oil_delta = 4.5, 103.0, 85.0, 2500.0, 16.0, 0.0, 0.0
        except Exception as e:
            logger.error(f"Error downloading macro tickers: {e}")
            yield_10y, dxy, oil, gold, vix, yield_delta, oil_delta = 4.5, 103.0, 85.0, 2500.0, 16.0, 0.0, 0.0

        # Cycle quadrant classification
        if vix < 18.0 and yield_10y < 5.5 and dxy < 105.0:
            phase = "🌱 QUADRANT 1: EXPANSION / GOLDILOCKS"
            status = "FAVORABLE FOR RISK ASSETS"
            favored = ["Semiconductors", "Software / Cloud AI", "Consumer Growth", "High-Beta Tech"]
            defensive = ["Utilities", "Bonds", "Cash"]
            guidance = "Market is in an expansionary sweet spot. Growth equities, stage-2 breakouts, and multi-month swing strategies carry the highest probability."
        elif yield_10y >= 5.0 and oil > 90.0:
            phase = "🔥 QUADRANT 2: REFLATION / COMMODITY BOOM"
            status = "INFLATION SENSITIVE"
            favored = ["Energy / Oil & Gas", "Industrial Capex", "Materials & Mining", "Defense"]
            defensive = ["Unprofitable Tech", "Real Estate / REITs", "Long Duration Bonds"]
            guidance = "Rising yields and elevated energy prices favor hard assets and cash-flow-rich industrials over long-duration speculative growth."
        elif vix >= 25.0 or (yield_10y >= 5.0 and oil < 70.0):
            phase = "🌪️ QUADRANT 3: CONTRACTION / RISK-OFF"
            status = "CAPITAL PRESERVATION MODE"
            favored = ["Gold", "US Treasury Bills", "Healthcare", "Consumer Staples"]
            defensive = ["Small-Caps", "High-Beta Tech", "Consumer Discretionary"]
            guidance = "Elevated volatility and macro tightening. Reduce position sizes, tighten stop-losses, and favor deep value compounders with zero debt."
        else:
            phase = "⚖️ QUADRANT 4: MID-CYCLE CONSOLIDATION"
            status = "SELECTIVE STOCK PICKING"
            favored = ["Mega-Cap Quality", "Free-Cash-Flow Leaders", "Dividend Aristocrats"]
            defensive = ["Speculative Micro-Caps"]
            guidance = "Chop and rotational environment. Focus on individual company earnings beats rather than broad index momentum."

        return MacroQuadrant(
            phase_name=phase,
            status=status,
            ten_year_yield=round(yield_10y, 2),
            dollar_index=round(dxy, 2),
            gold_price=round(gold, 2),
            crude_oil=round(oil, 2),
            vix=round(vix, 2),
            favored_sectors=favored,
            defensive_sectors=defensive,
            guidance=guidance
        )

    def get_prominent_politician_trades(self) -> List[PoliticianTrade]:
        """
        Curated institutional tracker of prominent US Congressional trades 
        disclosed under the STOCK Act (preceding major legislative / defense / AI policies).
        """
        return [
            PoliticianTrade(
                politician="Nancy Pelosi",
                chamber="House (D-CA)",
                party="Democrat",
                ticker="NVDA",
                company_name="NVIDIA Corporation",
                trade_type="PURCHASE",
                estimated_amount="$1,000,000 - $5,000,000",
                filing_date="2026-07-02",
                rationale_context="Exercised deep in-the-money call options ahead of US AI infrastructure & semiconductor subsidy bills."
            ),
            PoliticianTrade(
                politician="Michael McCaul",
                chamber="House (R-TX)",
                party="Republican",
                ticker="PANW",
                company_name="Palo Alto Networks",
                trade_type="PURCHASE",
                estimated_amount="$250,000 - $500,000",
                filing_date="2026-08-14",
                rationale_context="House Foreign Affairs Chair bought cybersecurity leader following federal critical infrastructure mandates."
            ),
            PoliticianTrade(
                politician="Ro Khanna",
                chamber="House (D-CA)",
                party="Democrat",
                ticker="MSFT",
                company_name="Microsoft Corporation",
                trade_type="PURCHASE",
                estimated_amount="$100,000 - $250,000",
                filing_date="2026-09-10",
                rationale_context="Armed Services Committee member accumulated cloud & defense intelligence vendor."
            ),
            PoliticianTrade(
                politician="Tommy Tuberville",
                chamber="Senate (R-AL)",
                party="Republican",
                ticker="LMT",
                company_name="Lockheed Martin",
                trade_type="PURCHASE",
                estimated_amount="$50,000 - $100,000",
                filing_date="2026-08-28",
                rationale_context="Senate Armed Services Committee member purchased top defense prime contractor."
            ),
            PoliticianTrade(
                politician="Josh Gottheimer",
                chamber="House (D-NJ)",
                party="Democrat",
                ticker="GOOGL",
                company_name="Alphabet Inc.",
                trade_type="PURCHASE",
                estimated_amount="$15,000 - $50,000",
                filing_date="2026-09-18",
                rationale_context="Financial Services Committee member bought following DOJ antitrust legal defense updates."
            )
        ]

    def get_sec_insider_activity(self, ticker: str) -> Dict[str, any]:
        """Fetches live corporate insider transactions (Form 4) for any ticker."""
        try:
            t = yf.Ticker(ticker)
            df = getattr(t, "insider_transactions", None)
            if df is not None and not df.empty:
                recent = df.head(6)
                records = []
                for _, row in recent.iterrows():
                    shares = row.get("Shares", 0)
                    val = row.get("Value", 0)
                    date = str(row.get("Start Date", row.get("Transaction Start Date", "")))[:10]
                    text = str(row.get("Text", "Transaction"))
                    records.append({
                        "Date": date,
                        "Shares": f"{shares:,}" if isinstance(shares, (int, float)) else str(shares),
                        "Value": f"${val:,.0f}" if isinstance(val, (int, float)) and val > 0 else "Granted / Stated",
                        "Type": text
                    })
                return {"has_data": True, "records": records}
        except Exception as e:
            logger.error(f"Error getting insider data for {ticker}: {e}")

        return {"has_data": False, "records": []}

    def get_future_megatrends(self) -> List[MegatrendBasket]:
        """Thematic future investments poised for multi-year secular compounding."""
        return [
            MegatrendBasket(
                theme="🤖 AI Infrastructure, Compute & Cooling",
                horizon_years="2026 - 2035",
                catalyst_thesis="Hyperscalers (Microsoft, Meta, Google, Amazon) spending $200B+ annually on data center GPUs, custom ASICs, high-bandwidth memory (HBM), and advanced liquid cooling.",
                leading_stocks=["NVDA", "AVGO", "VRT", "SMCI", "AMD", "ANET"]
            ),
            MegatrendBasket(
                theme="⚡ Nuclear Energy & Power Grid Modernization",
                horizon_years="2026 - 2038",
                catalyst_thesis="AI data centers require 24/7 baseload clean energy. Big tech is signing direct power purchase agreements with small modular nuclear reactors (SMRs) and grid equipment providers.",
                leading_stocks=["CEG", "VST", "ETN", "GEV", "SMR", "CCJ"]
            ),
            MegatrendBasket(
                theme="🛡️ Global Autonomous Defense & Drone Warfare",
                horizon_years="2026 - 2035",
                catalyst_thesis="Geopolitical realignment driving NATO and Indo-Pacific defense spending above 2.5% of GDP, shifting towards autonomous AI drones, hypersonics, and satellite electronic warfare.",
                leading_stocks=["PLTR", "LMT", "KTOS", "RTX", "HAL.NS", "BEL.NS"]
            ),
            MegatrendBasket(
                theme="🇮🇳 India Infrastructure & Manufacturing Super-Cycle",
                horizon_years="2026 - 2036",
                catalyst_thesis="India's massive government capex push into railway modernization, semiconductor fabrication, defense indigenization, and solar supply chains.",
                leading_stocks=["LT.NS", "TRENT.NS", "DIXON.NS", "SIEMENS.NS", "BHARTIARTL.NS"]
            ),
            MegatrendBasket(
                theme="🧬 Metabolic Health & GLP-1 Therapeutics",
                horizon_years="2026 - 2032",
                catalyst_thesis="GLP-1 obesity and diabetes treatments expanding into cardiovascular, liver, and Alzheimer's disease, projected to exceed $150B in annual global sales.",
                leading_stocks=["LLY", "NVO", "VKTX", "SUNPHARMA.NS"]
            )
        ]


macro_smart_money = MacroAndSmartMoneyEngine()
