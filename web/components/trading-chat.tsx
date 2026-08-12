"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type {
  CaseView,
  ConversationMessage,
  ConversationSummary,
  ConversationView,
  StrategyManifest,
  UserEntitlement
} from "../lib/api";
import { ConversationSidebar } from "./conversation-sidebar";
import { DecisionSummary } from "./decision-summary";
import { StrategyAuditDrawer } from "./strategy-audit-drawer";
import { StrategySelector, strategyAccess } from "./strategy-selector";

type PendingClarification = {
  clarificationId: string;
  userMessage: string;
  interpretation: string;
  facts: { field: string; value: boolean | number | string }[];
};

function pendingClarification(caseView: CaseView): PendingClarification | null {
  const pending = [...caseView.clarification.history].reverse().find((item) => (
    item.status === "PENDING_CONFIRMATION"
    && item.sourceAnalysisId === caseView.clarification.sourceAnalysisId
  ));
  return pending ? {
    clarificationId: pending.clarificationId,
    userMessage: pending.userMessage,
    interpretation: pending.interpretation,
    facts: pending.facts.map((fact) => ({
      field: fact.field,
      value: fact.value
    }))
  } : null;
}

function messageTime(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? ""
    : new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit"
      }).format(date);
}

export function TradingChat({
  caseId,
  caseView,
  conversation,
  conversations,
  entitlements,
  strategies
}: {
  caseId: string;
  caseView: CaseView;
  conversation: ConversationView;
  conversations: ConversationSummary[];
  entitlements: UserEntitlement[];
  strategies: StrategyManifest[];
}) {
  const router = useRouter();
  const [messages, setMessages] = useState(conversation.messages);
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [privacyConfirmed, setPrivacyConfirmed] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auditOpen, setAuditOpen] = useState(false);
  const [unauthorizedStrategy, setUnauthorizedStrategy] = useState(
    null as StrategyManifest | null
  );
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const [clarificationProposal, setClarificationProposal] = (
    useState<PendingClarification | null>(() => pendingClarification(caseView))
  );
  const strategyValue = (
    `${conversation.strategy.strategyId}@${conversation.strategy.version}`
  );
  const needsClarification = caseView.clarification.questions.length > 0;

  useEffect(() => {
    setMessages(conversation.messages);
    setClarificationProposal(pendingClarification(caseView));
  }, [
    caseView,
    conversation.currentAnalysisId,
    conversation.messages
  ]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, clarificationProposal]);

  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (!content || sending) return;
    if (!needsClarification && files.length > 0) {
      await createAnalysisVersion(content);
      return;
    }
    setSending(true);
    setError(null);
    const localUser: ConversationMessage = {
      messageId: crypto.randomUUID(),
      role: "user",
      messageType: "USER_MESSAGE",
      content,
      createdAt: new Date().toISOString(),
      analysisId: conversation.currentAnalysisId,
      metadata: {}
    };
    setMessages((current) => [...current, localUser]);
    try {
      const endpoint = needsClarification
        ? `/api/cases/${encodeURIComponent(caseId)}/clarifications`
        : `/api/cases/${encodeURIComponent(caseId)}/messages`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID()
        },
        body: JSON.stringify({ message: content })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? `服务返回 ${response.status}`);
      }
      if (needsClarification) {
        if (payload.status === "AUTO_RESOLVED") {
          setMessage("");
          router.refresh();
          return;
        }
        setClarificationProposal({
          clarificationId: payload.clarification_id,
          userMessage: content,
          interpretation: payload.interpretation,
          facts: payload.facts
        });
      } else {
        setMessages((current) => [...current, {
          messageId: crypto.randomUUID(),
          role: "assistant",
          messageType: "STRATEGY_EXPLANATION",
          content: payload.answer,
          createdAt: new Date().toISOString(),
          analysisId: payload.source_analysis_id,
          metadata: {
            suggested_questions: payload.suggested_questions
          }
        }]);
      }
      setMessage("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "发送失败。"
      );
    } finally {
      setSending(false);
    }
  }

  async function createAnalysisVersion(content: string) {
    if (sending || (files.length > 0 && !privacyConfirmed)) return;
    setSending(true);
    setError(null);
    const formData = new FormData();
    formData.set("message", content);
    if (files.length > 0) formData.set("privacyConfirmed", "on");
    files.forEach((file) => formData.append("images", file, file.name));
    try {
      const response = await fetch(
        `/api/cases/${encodeURIComponent(caseId)}/analysis`,
        {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: formData
        }
      );
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? `服务返回 ${response.status}`);
      }
      setMessage("");
      setFiles([]);
      setPrivacyConfirmed(false);
      router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "重新分析失败。"
      );
    } finally {
      setSending(false);
    }
  }

  async function confirmClarification() {
    if (!clarificationProposal) return;
    setSending(true);
    const response = await fetch(
      `/api/cases/${encodeURIComponent(caseId)}/clarifications/`
      + `${encodeURIComponent(clarificationProposal.clarificationId)}/confirm`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": crypto.randomUUID()
        }
      }
    );
    setSending(false);
    if (response.ok) router.refresh();
  }

  return (
    <main className="chat-shell">
      <ConversationSidebar
        activeCaseId={caseId}
        conversations={conversations}
      />
      <section className="chat-workspace">
        <header className="chat-topbar">
          <div>
            <strong>{caseView.evidence[0]?.role ?? "中国期货"}</strong>
            <span>案例 {caseId.slice(0, 12)}</span>
          </div>
          <StrategySelector
            caseId={caseId}
            entitlements={entitlements}
            onSelected={(strategy) => {
              setUnauthorizedStrategy(null);
              setMessages((current) => [...current, {
                messageId: `strategy:${crypto.randomUUID()}`,
                role: "system",
                messageType: "STRATEGY_CHANGE",
                content: (
                  `已切换至${strategy.displayName} v${strategy.version}`
                ),
                createdAt: new Date().toISOString(),
                analysisId: null,
                metadata: {
                  strategy_id: strategy.strategyId,
                  strategy_version: strategy.version
                }
              }]);
            }}
            onUnauthorized={(strategy) => {
              const access = strategyAccess(strategy, entitlements);
              setMessages((current) => [...current, {
                messageId: `strategy:unauthorized:${crypto.randomUUID()}`,
                role: "system",
                messageType: "STRATEGY_UNAUTHORIZED",
                content: (
                  `${strategy.displayName}（v${strategy.version}）${access.label}。`
                  + `前往策略商店购买后可使用。`
                ),
                createdAt: new Date().toISOString(),
                analysisId: null,
                metadata: {
                  strategy_id: strategy.strategyId,
                  strategy_version: strategy.version
                }
              }]);
              setUnauthorizedStrategy(strategy);
            }}
            strategies={strategies}
            value={strategyValue}
          />
          <div className="chat-topbar__actions">
            <button
              disabled={sending}
              onClick={() => void createAnalysisVersion(
                "刷新公开行情并重新分析。"
              )}
              type="button"
            >
              刷新行情重新分析
            </button>
            <button onClick={() => setAuditOpen(true)} type="button">
              查看策略审计
            </button>
          </div>
        </header>
        {unauthorizedStrategy ? (
          <div className="chat-unauthorized-banner">
            <span>
              {unauthorizedStrategy.displayName} 需要购买后才能在此会话中使用。
            </span>
            <a
              href={`/store/${encodeURIComponent(unauthorizedStrategy.strategyId)}`}
              onClick={(event) => {
                event.preventDefault();
                router.push(`/store/${encodeURIComponent(unauthorizedStrategy.strategyId)}`);
              }}
            >
              去策略商店购买 →
            </a>
          </div>
        ) : null}
        <div className="chat-thread">
          {messages.map((item) => (
            <article
              className={`chat-message chat-message--${item.role}`}
              data-testid="chat-message"
              key={item.messageId}
            >
              <div className="chat-avatar">
                {item.role === "user" ? "你" : item.role === "system" ? "系" : "磐"}
              </div>
              <div className="chat-bubble">
                <header>
                  <strong>
                    {item.role === "user"
                      ? "你"
                      : item.role === "system"
                        ? "系统"
                        : "磐石交易AI"}
                  </strong>
                  <span>{messageTime(item.createdAt)}</span>
                </header>
                {(
                  item.messageType === "STRATEGY_CONCLUSION"
                  && item.analysisId === conversation.currentAnalysisId
                ) ? (
                  <div data-testid="strategy-conclusion">
                    <DecisionSummary data={caseView} />
                    <button
                      className="inline-audit"
                      onClick={() => setAuditOpen(true)}
                      type="button"
                    >
                      展开每一步依据
                    </button>
                  </div>
                ) : item.messageType === "STRATEGY_CONCLUSION" ? (
                  <div
                    className="historical-conclusion"
                    data-testid="historical-conclusion"
                  >
                    <strong>历史分析结论</strong>
                    <p>{item.content}</p>
                  </div>
                ) : (
                  <p>{item.content}</p>
                )}
                {item.analysisId ? (
                  <small data-testid="source-analysis-id">
                    依据分析 {item.analysisId}
                  </small>
                ) : null}
              </div>
            </article>
          ))}
          {needsClarification ? (
            <article className="chat-message chat-message--assistant">
              <div className="chat-avatar">磐</div>
              <div className="chat-bubble clarification-message">
                <header><strong>需要确认的私有事实</strong></header>
                <p>
                  截图与公开行情已优先自动核验。以下信息仍存在真实歧义，
                  直接在下方输入框补充即可：
                </p>
                <ul>
                  {caseView.clarification.questions.map((question) => (
                    <li key={question.questionId}>{question.question}</li>
                  ))}
                </ul>
                {clarificationProposal ? (
                  <div className="clarification-confirm">
                    <p>你补充：{clarificationProposal.userMessage}</p>
                    <strong>我理解为</strong>
                    <p>{clarificationProposal.interpretation}</p>
                    <button
                      disabled={sending}
                      onClick={() => void confirmClarification()}
                      type="button"
                    >
                      确认并重新分析
                    </button>
                  </div>
                ) : null}
              </div>
            </article>
          ) : null}
          <div ref={threadEndRef} />
        </div>
        <form className="chat-composer" onSubmit={send}>
          <textarea
            aria-label="继续追问"
            onChange={(event) => setMessage(event.target.value)}
            placeholder={
              needsClarification
                ? "补充上面仍不确定的信息…"
                : "继续追问结论、步骤或风险依据…"
            }
            rows={2}
            value={message}
          />
          {files.length > 0 ? (
            <div
              className="chat-attachment-preview"
              data-testid="chat-attachment-preview"
            >
              {files.map((file, index) => (
                <span key={`${file.name}-${index}`}>{file.name}</span>
              ))}
            </div>
          ) : null}
          {files.length > 0 ? (
            <label className="chat-privacy-line">
              <input
                aria-label="确认新增截图隐私授权"
                checked={privacyConfirmed}
                onChange={(event) => setPrivacyConfirmed(event.target.checked)}
                type="checkbox"
              />
              <span>确认新增截图可交给本机配置的多模态模型分析。</span>
            </label>
          ) : null}
          <div>
            <label className="chat-attach-control">
              <span>＋ 附件</span>
              <input
                accept="image/png,image/jpeg,image/webp"
                aria-label="上传新图表"
                disabled={sending || needsClarification}
                multiple
                onChange={(event) => {
                  setFiles(Array.from(event.target.files ?? []).slice(0, 2));
                }}
                type="file"
              />
            </label>
            <span>
              {needsClarification
                ? "补充只用于账户私有信息或真实歧义"
                : files.length > 0
                  ? "新增证据会创建新分析版本并保留旧结论"
                  : "追问只解释当前不可变分析，不会修改原结论"}
            </span>
            <button
              disabled={
                sending
                || !message.trim()
                || (files.length > 0 && !privacyConfirmed)
              }
              type="submit"
            >
              {sending
                ? "处理中"
                : files.length > 0
                  ? "用新证据重新分析"
                  : "发送"}
            </button>
          </div>
          {error ? <p role="alert">{error}</p> : null}
        </form>
      </section>
      <aside className="case-status-rail">
        <span>当前动作</span>
        <strong>{caseView.action}</strong>
        <dl>
          <div><dt>市场</dt><dd>{caseView.marketState}</dd></div>
          <div><dt>策略</dt><dd>{caseView.strategyManifest.displayName}</dd></div>
          <div><dt>进度</dt><dd>{caseView.progress}</dd></div>
          <div><dt>截止</dt><dd>{caseView.cutoff}</dd></div>
        </dl>
        <button onClick={() => setAuditOpen(true)} type="button">
          展开完整依据
        </button>
      </aside>
      {auditOpen ? (
        <StrategyAuditDrawer
          data={caseView}
          onClose={() => setAuditOpen(false)}
        />
      ) : null}
    </main>
  );
}
