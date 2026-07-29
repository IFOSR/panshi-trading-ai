"use client";

import type { CaseView } from "../lib/api";
import { ChangeReport } from "./change-report";
import { EvidenceViewer } from "./evidence-viewer";
import { StrategyMilestoneRail } from "./strategy-milestone-rail";

export function StrategyAuditDrawer({
  data,
  onClose
}: {
  data: CaseView;
  onClose: () => void;
}) {
  return (
    <div className="audit-layer" role="presentation">
      <button
        aria-label="关闭策略审计"
        className="audit-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        aria-label="策略审计"
        className="strategy-audit-drawer"
        data-testid="strategy-audit-drawer"
      >
        <header>
          <div>
            <span>STRATEGY AUDIT</span>
            <h2>
              {data.strategyManifest.displayName} v
              {data.strategyManifest.version}
            </h2>
            <p>
              {data.strategyManifest.processLabel} · {data.progress}
            </p>
          </div>
          <button onClick={onClose} type="button">关闭</button>
        </header>
        <ChangeReport data={data.change} />
        <StrategyMilestoneRail
          milestones={data.milestones}
          processLabel={data.strategyManifest.processLabel}
        />
        <EvidenceViewer evidence={data.evidence} />
      </aside>
    </div>
  );
}
