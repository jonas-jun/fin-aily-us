/**
 * components/news/DigestCard.tsx
 * ────────────────────────────────
 * 종합 요약 블록.
 * 상단 배지(Sentiment) + bullet 요약 목록을 표시한다.
 */

import type { Digest, Article } from "@/lib/api";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { sentimentBgClass, sentimentEmoji, sentimentTextColor, formatScore } from "@/lib/utils";

interface TickerProps {
  digest: Digest;
}

interface MarketProps {
  digest: Digest;
  articles: Article[];
}

interface ListProps {
  digest: Digest;
  articles?: Article[];
  marketPulse: boolean;
}

function DigestList({ digest, articles, marketPulse }: ListProps) {
  const { summary, sentiment, based_on_articles } = digest;

  return (
    <div className={`rounded-xl border p-5 mb-6 ${marketPulse ? "bg-white" : sentimentBgClass(sentiment.label)}`}>
      {/* 헤더 */}
      <div className="flex flex-col gap-2 mb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-base">📝</span>
          <h2 className="font-semibold text-slate-800 text-sm">
            {marketPulse ? "Market News AI Summary" : "Yahoo Finance News AI Summary"}
          </h2>
          <span className="text-xs text-slate-400">
            최근 {based_on_articles}개 기사 기반
          </span>
        </div>
        {/* Sentiment 배지 */}
        {!marketPulse && (
          <div
            className={`flex items-center gap-1 text-sm font-semibold ${sentimentTextColor(sentiment.label)}`}
          >
            <span>{sentimentEmoji(sentiment.label)}</span>
            <span>{formatScore(sentiment.score)}</span>
            <span className="text-slate-400 font-normal text-xs ml-0.5">
              ({sentiment.label})
            </span>
          </div>
        )}
      </div>

      {/* Bullet 요약 목록 */}
      <ul className="space-y-3">
        {summary.map((bullet, i) => (
          <li key={i} className="flex gap-2 text-sm text-slate-700 leading-relaxed">
            {marketPulse ? (
              <span className="mt-0.5 text-brand-green font-semibold shrink-0 select-none w-5 text-center">{i + 1}</span>
            ) : (
              <span className="mt-0.5 text-slate-400 shrink-0 select-none">•</span>
            )}
            <div className="flex flex-col gap-1 min-w-0">
              <span>{bullet.point}</span>
              {marketPulse && articles?.[i] ? (
                <ExternalLink
                  href={articles[i].url}
                  className="text-xs text-slate-400 hover:text-brand-green transition-colors truncate"
                >
                  {articles[i].title} ↗
                </ExternalLink>
              ) : bullet.quote ? (
                <blockquote className="border-l-2 border-slate-300 pl-2 text-xs text-slate-400 italic">
                  {bullet.quote}
                </blockquote>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TickerDigestCard({ digest }: TickerProps) {
  return <DigestList digest={digest} marketPulse={false} />;
}

export function MarketPulseCard({ digest, articles }: MarketProps) {
  return <DigestList digest={digest} articles={articles} marketPulse />;
}
