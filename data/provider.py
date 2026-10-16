"""Universal Market Data Provider for US & Indian (NSE) stocks.

Uses curl_cffi with browser impersonation as the primary data source to bypass
Yahoo Finance "Invalid Crumb" / HTTP 401 blocking on cloud IPs (Streamlit Cloud,
Railway, Render, etc.). Falls back to yfinance if curl_cffi is unavailable.
"""

import logging
from typing import Optional, Dict
import pandas as pd
import yfinance as yf
from curl_cffi import requests as curl_requests
from data.base import MarketDataProvider

logger = logging.getLogger(__name__)

# Browser-impersonating session to bypass Yahoo Finance crumb/401 blocking on cloud IPs
_browser_session = curl_requests.Session(impersonate="chrome")


def _fetch_yahoo_chart(ticker: str, range_param: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch Yahoo Finance chart data using curl_cffi browser impersonation.
    Bypasses the 'Invalid Crumb' / 401 errors that affect cloud IPs.
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": range_param, "interval": interval}
    try:
        resp = _browser_session.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"Yahoo chart API returned {resp.status_code} for {ticker}")
            return pd.DataFrame()
        data = resp.json()
        result = data.get("chart", {}).get("result", [None])[0]
        if result is None:
            return pd.DataFrame()

        timestamps = result.get("timestamp", [])
        indicators = result.get("indicators", {}).get("quote", [{}])[0]

        df = pd.DataFrame({
            "Open": indicators.get("open", []),
            "High": indicators.get("high", []),
            "Low": indicators.get("low", []),
            "Close": indicators.get("close", []),
            "Volume": indicators.get("volume", []),
        }, index=pd.to_datetime(timestamps, unit="s", utc=True))

        df.index.name = "Date"
        return df.dropna(subset=["Close"])
    except Exception as e:
        logger.error(f"Error fetching chart data for {ticker}: {e}")
        return pd.DataFrame()


def _fetch_latest_quote_curl(ticker: str) -> dict:
    """Fetch latest quote using curl_cffi browser impersonation."""
    try:
        df = _fetch_yahoo_chart(ticker, range_param="1d", interval="1d")
        if not df.empty:
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) > 1 else last_row
            currency = "INR" if ".NS" in ticker else "USD"
            return {
                "last_price": float(last_row["Close"]),
                "previous_close": float(prev_row["Close"]),
                "currency": currency,
            }
    except Exception as e:
        logger.error(f"Error fetching latest quote (curl) for {ticker}: {e}")
    return {"last_price": 0.0, "previous_close": 0.0, "currency": "USD"}


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

        # Primary: curl_cffi browser impersonation (bypasses Yahoo 401 on cloud)
        df = _fetch_yahoo_chart(ticker, range_param=period, interval="1d")
        if not df.empty:
            self._cache[cache_key] = df
            return df

        # Fallback: yfinance
        try:
            raw = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True,
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

        # Primary: curl_cffi browser impersonation
        df = _fetch_yahoo_chart(ticker, range_param=period, interval=interval)
        if not df.empty:
            self._cache[cache_key] = df
            return df

        # Fallback: yfinance
        try:
            raw = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
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
        # Primary: curl_cffi chart API
        quote = _fetch_latest_quote_curl(ticker)
        if quote["last_price"] > 0:
            return quote

        # Fallback: yfinance Ticker
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
                    "currency": "INR" if ".NS" in ticker else "USD",
                }
        except Exception as e:
            logger.error(f"Error fetching latest quote for {ticker}: {e}")

        return {"last_price": 0.0, "previous_close": 0.0, "currency": "USD"}


data_provider = UniversalDataProvider()
