import type { EvidenceImage } from "../lib/api";

function providerLabel(provider: string): string {
  return provider === "codex" ? "Codex" : provider;
}

export function EvidenceViewer({ evidence }: { evidence: EvidenceImage[] }) {
  return (
    <aside className="evidence">
      <p className="eyebrow">SOURCE EVIDENCE</p>
      <h3>多图原始证据</h3>
      <div className="evidence__set">
        {evidence.map((image, imageIndex) => (
          <section className="evidence__item" key={`${image.sha256}-${imageIndex}`}>
            <div className="evidence__frame" data-testid="evidence-image">
              {image.imageUrl ? (
                <img
                  src={image.imageUrl}
                  alt={`${image.role} 用户上传的未裁剪原始行情截图`}
                  data-testid={imageIndex === 0
                    ? "original-evidence-image"
                    : "evidence-image-secondary"}
                />
              ) : <div className="evidence__missing">原图不可用</div>}
            </div>
            <div className="evidence__meta">
              <span>{image.role}</span>
              <strong>{providerLabel(image.provider)} · {image.model}</strong>
              <small>{image.promptVersion} · {image.allowedUsage}</small>
              <small>SHA-256 {image.sha256.slice(0, 12)}</small>
            </div>
            <div className="evidence__facts">
              {image.observations.map((item) => (
                <article key={item.id}>
                  <span>{item.kind} · 置信度 {Math.round(item.confidence * 100)}%</span>
                  <strong>{item.value}</strong>
                  <p>{item.description ?? item.visibleText ?? "无额外可见文本"}</p>
                  <small>{item.provenance}</small>
                </article>
              ))}
              {Object.entries(image.fieldProvenance).map(([field, source]) => (
                <article key={field}>
                  <span>字段来源</span>
                  <strong>{field}</strong>
                  <small>{source}</small>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
      <p>精确值仅来自可见文本或结构化行情校验；图形坐标不生成委托价格。</p>
    </aside>
  );
}
