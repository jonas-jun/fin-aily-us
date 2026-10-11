"""
cache_service.py
────────────────
티커 단위 종합 요약 캐시 서비스.
캐시 키: (ticker_id + summary_ttl_hours TTL)

요약과 함께 응답한 기사 목록 스냅샷(articles)을 저장한다. 캐시 히트 시 기사를
news_articles에서 다시 조회하지 않고 이 스냅샷으로 응답해, 요약 i번째와 기사 i번째가
항상 같은 묶음·순서로 짝지어지게 한다. (Market Pulse 화면이 둘을 짝지어 표시한다)
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from supabase import AsyncClient

from app.config import get_cache_config
from app.schemas.news import ArticleOut
from app.services.summarization_service import DigestResult, SummaryPoint
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class CachedDigest:
    digest: DigestResult
    articles: list[ArticleOut]  # 요약 생성 때 응답한 기사 목록 (순서 그대로)


async def get_cached_digest(
    db: AsyncClient,
    ticker_id: int,
    lang: str = "ko",
) -> Optional[CachedDigest]:
    """
    유효한 캐시(TTL 이내)가 있으면 요약과 기사 스냅샷을 반환하고, 없으면 None을 반환한다.
    기사 스냅샷이 없는 구 포맷 행은 짝지을 기사를 알 수 없으므로 캐시 미스로 취급한다.
    """
    cutoff = utc_now() - timedelta(hours=get_cache_config().summary_ttl_hours)

    res = (
        await db.table("ticker_summaries")
        .select("*")
        .eq("ticker_id", ticker_id)
        .gte("created_at", cutoff.isoformat())
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        logger.debug("캐시 미스: ticker_id=%d", ticker_id)
        return None

    row = res.data[0]
    if row.get("articles") is None:
        logger.info("캐시 미스(기사 스냅샷 없는 구 포맷): ticker_id=%d", ticker_id)
        return None
    logger.info("캐시 히트: ticker_id=%d", ticker_id)

    summary_text: str = row["summary_ko"] if lang == "ko" else (row["summary_en"] or row["summary_ko"])

    # JSON 형식(새 포맷) → 기존 bullet 텍스트(구 포맷) 순으로 시도
    try:
        raw = json.loads(summary_text)
        bullets = [SummaryPoint(point=b["point"], quote=b.get("quote", "")) for b in raw]
    except (json.JSONDecodeError, TypeError, KeyError):
        bullets = [
            SummaryPoint(point=line.lstrip("• ").strip(), quote="")
            for line in summary_text.splitlines()
            if line.strip()
        ]

    digest = DigestResult(
        summary=bullets,
        sentiment_score=float(row["sentiment_score"]),
        sentiment_label=row["sentiment_label"],
        model_version=row["model_version"],
        article_ids=row["article_ids"],
        article_count=row["article_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
    return CachedDigest(
        digest=digest,
        articles=[ArticleOut(**a) for a in row["articles"]],
    )


async def save_digest_cache(
    db: AsyncClient,
    ticker_id: int,
    digest_ko: DigestResult,
    articles: list[ArticleOut],
) -> None:
    """종합 요약 결과와 함께 응답한 기사 목록을 ticker_summaries에 저장한다."""
    def to_json(points: list[SummaryPoint]) -> str:
        return json.dumps([p.model_dump() for p in points], ensure_ascii=False)

    payload = {
        "ticker_id":       ticker_id,
        "article_ids":     digest_ko.article_ids,
        "summary_ko":      to_json(digest_ko.summary),
        "summary_en":      None,
        "sentiment_score": float(digest_ko.sentiment_score),
        "sentiment_label": digest_ko.sentiment_label,
        "model_version":   digest_ko.model_version,
        "article_count":   digest_ko.article_count,
        "articles":        [a.model_dump() for a in articles],
        "created_at":      digest_ko.created_at.isoformat(),
    }

    await db.table("ticker_summaries").insert(payload).execute()
    logger.info("캐시 저장: ticker_id=%d, count=%d", ticker_id, digest_ko.article_count)
