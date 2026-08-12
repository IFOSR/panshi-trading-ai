import { AnalysisInput } from "../components/analysis-input";
import { getMyEntitlements, getRecentConversations, getStrategies } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [strategies, conversations, entitlements] = await Promise.all([
    getStrategies(),
    getRecentConversations(),
    getMyEntitlements()
  ]);
  return (
    <AnalysisInput
      conversations={conversations}
      entitlements={entitlements}
      strategies={strategies}
    />
  );
}
