-- ============================================================
-- Migration: 003_summary_articles
-- Description: ticker_summaries에 요약과 함께 응답한 기사 목록 스냅샷 컬럼 추가
-- Date: 2026-10-11
-- ============================================================
-- 캐시 히트 시 기사를 news_articles에서 다시 조회하면, url 전역 UNIQUE +
-- ON CONFLICT DO NOTHING + created_at 필터 때문에 요약 생성 때와 다른 묶음이 읽혀
-- 요약 i번째와 기사 i번째가 어긋난다(#58). 요약과 기사 목록을 한 행에 묶어 저장한다.
--
-- ⚠️ 백엔드 배포 전에 적용해야 한다. 컬럼이 없으면 요약 저장이 실패해 503이 난다.
-- 기존 행은 NULL로 남고, 백엔드가 캐시 미스로 취급해 다음 요청에서 새로 만든다.

ALTER TABLE ticker_summaries ADD COLUMN IF NOT EXISTS articles JSONB;

COMMENT ON COLUMN ticker_summaries.articles IS
    '요약과 함께 응답한 기사 목록 (ArticleOut 배열, 응답 순서 그대로). NULL이면 구 포맷 → 캐시 미스.';
