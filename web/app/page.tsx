import { AnalysisInput } from "../components/analysis-input";
import { getRecentConversations, getStrategies } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [strategies, conversations] = await Promise.all([
    getStrategies(),
    getRecentConversations()
  ]);
  return (
    <AnalysisInput
      conversations={conversations}
      strategies={strategies}
    />
  );
}
