export function ChangeReport({ text }: { text: string }) {
  return (
    <aside className="change">
      <span>本次变化</span>
      <p>{text}</p>
      <div><i>上次：等待数据</i><b>→</b><i>本次：等待数据</i></div>
    </aside>
  );
}
