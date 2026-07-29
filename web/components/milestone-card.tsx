import type { Milestone } from "../lib/api";

function providerLabel(provider: string | null): string {
  return provider === "codex" ? "Codex" : provider ?? "来源未知";
}

function statusLabel(status: Milestone["status"]): string {
  return {
    CONFIRMED: "已确认",
    CANDIDATE: "条件未触发",
    BLOCKED: "证据不足",
    INVALIDATED: "已失效"
  }[status];
}

export function MilestoneCard({ milestone }: { milestone: Milestone }) {
  return (
    <details className={`milestone milestone--${milestone.status.toLowerCase()}`} data-testid="strategy-milestone">
      <summary>
        <span className="milestone__number">{String(milestone.number).padStart(2, "0")}</span>
        <span className="milestone__main"><b>{milestone.title}</b><small>{milestone.result}</small></span>
        <span className="status">{statusLabel(milestone.status)}</span>
        <span className="chevron">＋</span>
      </summary>
      <div className="audit">
        <section className="audit__section">
          <span>实际输入</span>
          <dl className="audit__fields">
            {milestone.inputs.length > 0 ? milestone.inputs.map((field) => (
              <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>
            )) : <p>{milestone.details.length > 0
              ? "本步使用的输入见右侧里程碑详情。"
              : "当前响应未提供显式输入。"}</p>}
          </dl>
        </section>
        <section className="audit__section">
          <span>里程碑详情</span>
          <dl className="audit__fields">
            {milestone.details.length > 0 ? milestone.details.map((field) => (
              <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>
            )) : <p>无额外详情。</p>}
          </dl>
        </section>
        <section className="audit__section">
          <span>规则 {milestone.rules.join(", ") || "未提供"}</span>
          <p>展示结构化输入与确定性规则结果，不展示隐藏思维过程。</p>
        </section>
        <section className="audit__section">
          <span>结构化比较</span>
          <div className="audit__comparisons">
            {milestone.comparisons.length > 0 ? milestone.comparisons.map((comparison) => (
              <article key={`${comparison.label}-${comparison.actual}`}>
                <strong>{comparison.label}</strong>
                <p>实际 {comparison.actual}</p>
                <p>目标 {comparison.expected}</p>
                <b>{comparison.result}</b>
                {comparison.source ? <small>{comparison.source}</small> : null}
              </article>
            )) : <p>当前步骤无结构化比较。</p>}
          </div>
        </section>
        <section className="audit__section audit__section--wide">
          <span>证据引用与来源</span>
          <div className="milestone-evidence">
            {milestone.evidence.length > 0 ? milestone.evidence.map((item) => (
              <article
                key={`${item.reference}-${item.imageRole ?? "unresolved"}`}
                data-testid={
                  item.provenance === "user_confirmed"
                    ? "user-confirmed-evidence"
                    : undefined
                }
              >
                {item.imageUrl ? (
                  <img
                    src={item.imageUrl}
                    alt={`${item.imageRole ?? "未知角色"} 里程碑证据`}
                    data-testid="milestone-evidence-image"
                  />
                ) : null}
                <div>
                  <span>{item.reference}</span>
                  <strong>{item.kind} · {item.value}</strong>
                  {item.confidence === null
                    ? null
                    : <p>置信度 {Math.round(item.confidence * 100)}%</p>}
                  <p>{item.description ?? item.visibleText ?? "无额外可见文本"}</p>
                  <small>
                    {item.imageRole ?? "未解析图像"} · {providerLabel(item.provider)}
                    {item.model ? ` · ${item.model}` : ""} · {item.provenance ?? "来源未知"}
                  </small>
                </div>
              </article>
            )) : (
              <p>{milestone.evidenceRefs.length > 0
                ? milestone.evidenceRefs.join("；")
                : "当前步骤未声明证据引用。"}</p>
            )}
          </div>
        </section>
        <section className="audit__section">
          <span>上次 / 本次变化</span>
          <div className="audit__change">
            <article>
              <small>上次结果</small>
              <strong>{milestone.change.previous
                ? `${milestone.change.previous.status} · ${milestone.change.previous.result}`
                : "首次分析"}</strong>
            </article>
            <article>
              <small>本次结果</small>
              <strong>{milestone.change.current.status} · {milestone.change.current.result}</strong>
            </article>
            <b>{milestone.change.changed ? "本步已变化" : "本步未变化"}</b>
          </div>
        </section>
        <section className="audit__section">
          <span>阻断与下一条件</span>
          <p>{milestone.blockers.join("；") || "当前步骤无阻断。"}</p>
          <p>{milestone.nextConditions.join("；") || "保持当前状态。"}</p>
        </section>
      </div>
    </details>
  );
}
