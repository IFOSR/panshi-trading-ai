import { AnalysisInput } from "../components/analysis-input";
import {
  getAgentBackends,
  getRecentConversations,
  getStrategies
} from "../lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [strategies, agents, conversations] = await Promise.all([
    getStrategies(),
    getAgentBackends(),
    getRecentConversations()
  ]);
  return (
    <AnalysisInput
      agents={agents}
      conversations={conversations}
      strategies={strategies}
    />
  );
}
