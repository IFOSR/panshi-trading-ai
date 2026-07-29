import type { Milestone } from "../lib/api";
import { MilestoneCard } from "./milestone-card";

export function StrategyMilestoneRail({
  milestones,
  processLabel = "策略里程碑"
}: {
  milestones: Milestone[];
  processLabel?: string;
}) {
  return (
    <section className="rail">
      <header>
        <p className="eyebrow">AUDITABLE STRATEGY / 可审计策略</p>
        <h2>{processLabel}</h2>
      </header>
      <div className="rail__line" />
      {milestones.map((milestone) => <MilestoneCard key={milestone.number} milestone={milestone} />)}
    </section>
  );
}
