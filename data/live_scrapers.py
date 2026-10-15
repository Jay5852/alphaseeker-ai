"""Dynamic Web Scraping Engine with Anti-Blocking & Multi-Source Failover.

Zero Hardcoded Tickers. All market universes and news feeds are scraped 
dynamically from the internet across:
- US Securities & Exchange Commission (SEC) official company registry (10,000+ US stocks)
- National Stock Exchange of India (NSE) official index archives (Nifty 50, 100, 500)
- Wikipedia Live Index constituent tables (S&P 500, Nifty 50)
- Real-time intraday active volume movers and top percentage gainers
- Google News RSS real-time financial articles

Anti-Blocking Features:
1. Session connection pooling with requests
2. Realistic browser header rotation
3. Automated multi-source failover (if Source A fails, Source B takes over)
4. Disk & in-memory caching with TTL to prevent IP rate-limiting (HTTP 429)
"""

import io
import json
import logging
import random
import time
from pathlib import Path
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]


def get_headers(is_sec: bool = False) -> Dict[str, str]:
    """Generates anti-blocking headers."""
    if is_sec:
        return {
            "User-Agent": "AlphaSeekerQuantResearch/2.0 (quant-engine@alphaseeker-system.org)",
            "Accept": "application/json, text/plain, */*"
        }

    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }


class DynamicMarketScraper:
    def __init__(self, cache_ttl_hours: int = 12):
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.session = requests.Session()

    def _get_from_disk_cache(self, key: str) -> Optional[List[str]]:
        cache_file = CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            try:
                mtime = cache_file.stat().st_mtime
                if (time.time() - mtime) < self.cache_ttl_seconds:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list) and len(data) > 0:
                            return data
            except Exception as e:
                logger.warning(f"Error reading cache for {key}: {e}")
        return None

    def _save_to_disk_cache(self, key: str, data: List[str]):
        cache_file = CACHE_DIR / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Error saving cache for {key}: {e}")

    # ==========================================
    # 1. US MARKET DYNAMIC SCRAPERS
    # ==========================================

    def scrape_us_sec_universe(self, limit: int = 100) -> List[str]:
        """Scrapes live official company tickers from the SEC public registry (10,000+ active tickers)."""
        cache_key = f"us_sec_top_{limit}"
        cached = self._get_from_disk_cache(cache_key)
        if cached:
            return cached

        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            resp = self.session.get(url, headers=get_headers(is_sec=True), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                tickers = [
                    v["ticker"].replace(".", "-") for v in data.values() 
                    if "ticker" in v and len(v["ticker"]) <= 5 and not any(c in v["ticker"] for c in ["^", "=", " "])
                ]
                result = tickers[:limit]
                if result:
                    self._save_to_disk_cache(cache_key, result)
                    return result
        except Exception as e:
            logger.error(f"SEC registry scrape failed: {e}. Falling back to Wikipedia S&P 500...")

        return self.scrape_us_sp500()[:limit]

    def scrape_us_sp500(self) -> List[str]:
        """Scrapes live S&P 500 constituents from Wikipedia."""
        cache_key = "us_sp500_live"
        cached = self._get_from_disk_cache(cache_key)
        if cached:
            return cached

        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        try:
            resp = self.session.get(url, headers=get_headers(), timeout=10)
            if resp.status_code == 200:
                tables = pd.read_html(io.StringIO(resp.text))
                symbols = [str(s).strip().replace(".", "-") for s in tables[0]["Symbol"].dropna()]
                if len(symbols) >= 400:
                    self._save_to_disk_cache(cache_key, symbols)
                    return symbols
        except Exception as e:
            logger.error(f"Wikipedia S&P 500 scrape failed: {e}")

        return self.scrape_us_sec_universe(limit=60)

    def scrape_us_live_actives(self, count: int = 40) -> List[str]:
        """Scrapes today's real-time most active volume leaders from Yahoo Finance."""
        url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=most_actives&count={count}"
        try:
            resp = self.session.get(url, headers=get_headers(), timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                quotes = data["finance"]["result"][0]["quotes"]
                tickers = [q["symbol"] for q in quotes if "symbol" in q and not q["symbol"].startswith("^")]
                if tickers:
                    return tickers
        except Exception as e:
            logger.error(f"Yahoo most_actives scrape failed: {e}")

        return self.scrape_us_sec_universe(limit=count)

    def scrape_us_day_gainers(self, count: int = 40) -> List[str]:
        """Scrapes today's real-time top % gainers."""
        url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=day_gainers&count={count}"
        try:
            resp = self.session.get(url, headers=get_headers(), timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                quotes = data["finance"]["result"][0]["quotes"]
                tickers = [q["symbol"] for q in quotes if "symbol" in q and not q["symbol"].startswith("^")]
                if tickers:
                    return tickers
        except Exception as e:
            logger.error(f"Yahoo day_gainers scrape failed: {e}")

        return self.scrape_us_sec_universe(limit=count)

    # ==========================================
    # 2. INDIAN MARKET DYNAMIC SCRAPERS
    # ==========================================

    def scrape_india_nifty50(self) -> List[str]:
        """Scrapes live Nifty 50 constituents from official NSE archives or Wikipedia."""
        cache_key = "india_nifty50_live"
        cached = self._get_from_disk_cache(cache_key)
        if cached:
            return cached

        # Source 1: Official NSE Archives CSV
        url_nse = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
        try:
            resp = self.session.get(url_nse, headers=get_headers(), timeout=8)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.text))
                symbols = [f"{str(s).strip()}.NS" for s in df["Symbol"].dropna() if len(str(s).strip()) > 1]
                if len(symbols) >= 45:
                    self._save_to_disk_cache(cache_key, symbols)
                    return symbols
        except Exception as e:
            logger.warning(f"NSE Nifty 50 CSV scrape failed: {e}. Trying Wikipedia...")

        # Source 2: Wikipedia Fallback
        url_wiki = "https://en.wikipedia.org/wiki/NIFTY_50"
        try:
            resp = self.session.get(url_wiki, headers=get_headers(), timeout=10)
            if resp.status_code == 200:
                tables = pd.read_html(io.StringIO(resp.text))
                for t in tables:
                    if "Symbol" in t.columns:
                        symbols = [f"{str(s).strip()}.NS" for s in t["Symbol"].dropna() if len(str(s).strip()) > 1]
                        if len(symbols) >= 45:
                            self._save_to_disk_cache(cache_key, symbols)
                            return symbols
        except Exception as e:
            logger.error(f"Wikipedia Nifty 50 scrape failed: {e}")

        return []

    def scrape_india_nifty500(self, limit: int = 100) -> List[str]:
        """Scrapes the live official Nifty 500 constituents from NSE Archives."""
        cache_key = f"india_nifty500_top_{limit}"
        cached = self._get_from_disk_cache(cache_key)
        if cached:
            return cached

        url_nse = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        try:
            resp = self.session.get(url_nse, headers=get_headers(), timeout=10)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.text))
                symbols = [f"{str(s).strip()}.NS" for s in df["Symbol"].dropna() if len(str(s).strip()) > 1]
                res = symbols[:limit]
                if res:
                    self._save_to_disk_cache(cache_key, res)
                    return res
        except Exception as e:
            logger.error(f"NSE Nifty 500 CSV scrape failed: {e}")

        return self.scrape_india_nifty50()[:limit]

    # ==========================================
    # 3. LIVE NEWS ARTICLES SCRAPER
    # ==========================================

    def scrape_live_news_articles(self, ticker: str, max_items: int = 10) -> List[Dict[str, str]]:
        """Scrapes real-time financial news articles from Google News RSS for any stock."""
        clean = ticker.replace(".NS", "")
        url = f"https://news.google.com/rss/search?q={clean}+stock&hl=en-US&gl=US&ceid=US:en"

        articles = []
        try:
            resp = self.session.get(url, headers=get_headers(), timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:max_items]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else "#"
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    source = item.find("source").text if item.find("source") is not None else "Financial News"

                    articles.append({
                        "title": title,
                        "link": link,
                        "publish_time": pub_date,
                        "publisher": source
                    })
        except Exception as e:
            logger.error(f"Error scraping live news for {ticker}: {e}")

        return articles

    # Backward-compatible convenience aliases
    scrape_sp500_live = scrape_us_sp500
    scrape_nifty50_live = scrape_india_nifty50
    scrape_us_most_actives = scrape_us_live_actives
    scrape_google_news_rss = scrape_live_news_articles


live_scraper = DynamicMarketScraper()
