type Props = {
  data: {
    action: string; marketState: string; strategy: string; progress: string;
    blockers: string[]; nextMilestone: string; cutoff: string;
  };
};

export function DecisionSummary({ data }: Props) {
  return (
    <section className="decision">
      <div className="decision__stamp">策略结论</div>
      <div>
        <p className="eyebrow">CURRENT ACTION / 当前操作</p>
        <h1 data-testid="current-action">{data.action}</h1>
        <p className="decision__reason">
          当前证据只能支持结构判断，不能支持精确交易动作。先补齐阻断信息，不追单。
        </p>
      </div>
      <dl className="decision__grid">
        <div><dt>市场状态</dt><dd>{data.marketState}</dd></div>
        <div><dt>启用策略</dt><dd>{data.strategy}</dd></div>
        <div><dt>策略进度</dt><dd>{data.progress}</dd></div>
        <div><dt>数据截止</dt><dd>{data.cutoff}</dd></div>
      </dl>
      <div className="blockers">
        <span>关键阻断</span>
        {data.blockers.map((item) => <b key={item}>{item}</b>)}
      </div>
      <div className="next">
        <span>下一里程碑</span>
        <strong>{data.nextMilestone}</strong>
      </div>
    </section>
  );
}
