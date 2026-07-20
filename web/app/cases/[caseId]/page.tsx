import { ChangeReport } from "../../../components/change-report";
import { DecisionSummary } from "../../../components/decision-summary";
import { EvidenceViewer } from "../../../components/evidence-viewer";
import { StrategyMilestoneRail } from "../../../components/strategy-milestone-rail";
import { getCaseView } from "../../../lib/api";

export default async function CasePage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const caseView = await getCaseView(caseId);
  return (
    <main>
      <nav><div className="brand">磐石<span>PANSHI</span></div><p>中国期货策略代理</p><code>{caseId}</code></nav>
      <DecisionSummary data={caseView} />
      <ChangeReport text={caseView.changes} />
      <div className="workspace">
        <StrategyMilestoneRail milestones={caseView.milestones} />
        <EvidenceViewer />
      </div>
      <footer>非自动交易系统 · 所有动作由确定性策略与独立风控生成</footer>
    </main>
  );
}
