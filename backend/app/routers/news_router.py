"""
news_router.py
──────────────
뉴스 조회 라우터.
- /news/{symbol}: 특정 종목 뉴스 및 요약
- /news/market-pulse: 시장 전체 뉴스(소스: news_service.MARKET_RSS_FEEDS) 및 요약
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import get_settings
from app.dependencies import get_db
from app.schemas.news import ArticleOut, DigestOut, NewsResponse, SentimentOut
from app.services.article_cache_service import (
    get_cached_articles,
    save_articles,
)
from app.services.cache_service import get_cached_digest, save_digest_cache
from app.services.news_service import RawArticle, fetch_articles, fetch_market_news
from app.services.summarization_service import (
    ArticleInput,
    DigestResult,
    summarize_articles,
)
from app.services.ticker_service import ensure_ticker
from app.time_utils import utc_now_iso

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/news", tags=["news"])


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _rows_to_raw_articles(rows: list[dict]) -> list[RawArticle]:
    """DB 행을 RawArticle로 변환한다."""
    return [
        RawArticle(
            title=r["title"],
            url=r["url"],
            source=r.get("source", ""),
            published_at=(
                datetime.fromisoformat(r["published_at"])
                if r.get("published_at")
                else None
            ),
            raw_content=r.get("raw_content", ""),
        )
        for r in rows
    ]


def _build_article_inputs(articles: list[RawArticle]) -> list[ArticleInput]:
    return [
        ArticleInput(id=i, title=a.title, source=a.source, content=a.raw_content)
        for i, a in enumerate(articles)
    ]


def _build_article_outs(articles: list[RawArticle]) -> list[ArticleOut]:
    return [
        ArticleOut(
            id=i,
            title=a.title,
            source=a.source,
            url=a.url,
            published_at=a.published_at.isoformat() if a.published_at else "",
        )
        for i, a in enumerate(articles)
    ]


async def _get_or_fetch_articles(
    db, ticker_id: int, fetch_fn, limit: int
) -> list[RawArticle]:
    """기사 캐시(article_ttl_hours) 이내 기사가 있으면 사용하고, 없으면 외부 수집 후 DB에 저장한다."""
    cached = await get_cached_articles(db, ticker_id, limit)
    if cached:
        return _rows_to_raw_articles(cached)

    raw_articles = await fetch_fn()
    if raw_articles:
        await save_articles(db, ticker_id, raw_articles)
    return raw_articles


def _digest_out(digest: DigestResult) -> DigestOut:
    # 요약 입력은 앞 MAX_ARTICLES개로 잘리므로, 캐시 미스·히트 모두 요약 결과의 기사 수를 쓴다.
    return DigestOut(
        summary=digest.summary,
        sentiment=SentimentOut(score=digest.sentiment_score, label=digest.sentiment_label),
        based_on_articles=digest.article_count,
    )


async def _summarize_and_cache(
    db, ticker_id: int, symbol: str, company_name: str,
    articles: list[RawArticle], lang: str,
    feature: str = "ticker_brief",
) -> tuple[DigestOut, list[ArticleOut]]:
    """AI 요약을 생성하고, 응답할 기사 목록과 함께 요약 캐시에 저장한다.

    기사 목록은 입력 전체다(요약 입력은 그중 앞 MAX_ARTICLES개). 캐시 저장이 실패해도
    이미 만든 요약으로 응답한다. (예: migration 003 미적용 → ERROR 로그로 드러난다)
    """
    settings = get_settings()
    api_key = settings.gemini_api_key or None

    inputs = _build_article_inputs(articles)
    digest = await summarize_articles(
        symbol=symbol,
        company_name=company_name,
        articles=inputs,
        lang=lang,
        api_key=api_key,
        feature=feature,
    )

    article_outs = _build_article_outs(articles)
    try:
        await save_digest_cache(db, ticker_id, digest, article_outs)
    except Exception:
        logger.exception("요약 캐시 저장 실패(응답은 정상 반환): ticker_id=%d, symbol=%s", ticker_id, symbol)
    return _digest_out(digest), article_outs


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get(
    "/market-pulse",
    response_model=NewsResponse,
    summary="시장 최신 뉴스 + AI 비서 요약",
)
async def get_market_pulse(
    lang: str = Query(default="ko", pattern="^(ko|en)$"),
    db=Depends(get_db),
):
    """
    MARKET_RSS_FEEDS에서 소스별로 고르게 섞은 최신 시장 뉴스 최대 10개를 가져와 '똑똑한 비서' 페르소나로 요약한다.
    요약 캐시가 유효하면 요약과 함께 저장한 기사 목록으로 응답하고, 아니면 기사 캐시
    (article_ttl_hours) 또는 외부 수집 결과로 요약을 새로 만든다.
    """
    ticker = await ensure_ticker(db, "MARKET", lookup_profile=False)
    ticker_id = ticker["id"]

    cached = await get_cached_digest(db, ticker_id, lang)
    if cached:
        digest_out = _digest_out(cached.digest)
        article_outs = cached.articles
    else:
        raw_articles = await _get_or_fetch_articles(
            db, ticker_id, lambda: fetch_market_news(limit=10), limit=10
        )
        if not raw_articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NO_NEWS", "message": "최신 시장 뉴스를 가져올 수 없습니다."},
            )

        try:
            digest_out, article_outs = await _summarize_and_cache(
                db, ticker_id, "MARKET", "Market Top Stories", raw_articles, lang,
                feature="market_pulse",
            )
        except Exception:
            logger.exception("Market Pulse 요약 실패: ticker_id=%d", ticker_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "SUMMARIZATION_FAILED", "message": "시장 요약 생성에 실패했습니다."},
            )

    return NewsResponse(
        symbol="MARKET",
        company_name="Market Top Stories",
        last_updated=utc_now_iso(),
        digest=digest_out,
        articles=article_outs,
    )


@router.get(
    "/{symbol}",
    response_model=NewsResponse,
    summary="종목 최신 뉴스 + AI 종합 요약",
)
async def get_news(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=20),
    lang: str = Query(default="ko", pattern="^(ko|en)$"),
    db=Depends(get_db),
):
    """
    특정 티커에 대한 최신 뉴스를 수집하고 AI 종합 요약을 제공한다.
    요약 캐시가 유효하면 요약과 함께 저장한 기사 목록으로 응답하고, 아니면 기사 캐시
    (article_ttl_hours) 또는 외부 수집 결과로 요약을 새로 만든다.
    """
    upper_symbol = symbol.upper()
    ticker = await ensure_ticker(db, upper_symbol)
    ticker_id, company = ticker["id"], ticker["name"]

    cached = await get_cached_digest(db, ticker_id, lang)
    if cached:
        digest_out = _digest_out(cached.digest)
        article_outs = cached.articles
    else:
        raw_articles = await _get_or_fetch_articles(
            db, ticker_id, lambda: fetch_articles(upper_symbol, limit), limit=limit
        )
        if not raw_articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NO_NEWS", "message": f"{upper_symbol}에 대한 뉴스를 찾을 수 없습니다."},
            )

        try:
            digest_out, article_outs = await _summarize_and_cache(
                db, ticker_id, upper_symbol, company, raw_articles, lang
            )
        except Exception:
            logger.exception("종목 요약 실패: symbol=%s", upper_symbol)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "SUMMARIZATION_FAILED", "message": "뉴스 요약 생성에 실패했습니다."},
            )

    return NewsResponse(
        symbol=upper_symbol,
        company_name=company,
        last_updated=utc_now_iso(),
        digest=digest_out,
        articles=article_outs,
    )
