"use client";

import type { PerformanceSummary, StrategyStoreDetail } from "../lib/api";
import { formatDate, formatPercent, formatPercentNoDecimal } from "../lib/api";

function PerformanceMetric({
  label,
  value,
  negative = false,
  positive = false
}: {
  label: string;
  value: string;
  negative?: boolean;
  positive?: boolean;
}) {
  return (
    <div className="perf-metric">
      <span>{label}</span>
      <strong className={negative ? "is-down" : positive ? "is-up" : ""}>{value}</strong>
    </div>
  );
}

function EquityCurve({ curve }: { curve: Array<{ date: string; value: number }> | null }) {
  if (!curve || curve.length < 2) return <p className="perf-empty">暂无收益曲线数据。</p>;
  const values = curve.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 600;
  const height = 160;
  const points = curve.map((point, index) => {
    const x = (index / (curve.length - 1)) * width;
    const y = height - ((point.value - min) / range) * height;
    return `${x},${y}`;
  }).join(" ");
  return (
    <div className="perf-curve">
      <svg preserveAspectRatio="none" viewBox={`0 0 ${width} ${height}`}>
        <polyline fill="none" points={points} stroke="currentColor" strokeWidth="2" />
      </svg>
      <div className="perf-curve__labels">
        <span>{formatDate(curve[0].date)}</span>
        <span>{formatDate(curve[curve.length - 1].date)}</span>
      </div>
    </div>
  );
}

function SignalTable({ signals }: { signals: PerformanceSummary["signals"] }) {
  if (signals.length === 0) return <p className="perf-empty">暂无信号记录。</p>;
  return (
    <div className="perf-signals">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>标的</th>
            <th>方向</th>
            <th>结果</th>
          </tr>
        </thead>
        <tbody>
          {signals.slice(0, 20).map((signal, index) => (
            <tr key={`${signal.signal_date}-${index}`}>
              <td>{formatDate(signal.signal_date)}</td>
              <td>{signal.contract}</td>
              <td>
                {signal.direction === "LONG" ? "做多"
                  : signal.direction === "SHORT" ? "做空"
                    : signal.direction === "FLAT" ? "空仓" : "观望"}
              </td>
              <td className={signal.return_pct && signal.return_pct >= 0 ? "is-up" : "is-down"}>
                {signal.return_pct !== null ? formatPercent(signal.return_pct) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StrategyPerformanceView({ detail }: { detail: StrategyStoreDetail }) {
  const perf = detail.recent_performance;
  if (!perf) {
    return <p className="perf-empty">该策略暂最近三个月表现数据。</p>;
  }

  return (
    <section className="strategy-performance">
      <header>
        <span>最近三个月表现</span>
        <small>{formatDate(perf.start_date)} 至 {formatDate(perf.end_date)}</small>
      </header>
      <div className="perf-metrics">
        <PerformanceMetric
          label="整体涨跌"
          value={formatPercentNoDecimal(perf.total_return)}
          positive={(perf.total_return ?? 0) >= 0}
          negative={(perf.total_return ?? 0) < 0}
        />
        <PerformanceMetric label="信号次数" value={String(perf.signal_count)} />
        <PerformanceMetric label="盈利次数" value={String(perf.win_count)} />
        <PerformanceMetric label="亏损次数" value={String(perf.loss_count)} />
        <PerformanceMetric label="胜率" value={formatPercentNoDecimal(perf.win_rate)} />
        <PerformanceMetric
          label="最大回撤"
          value={formatPercentNoDecimal(perf.max_drawdown)}
          negative
        />
      </div>
      <EquityCurve curve={perf.equity_curve} />
      <SignalTable signals={perf.signals} />
      <p className="perf-disclaimer">
        以上表现基于历史行情计算，不代表未来收益。策略信号可能因市场变化而失效。
      </p>
    </section>
  );
}
