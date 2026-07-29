export function ChangeReport({ data }: {
  data: {
    summary: string;
    previousAction: string | null;
    currentAction: string;
    changedSteps: number[];
  };
}) {
  return (
    <aside className="change">
      <span>本次变化</span>
      <p>{data.summary}</p>
      <div>
        <i>上次：{data.previousAction ?? "首次分析"}</i>
        <b>→</b>
        <i>本次：{data.currentAction}</i>
        <em>变化步骤：{data.changedSteps.join(", ") || "无"}</em>
      </div>
    </aside>
  );
}
