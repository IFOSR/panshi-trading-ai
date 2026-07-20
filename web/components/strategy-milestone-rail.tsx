import type { Milestone } from "../lib/api";
import { MilestoneCard } from "./milestone-card";

export function StrategyMilestoneRail({ milestones }: { milestones: Milestone[] }) {
  return (
    <section className="rail">
      <header><p className="eyebrow">AUDITABLE STRATEGY / 可审计策略</p><h2>八步执行账本</h2></header>
      <div className="rail__line" />
      {milestones.map((milestone) => <MilestoneCard key={milestone.number} milestone={milestone} />)}
    </section>
  );
}
