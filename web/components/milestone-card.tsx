import type { Milestone } from "../lib/api";

export function MilestoneCard({ milestone }: { milestone: Milestone }) {
  return (
    <details className={`milestone milestone--${milestone.status.toLowerCase()}`} data-testid="strategy-milestone">
      <summary>
        <span className="milestone__number">{String(milestone.number).padStart(2, "0")}</span>
        <span className="milestone__main"><b>{milestone.title}</b><small>{milestone.result}</small></span>
        <span className="status">{milestone.status}</span>
        <span className="chevron">＋</span>
      </summary>
      <div className="audit">
        <div><span>输入</span><p>{milestone.input}</p></div>
        <div><span>规则 {milestone.rule}</span><p>当前值按确定性规则评估，不使用隐藏思维过程。</p></div>
        <div><span>证据与来源</span><p>{milestone.evidence}</p></div>
        <div><span>下一条件</span><p>{milestone.next}</p></div>
      </div>
    </details>
  );
}
