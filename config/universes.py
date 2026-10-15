"""Dynamic Stock Universe Engine (Zero Hardcoded Tickers).

All universes are scraped dynamically in real-time from the internet:
- US Universes: Scraped from SEC Official Public Registry & Wikipedia S&P 500
- Indian Universes: Scraped from Official National Stock Exchange (NSE) Archives
- Momentum & Movers: Scraped live from real-time volume leaders
"""

from typing import List, Dict
from data.live_scrapers import live_scraper

# Benchmark market indices for regime & relative strength detection
BENCHMARK_TICKERS = {
    "US": "^GSPC",    # S&P 500 Index
    "INDIA": "^NSEI"  # Nifty 50 Index
}


def get_us_universe(limit: int = 50) -> List[str]:
    """Dynamically scrapes top prominent US companies from the official SEC registry."""
    return live_scraper.scrape_us_sec_universe(limit=limit)


def get_us_active_movers(limit: int = 35) -> List[str]:
    """Dynamically scrapes today's real-time most active volume movers."""
    return live_scraper.scrape_us_live_actives(count=limit)


def get_us_top_gainers(limit: int = 35) -> List[str]:
    """Dynamically scrapes today's real-time highest % gainers."""
    return live_scraper.scrape_us_day_gainers(count=limit)


def get_india_universe(limit: int = 50) -> List[str]:
    """Dynamically scrapes official constituent companies from the National Stock Exchange (NSE)."""
    return live_scraper.scrape_india_nifty50()[:limit]


def get_india_broad_market(limit: int = 50) -> List[str]:
    """Dynamically scrapes broader market stocks from the official NSE 500 archive."""
    return live_scraper.scrape_india_nifty500(limit=limit)


# Module-level dynamic attribute loader (PEP 562)
# Guarantees that accessing variables dynamically triggers live internet scraping with zero hardcoding
def __getattr__(name: str):
    if name == "US_CORE_UNIVERSE":
        return get_us_universe(limit=50)
    elif name == "US_HIGH_MOMENTUM_WATCHLIST":
        return get_us_active_movers(limit=35)
    elif name == "INDIA_NSE_CORE_UNIVERSE":
        return get_india_universe(limit=50)
    elif name == "INDIA_NSE_MOMENTUM_WATCHLIST":
        return get_india_broad_market(limit=40)
    raise AttributeError(f"Module 'config.universes' has no attribute '{name}'")
