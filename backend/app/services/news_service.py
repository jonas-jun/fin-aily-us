"""
news_service.py
───────────────
뉴스 수집 서비스.
- 종목 뉴스: Yahoo Finance 티커별 RSS → yfinance 순으로 수집을 시도한다.
- 시장 뉴스: MARKET_RSS_FEEDS의 여러 RSS를 병렬 수집해 병합한다.
  한 소스가 실패(HTTP 오류·timeout·파싱 예외)해도 나머지 소스로 응답한다.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain, zip_longest
from typing import Optional
from urllib.parse import quote

import feedparser
import requests
import yfinance as yf
from newspaper import Article

logger = logging.getLogger(__name__)

# 기본 UA는 Yahoo edge에서 429로 차단된 사례가 있어 모든 RSS 요청에 브라우저 UA를 쓴다.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
# (connect, read) 초. feedparser 자체 요청에는 timeout이 없어, 응답 없는 소스 하나가
# Market Pulse 전체를 무기한 붙잡는다.
RSS_TIMEOUT = (3, 10)

# 티커(쉼표로 여러 개 가능)별 헤드라인 RSS
YAHOO_HEADLINE_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbols}&region=US&lang=en-US"

# 키는 RawArticle.source·로그 라벨로 쓰이며, 정의 순서가 라운드로빈 순서다.
MARKET_RSS_FEEDS = {
    "Yahoo Finance": YAHOO_HEADLINE_RSS.format(symbols=quote("^GSPC,^DJI,^IXIC")),  # S&P500·다우·나스닥
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # Top News
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",  # Top Stories
}

_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)

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


def _newest_first(articles: list[RawArticle]) -> list[RawArticle]:
    """발행 시각 내림차순(없으면 맨 뒤)으로 안정 정렬한다.

    get_cached_articles의 ORDER BY published_at DESC NULLS LAST, id ASC와 같은 순서가 되도록,
    동률은 입력 순서(= DB 저장 순서)를 유지한다.
    """
    return sorted(articles, key=lambda a: a.published_at or _MIN_DT, reverse=True)


async def fetch_articles(symbol: str, limit: int = 10) -> list[RawArticle]:
    """티커 심볼에 대한 최신 뉴스를 수집한다."""
    articles = await _fetch_from_rss(symbol, limit)
    if not articles:
        logger.warning("티커 RSS 수집 실패, yfinance 시도: symbol=%s", symbol)
        articles = _newest_first(await _fetch_from_yfinance(symbol, limit))
    if not articles:
        logger.error("티커 뉴스 전 소스 수집 실패: symbol=%s", symbol)

    logger.info("뉴스 수집 완료: symbol=%s, count=%d", symbol, len(articles))
    return articles[:limit]

async def fetch_market_news(limit: int = 10) -> list[RawArticle]:
    """MARKET_RSS_FEEDS를 병렬 수집해 소스별 최신 기사를 번갈아 limit개 고르고 최신순으로 반환한다.

    중복(url, 없으면 title)은 제거하고, summary가 빈 기사는 본문을 스크래핑해 채운다.
    """
    results = await asyncio.gather(
        *(asyncio.to_thread(_parse_feed, url, source) for source, url in MARKET_RSS_FEEDS.items()),
        return_exceptions=True,
    )
    per_source = []
    for source, result in zip(MARKET_RSS_FEEDS, results):
        if isinstance(result, BaseException):
            logger.error("RSS 처리 오류: source=%s", source, exc_info=result)
            result = []
        # 피드 순서가 최신순이라는 보장이 없어(Yahoo·CNBC 실측) 소스별로 먼저 정렬한다.
        per_source.append(_newest_first(result))

    logger.info(
        "시장 뉴스 수집 완료: %s",
        ", ".join(f"{src}={len(items)}" for src, items in zip(MARKET_RSS_FEEDS, per_source)),
    )
    if not any(per_source):
        logger.error("시장 뉴스 전 소스 수집 실패")
        return []

    # 발행 시각만으로 고르면 발행 빈도가 높은 소스가 상위를 독점하므로 소스별로 번갈아 뽑는다.
    merged = [a for a in chain.from_iterable(zip_longest(*per_source)) if a is not None]
    articles, seen = [], set()
    for a in merged:
        key = a.url or a.title
        if key in seen:
            continue
        seen.add(key)
        articles.append(a)
        if len(articles) == limit:
            break

    # Market Pulse 화면은 summary[i]와 articles[i]를 짝지어 표시하므로, 캐시 히트 때
    # get_cached_articles가 읽는 순서와 같게 맞춘다.
    articles = _newest_first(articles)
    return await asyncio.to_thread(_fill_missing_bodies, articles)


def _fill_missing_bodies(articles: list[RawArticle]) -> list[RawArticle]:
    """raw_content가 빈 기사만 본문을 순차 스크래핑해 채우고, 실패하면 제목으로 대체한다."""
    for a in articles:
        if not a.raw_content:
            a.raw_content = _scrape_body(a.url) or a.title
    return articles


def _parse_feed(url: str, source: str) -> list[RawArticle]:
    """RSS 피드를 받아 RawArticle 목록으로 변환한다.

    - 요청 실패(네트워크 오류·timeout·4xx/5xx)는 ERROR 로그 후 빈 리스트를 반환한다.
    - 응답은 정상인데 entry가 없거나 일부만 파싱됐으면 WARNING을 남기고 파싱된 entry를 반환한다.
    - 제목 없는 entry는 건너뛰고, 발행 시각이 없으면 published_at은 None이다.
    """
    try:
        resp = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=RSS_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("RSS 요청 실패: source=%s, url=%s, error=%s", source, url, e)
        return []
    if resp.history:
        # 피드 이전의 전조일 수 있어 최종 URL을 남긴다.
        logger.warning("RSS 리다이렉트: source=%s, url=%s -> %s", source, url, resp.url)

    feed = feedparser.parse(resp.content)
    if not feed.entries or feed.bozo:
        logger.warning(
            "RSS 파싱 이상: source=%s, url=%s, entries=%d, bozo=%s",
            source, url, len(feed.entries), feed.get("bozo_exception"),
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
    """티커 RSS가 비었을 때 쓰는 yfinance 조회와, body/summary가 없을 때의 본문 스크래핑을 같은 worker thread에서 수행한다."""
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
    """티커별 RSS의 동기 HTTP 요청을 worker thread에서 수행한다. summary가 비면 제목으로 채운다."""
    url = YAHOO_HEADLINE_RSS.format(symbols=quote(symbol.upper()))
    articles = _newest_first(_parse_feed(url, "Yahoo Finance"))[:limit]
    for a in articles:
        a.raw_content = a.raw_content or a.title
    return articles
