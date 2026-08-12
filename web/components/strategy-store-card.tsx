"use client";

import Link from "next/link";
import type { StrategyStoreCard } from "../lib/api";
import { formatPercentNoDecimal, formatPriceYuan } from "../lib/api";

export function StrategyStoreCard({ strategy }: { strategy: StrategyStoreCard }) {
  const perf = strategy.recent_performance;
  const price = strategy.pricing;
  const isFree = !price || price.type === "free";

  return (
    <article className="store-card">
      <header>
        <span className="store-card__category">{strategy.category ?? "策略"}</span>
        <Link href={`/store/${encodeURIComponent(strategy.strategy_id)}`}>
          <h3>{strategy.display_name}</h3>
        </Link>
        <small>
          {strategy.supported_markets.join("、")} · {" "}
          {strategy.supported_timeframes.join("、")}
        </small>
      </header>
      <div className="store-card__perf">
        <div>
          <span>近3个月涨跌</span>
          <strong className={perf && (perf.total_return ?? 0) >= 0 ? "is-up" : "is-down"}>
            {perf ? formatPercentNoDecimal(perf.total_return) : "—"}
          </strong>
        </div>
        <div>
          <span>信号次数</span>
          <strong>{perf?.signal_count ?? "—"}</strong>
        </div>
        <div>
          <span>胜率</span>
          <strong>{perf ? formatPercentNoDecimal(perf.win_rate) : "—"}</strong>
        </div>
        <div>
          <span>最大回撤</span>
          <strong className="is-down">{perf ? formatPercentNoDecimal(perf.max_drawdown) : "—"}</strong>
        </div>
      </div>
      <footer>
        <span className="store-card__price">
          {isFree ? "免费" : formatPriceYuan(price?.monthly_price)}
          {!isFree ? <small>/ 月</small> : null}
        </span>
        <Link className="store-card__action" href={`/store/${encodeURIComponent(strategy.strategy_id)}`}>
          查看详情
        </Link>
      </footer>
    </article>
  );
}
