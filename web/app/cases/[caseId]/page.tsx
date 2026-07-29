import Link from "next/link";

import { TradingChat } from "../../../components/trading-chat";
import {
  getCaseView,
  getConversation,
  getRecentConversations,
  getStrategies
} from "../../../lib/api";

export default async function CasePage({
  params
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  const [result, conversation, conversations, strategies] = await Promise.all([
    getCaseView(caseId),
    getConversation(caseId),
    getRecentConversations(),
    getStrategies()
  ]);
  if (result.status !== "ready" || !conversation) {
    const errorMessage = result.status === "ready"
      ? "无法读取案例对话。"
      : result.message;
    return (
      <main className="case-error">
        <div className="sidebar-brand">
          <strong>磐石交易AI</strong>
          <span>PANSHI TRADING AI</span>
        </div>
        <section
          data-testid={
            result.status === "not-found" ? "case-not-found" : "case-state"
          }
        >
          <span>{result.status.toUpperCase()}</span>
          <h1>{errorMessage}</h1>
          <p>系统不会用演示数据替代真实分析。</p>
          <Link href="/">返回新建分析</Link>
        </section>
      </main>
    );
  }
  return (
    <TradingChat
      caseId={caseId}
      caseView={result.data}
      conversation={conversation}
      conversations={conversations}
      strategies={strategies}
    />
  );
}
