"""Financial News Scraper & AI Catalyst Sentiment Analyzer."""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
import yfinance as yf

logger = logging.getLogger(__name__)

# Institutional catalyst keyword dictionaries
BULLISH_CATALYSTS = [
    "beat", "beats", "record revenue", "record profit", "guidance raised", "upgraded",
    "upgrade", "breakout", "strong growth", "expansion", "partnership", "soars",
    "surges", "new contract", "fda approved", "ai demand", "dividend hike",
    "buyback", "outperform", "bullish", "acquisition", "profit doubles"
]

BEARISH_CATALYSTS = [
    "miss", "misses", "downgrade", "downgraded", "lawsuit", "investigation",
    "sec probe", "slashes guidance", "layoffs", "cuts dividend", "debt default",
    "profit drops", "revenue declines", "falls", "plummets", "headwinds",
    "recall", "resignation", "weak forecast"
]


@dataclass
class NewsItem:
    title: str
    publisher: str
    link: str
    publish_time: str
    sentiment_tag: str     # 'BULLISH', 'BEARISH', 'NEUTRAL'
    sentiment_score: float # -1.0 to +1.0


@dataclass
class StockNewsSentiment:
    ticker: str
    total_articles: int
    bullish_count: int
    bearish_count: int
    net_sentiment_score: float # -100 to +100
    overall_sentiment: str     # 'POSITIVE_CATALYST', 'NEGATIVE_CATALYST', 'NEUTRAL'
    articles: List[NewsItem]


from data.live_scrapers import live_scraper


class NewsAnalyzer:
    def analyze_ticker_news(self, ticker: str, max_articles: int = 10) -> StockNewsSentiment:
        """Scrapes real-time financial news articles for a ticker and analyzes catalyst sentiment."""
        # 1. Scrape live real-time Google News RSS articles
        scraped_news = live_scraper.scrape_google_news_rss(ticker, max_items=max_articles)

        # 2. Fallback to yfinance news if RSS returned empty
        if not scraped_news:
            try:
                t = yf.Ticker(ticker)
                raw_yf = getattr(t, "news", []) or []
                for item in raw_yf[:max_articles]:
                    scraped_news.append({
                        "title": item.get("title", ""),
                        "publisher": item.get("publisher", "Financial News"),
                        "link": item.get("link", "#"),
                        "publish_time": str(item.get("providerPublishTime", ""))
                    })
            except Exception as e:
                logger.error(f"Error fetching news for {ticker}: {e}")

        articles: List[NewsItem] = []
        bullish_cnt = 0
        bearish_cnt = 0

        for item in scraped_news[:max_articles]:
            title = item.get("title", "")
            publisher = item.get("publisher", "Financial News")
            link = item.get("link", "#")
            publish_time = str(item.get("publish_time", ""))

            title_lower = title.lower()

            # Score title
            bull_hits = sum(1 for kw in BULLISH_CATALYSTS if kw in title_lower)
            bear_hits = sum(1 for kw in BEARISH_CATALYSTS if kw in title_lower)

            if bull_hits > bear_hits:
                sentiment_tag = "BULLISH"
                sentiment_score = 0.8
                bullish_cnt += 1
            elif bear_hits > bull_hits:
                sentiment_tag = "BEARISH"
                sentiment_score = -0.8
                bearish_cnt += 1
            else:
                sentiment_tag = "NEUTRAL"
                sentiment_score = 0.0

            articles.append(NewsItem(
                title=title,
                publisher=publisher,
                link=link,
                publish_time=publish_time,
                sentiment_tag=sentiment_tag,
                sentiment_score=sentiment_score
            ))

        total = len(articles)
        if total > 0:
            net_pct = ((bullish_cnt - bearish_cnt) / total) * 100.0
        else:
            net_pct = 0.0

        if net_pct >= 25.0:
            overall = "🚀 POSITIVE CATALYST (News Tailwinds)"
        elif net_pct <= -25.0:
            overall = "⚠️ NEGATIVE HEADWINDS (Caution)"
        else:
            overall = "⚖️ NEUTRAL / BALANCED NEWS FLOW"

        return StockNewsSentiment(
            ticker=ticker,
            total_articles=total,
            bullish_count=bullish_cnt,
            bearish_count=bearish_cnt,
            net_sentiment_score=round(net_pct, 1),
            overall_sentiment=overall,
            articles=articles
        )


news_analyzer = NewsAnalyzer()
