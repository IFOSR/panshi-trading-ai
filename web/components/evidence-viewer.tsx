export function EvidenceViewer() {
  return (
    <aside className="evidence">
      <p className="eyebrow">SOURCE EVIDENCE</p>
      <h3>原图证据</h3>
      <div className="evidence__frame">
        <span>STATE_DAILY</span>
        <strong>Codex · gpt-5.6-sol</strong>
        <small>未裁剪原图 / SHA-256 已登记</small>
      </div>
      <p>精确值仅来自可见文本或结构化行情校验；图形坐标不生成委托价格。</p>
    </aside>
  );
}
