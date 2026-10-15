"""Universal Market Data Provider for US & Indian (NSE) stocks."""

import logging
from typing import Optional, Dict
import pandas as pd
import yfinance as yf
from data.base import MarketDataProvider

logger = logging.getLogger(__name__)


class UniversalDataProvider(MarketDataProvider):
    """
    Handles data ingestion for both US tickers (e.g. 'NVDA') 
    and Indian NSE tickers (e.g. 'RELIANCE.NS').
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, pd.DataFrame] = {}

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flattens MultiIndex columns and normalizes column names."""
        if df.empty:
            return df
        
        # In newer yfinance versions, columns can be MultiIndex (Price, Ticker)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
            
        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })

        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in required_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Close"])
        return df

    def get_historical_daily(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Fetch historical daily OHLCV dataframe."""
        cache_key = f"daily_{ticker}_{period}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        try:
            raw = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True
            )
            df = self._clean_df(raw)
            if not df.empty:
                self._cache[cache_key] = df
            return df
        except Exception as e:
            logger.error(f"Error fetching daily data for {ticker}: {e}")
            return pd.DataFrame()

    def get_intraday_bars(self, ticker: str, interval: str = "5m", period: str = "5d") -> pd.DataFrame:
        """Fetch intraday OHLCV dataframe (1m, 5m, 15m)."""
        cache_key = f"intraday_{ticker}_{interval}_{period}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        try:
            raw = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True
            )
            df = self._clean_df(raw)
            if not df.empty:
                self._cache[cache_key] = df
            return df
        except Exception as e:
            logger.error(f"Error fetching intraday data for {ticker}: {e}")
            return pd.DataFrame()

    def get_latest_quote(self, ticker: str) -> dict:
        """Fetch latest price snapshot."""
        try:
            t = yf.Ticker(ticker)
            fast_info = getattr(t, "fast_info", None)
            if fast_info:
                return {
                    "last_price": getattr(fast_info, "last_price", 0.0),
                    "previous_close": getattr(fast_info, "previous_close", 0.0),
                    "currency": getattr(fast_info, "currency", "USD")
                }
            df = self.get_historical_daily(ticker, period="5d")
            if not df.empty:
                last_row = df.iloc[-1]
                prev_row = df.iloc[-2] if len(df) > 1 else last_row
                return {
                    "last_price": float(last_row["Close"]),
                    "previous_close": float(prev_row["Close"]),
                    "currency": "INR" if ".NS" in ticker else "USD"
                }
        except Exception as e:
            logger.error(f"Error fetching latest quote for {ticker}: {e}")
            
        return {"last_price": 0.0, "previous_close": 0.0, "currency": "USD"}


data_provider = UniversalDataProvider()
