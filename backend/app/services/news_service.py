"""
news_service.py
───────────────
뉴스 수집 서비스.
- 종목 뉴스: Yahoo Finance 티커별 RSS → yfinance 순으로 수집을 시도한다.
- 시장 뉴스: Yahoo Finance(지수 헤드라인)·CNBC·MarketWatch RSS를 병합한다.
  한 소스가 끊겨도 나머지로 서비스가 유지되도록 여러 경로를 함께 쓴다.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain, zip_longest
from typing import Optional
from urllib.parse import quote

import feedparser
import yfinance as yf
from newspaper import Article

from app.time_utils import utc_now

logger = logging.getLogger(__name__)

# 기본 feedparser UA는 Yahoo edge에서 429로 차단된 사례가 있어 브라우저 UA를 쓴다.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# 티커(쉼표로 여러 개 가능)별 헤드라인 RSS
YAHOO_HEADLINE_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbols}&region=US&lang=en-US"

MARKET_RSS_FEEDS = {
    "Yahoo Finance": YAHOO_HEADLINE_RSS.format(symbols=quote("^GSPC,^DJI,^IXIC")),  # S&P500·다우·나스닥
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # Top News
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}

@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    raw_content: str

def _scrape_body(url: str) -> str:
    """기사 URL에서 본문을 추출한다. 실패 시 빈 문자열 반환."""
    if not url:
        return ""
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text or ""
    except Exception as e:
        logger.debug("본문 스크래핑 실패: url=%s, error=%s", url, e)
        return ""


async def fetch_articles(symbol: str, limit: int = 10) -> list[RawArticle]:
    """티커 심볼에 대한 최신 뉴스를 수집한다."""
    articles = await _fetch_from_rss(symbol, limit)
    if not articles:
        logger.warning("티커 RSS 수집 실패, yfinance 시도: symbol=%s", symbol)
        articles = await _fetch_from_yfinance(symbol, limit)

    logger.info("뉴스 수집 완료: symbol=%s, count=%d", symbol, len(articles))
    return articles[:limit]

async def fetch_market_news(limit: int = 10) -> list[RawArticle]:
    """여러 시장 뉴스 RSS를 병렬로 수집해 소스별로 번갈아 limit개를 고르고 최신순으로 반환한다."""
    per_source = await asyncio.gather(*(
        asyncio.to_thread(_parse_feed, url, source)
        for source, url in MARKET_RSS_FEEDS.items()
    ))
    # 발행 시각만으로 정렬하면 기사가 많은 소스가 상위를 독점하므로 소스별로 번갈아 뽑는다.
    merged = [a for a in chain.from_iterable(zip_longest(*per_source)) if a is not None]

    articles, seen = [], set()
    for a in merged:
        key = a.url or a.title
        if key in seen:
            continue
        seen.add(key)
        a.published_at = a.published_at or utc_now()
        articles.append(a)
        if len(articles) == limit:
            break
    # DB 캐시는 published_at 내림차순으로 읽히므로 같은 순서로 맞춘다.
    # (Market Pulse 화면은 요약 i번째와 기사 i번째를 짝지어 표시한다)
    articles.sort(key=lambda a: a.published_at, reverse=True)

    logger.info(
        "시장 뉴스 수집 완료: %s",
        ", ".join(f"{src}={len(items)}" for src, items in zip(MARKET_RSS_FEEDS, per_source)),
    )
    return await asyncio.to_thread(_fill_missing_bodies, articles)


def _fill_missing_bodies(articles: list[RawArticle]) -> list[RawArticle]:
    """RSS summary가 비어 있는 기사만 본문을 스크래핑해 채운다."""
    for a in articles:
        if not a.raw_content:
            a.raw_content = _scrape_body(a.url) or a.title
    return articles


def _parse_feed(url: str, source: str) -> list[RawArticle]:
    """RSS 피드를 RawArticle 목록으로 변환한다. 실패 시 원인을 로그에 남기고 빈 리스트를 반환한다."""
    try:
        feed = feedparser.parse(url, agent=BROWSER_UA)
    except Exception as e:
        logger.error("RSS 수집 오류: source=%s, url=%s, error=%s", source, url, e)
        return []

    status = feed.get("status")
    if status != 200 or not feed.entries:
        logger.warning(
            "RSS 응답 이상: source=%s, url=%s, status=%s, entries=%d, bozo=%s",
            source, url, status, len(feed.entries), feed.get("bozo_exception"),
        )

    articles = []
    for entry in feed.entries:
        title = entry.get("title", "")
        if not title:
            continue
        pub = entry.get("published_parsed")
        articles.append(RawArticle(
            title=title,
            url=entry.get("link", ""),
            source=source,
            published_at=datetime(*pub[:6], tzinfo=timezone.utc) if pub else None,
            raw_content=entry.get("summary", ""),
        ))
    return articles

def _parse_pub_time(item: dict, content: dict) -> Optional[datetime]:
    """yfinance 0.2.x 뉴스 아이템에서 발행 시각을 추출한다."""
    # 1) 최상위 Unix 타임스탬프 (구형/신형 공통)
    pub_ts = item.get("providerPublishTime")
    if pub_ts:
        try:
            return datetime.fromtimestamp(int(pub_ts), tz=timezone.utc)
        except Exception:
            pass

    # 2) content.pubDate (ISO 문자열, yfinance 0.2.48+)
    pub_str = content.get("pubDate") or content.get("publishTime")
    if pub_str:
        try:
            return datetime.fromisoformat(str(pub_str).replace("Z", "+00:00"))
        except Exception:
            pass

    # 3) content.provider.publishTime (중첩 구조 대비)
    provider_ts = (content.get("provider") or {}).get("publishTime")
    if provider_ts:
        try:
            return datetime.fromtimestamp(int(provider_ts), tz=timezone.utc)
        except Exception:
            pass

    logger.debug("발행 시각 파싱 실패: item_keys=%s", list(item.keys()))
    return None


async def _fetch_from_yfinance(symbol: str, limit: int) -> list[RawArticle]:
    """yfinance를 통한 뉴스 수집"""
    return await asyncio.to_thread(_fetch_from_yfinance_sync, symbol, limit)


def _fetch_from_yfinance_sync(symbol: str, limit: int) -> list[RawArticle]:
    """yfinance 조회와 fallback 본문 스크래핑을 같은 worker thread에서 수행한다."""
    try:
        ticker = yf.Ticker(symbol)
        news_items = ticker.news or []
        articles = []
        for item in (news_items or []):
            if not isinstance(item, dict):
                continue
            content = item.get("content") or {}
            title = item.get("title") or content.get("title", "")
            if not title:
                continue
            # yfinance 0.2.48+: 원문 URL은 content.clickThroughUrl에 있음
            # 값이 None인 경우를 대비해 or {} 패턴 사용
            url = (
                (content.get("clickThroughUrl") or {}).get("url", "")
                or item.get("link", "")
                or (content.get("canonicalUrl") or {}).get("url", "")
                or item.get("url", "")
            )
            raw_text = content.get("body", "") or content.get("summary", "") or _scrape_body(url) or title
            pub_dt = _parse_pub_time(item, content)
            articles.append(RawArticle(
                title=title,
                url=url,
                source=item.get("publisher", "Yahoo Finance"),
                published_at=pub_dt,
                raw_content=raw_text,
            ))
        return articles
    except Exception as e:
        logger.error("yfinance 수집 오류: symbol=%s, error=%s", symbol, e)
        return []

async def _fetch_from_rss(symbol: str, limit: int) -> list[RawArticle]:
    """Yahoo Finance 티커별 RSS를 통한 뉴스 수집"""
    return await asyncio.to_thread(_fetch_from_rss_sync, symbol, limit)


def _fetch_from_rss_sync(symbol: str, limit: int) -> list[RawArticle]:
    """티커별 RSS의 동기 HTTP 요청을 worker thread에서 수행한다."""
    url = YAHOO_HEADLINE_RSS.format(symbols=quote(symbol.upper()))
    articles = _parse_feed(url, "Yahoo Finance")
    articles.sort(key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for a in articles:
        a.raw_content = a.raw_content or a.title
    return articles[:limit]
