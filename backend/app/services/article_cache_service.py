"""
article_cache_service.py
────────────────────────
뉴스 기사 DB 캐싱 서비스.
- article_ttl_hours(기본 1시간) TTL로 기사를 캐싱하여 외부 API 중복 호출을 방지한다.
"""

import logging
from datetime import timedelta
from typing import Optional

from supabase import AsyncClient

from app.config import get_cache_config
from app.services.news_service import RawArticle
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


async def get_cached_articles(
    db: AsyncClient,
    ticker_id: int,
    limit: int = 10,
) -> Optional[list[dict]]:

    cutoff = utc_now() - timedelta(hours=get_cache_config().article_ttl_hours)

    res = (
        await db.table("news_articles")
        .select("*")
        .eq("ticker_id", ticker_id)
        .gte("created_at", cutoff.isoformat())
        # news_service._newest_first와 같은 순서: 최신순, 시각 없음은 뒤로, 동률은 저장 순서
        .order("published_at", desc=True, nullsfirst=False)
        .order("id")
        .limit(limit)
        .execute()
    )

    if not res.data:
        logger.debug("기사 캐시 미스: ticker_id=%d", ticker_id)
        return None

    logger.info("기사 캐시 히트: ticker_id=%d, count=%d", ticker_id, len(res.data))
    return res.data


async def save_articles(
    db: AsyncClient,
    ticker_id: int,
    articles: list[RawArticle],
) -> list[dict]:
    """
    수집된 기사를 news_articles에 저장한다.
    url 중복 시 무시(upsert)하고 저장된 행들을 반환한다.
    """
    rows = [
        {
            "ticker_id": ticker_id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "raw_content": a.raw_content,
        }
        for a in articles
        if a.url  # URL 없는 기사는 UNIQUE 제약 충돌 방지를 위해 저장 제외
    ]
    if not rows:
        return []

    res = (
        await db.table("news_articles")
        .upsert(rows, on_conflict="url", ignore_duplicates=True)
        .execute()
    )

    logger.info("기사 저장: ticker_id=%d, saved=%d", ticker_id, len(res.data))
    return res.data
