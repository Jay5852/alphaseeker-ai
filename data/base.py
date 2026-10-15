"""Abstract Base Class for Market Data Providers."""

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def get_historical_daily(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Fetch daily OHLCV bars for swing analysis."""
        pass

    @abstractmethod
    def get_intraday_bars(self, ticker: str, interval: str = "5m", period: str = "5d") -> pd.DataFrame:
        """Fetch intraday OHLCV bars for intraday analysis."""
        pass

    @abstractmethod
    def get_latest_quote(self, ticker: str) -> dict:
        """Fetch real-time snapshot quote."""
        pass
