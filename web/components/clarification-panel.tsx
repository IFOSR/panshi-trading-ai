"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  ClarificationFact,
  ClarificationHistoryItem,
  ClarificationView
} from "../lib/api";

const fieldLabels: Record<string, string> = {
  state_bar_closed: "日线收盘状态",
  execution_bar_closed: "60 分钟收盘状态",
  position_behavior_state: "持仓行为",
  open_interest_change: "持仓量变化",
  price_confirmation: "价格确认",
  price_confirmation_direction: "价格确认方向",
  price_confirmation_type: "价格确认形态",
  contract: "合约",
  timeframe: "周期",
  cutoff_time: "截止时间"
};

type PendingProposalResponse = {
  clarification_id: string;
  source_analysis_id: string;
  user_message: string;
  facts: {
    question_id: string;
    field: string;
    value: boolean | number | string;
    explanation: string;
    resolves_blockers: string[];
  }[];
  unresolved_question_ids: string[];
  interpretation: string;
  provider: string;
  model: string;
  status: "PENDING_CONFIRMATION";
};

type AutoResolvedResponse = {
  clarification_id: string;
  source_analysis_id: string;
  result_analysis_id: string;
  user_message: string;
  facts: [];
  resolved_question_ids: string[];
  unresolved_question_ids: [];
  interpretation: string;
  provider: "automatic-evidence-refresh";
  model: "deterministic";
  status: "AUTO_RESOLVED";
};

type ProposalResponse = PendingProposalResponse | AutoResolvedResponse;

function proposalFromResponse(
  payload: PendingProposalResponse
): ClarificationHistoryItem {
  return {
    clarificationId: payload.clarification_id,
    sourceAnalysisId: payload.source_analysis_id,
    userMessage: payload.user_message,
    facts: payload.facts.map((fact) => ({
      questionId: fact.question_id,
      field: fact.field,
      value: fact.value,
      explanation: fact.explanation,
      resolvesBlockers: fact.resolves_blockers
    })),
    unresolvedQuestionIds: payload.unresolved_question_ids,
    interpretation: payload.interpretation,
    provider: payload.provider,
    model: payload.model,
    status: payload.status,
    confirmedAt: null,
    resultAnalysisId: null
  };
}

function factValue(fact: ClarificationFact): string {
  if (typeof fact.value === "boolean") return fact.value ? "是" : "否";
  return String(fact.value);
}

async function responseDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string };
    if (payload.detail) return payload.detail;
  } catch {
    // Use a stable local fallback when the upstream body is not JSON.
  }
  return `澄清服务返回 ${response.status}`;
}

export function ClarificationPanel({
  caseId,
  data,
  automaticRefreshRequired
}: {
  caseId: string;
  data: ClarificationView;
  automaticRefreshRequired: boolean;
}) {
  const router = useRouter();
  const initialPending = [...data.history]
    .reverse()
    .find(
      (item) => (
        item.status === "PENDING_CONFIRMATION"
        && item.sourceAnalysisId === data.sourceAnalysisId
      )
    ) ?? null;
  const messageRef = useRef<HTMLTextAreaElement | null>(null);
  const submissionAttemptRef = useRef<{
    message: string;
    idempotencyKey: string;
  } | null>(null);
  const [proposal, setProposal] = useState<ClarificationHistoryItem | null>(
    initialPending
  );
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmedHistory = data.history.filter(
    (item) => item.status === "CONFIRMED"
  );

  async function interpret(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const userMessage = messageRef.current?.value.trim() ?? "";
    const message = userMessage || (
      "请先重新读取截图并刷新公开行情；"
      + "只有仍无法自动确认的账户私有信息或真实歧义才需要用户补充。"
    );
    if (submitting) return;
    if (
      !submissionAttemptRef.current
      || submissionAttemptRef.current.message !== message
    ) {
      submissionAttemptRef.current = {
        message,
        idempotencyKey: crypto.randomUUID()
      };
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/cases/${encodeURIComponent(caseId)}/clarifications`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": submissionAttemptRef.current.idempotencyKey
          },
          body: JSON.stringify({ message })
        }
      );
      if (!response.ok) throw new Error(await responseDetail(response));
      const payload = await response.json() as ProposalResponse;
      submissionAttemptRef.current = null;
      if (payload.status === "AUTO_RESOLVED") {
        setProposal(null);
        if (messageRef.current) messageRef.current.value = "";
        router.refresh();
        return;
      }
      setProposal(proposalFromResponse(payload));
      if (data.questions.length === 0) router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "无法解析补充信息。"
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function confirm() {
    if (!proposal || confirming) return;
    setConfirming(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/cases/${encodeURIComponent(caseId)}/clarifications/${encodeURIComponent(proposal.clarificationId)}/confirm`,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": crypto.randomUUID()
          }
        }
      );
      if (!response.ok) throw new Error(await responseDetail(response));
      router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "无法确认并重新评估。"
      );
      setConfirming(false);
    }
  }

  return (
    <section className="clarification" data-testid="clarification-panel">
      <header className="clarification__header">
        <div>
          <p className="eyebrow">STRATEGY CLARIFICATION</p>
          <h2>补齐策略不确定项</h2>
          <p>
            系统先重新读取截图并刷新公开行情，仍无法确认时才需要你补充。
            用户补充只用于账户私有信息或真实歧义。
          </p>
        </div>
        <aside>
          <span>待确认</span>
          <strong>{data.questions.length}</strong>
          <small>不会覆盖明确截图证据或硬风控</small>
        </aside>
      </header>

      {confirmedHistory.length > 0 ? (
        <div className="clarification__confirmed">
          <b>用户确认事实已进入策略证据链</b>
          <span>
            {confirmedHistory.length} 次确认 · 最新分析已重新计算全部八步
          </span>
        </div>
      ) : null}

      {data.questions.length > 0 ? (
        <div className="clarification__layout">
          <div className="clarification__questions">
            {data.questions.map((question) => (
              <article
                className="clarification-question"
                data-testid="clarification-question"
                key={question.questionId}
              >
                <div className="clarification-question__step">
                  <span>影响第 {question.milestoneNumber} 步</span>
                  <b>{String(question.milestoneNumber).padStart(2, "0")}</b>
                </div>
                <div>
                  <strong>{question.uncertainty}</strong>
                  <p>{question.question}</p>
                  <small>
                    阻断：{question.blockingIssues.join("；")}
                  </small>
                  <em>例如：{question.answerExamples.join(" / ")}</em>
                </div>
              </article>
            ))}
          </div>

          <div className="clarification__conversation">
            <form onSubmit={interpret}>
              <label>
                <span>可选说明</span>
                <textarea
                  ref={messageRef}
                  defaultValue={initialPending?.userMessage ?? ""}
                  rows={6}
                  placeholder={
                    "无需填写即可自动核验。仅在截图识别有误，"
                    + "或需要补充持仓、成本等账户私有信息时输入。"
                  }
                />
              </label>
              <button disabled={submitting}>
                {submitting
                  ? "正在自动核验"
                  : proposal
                    ? "修正理解"
                    : "自动核验并处理"}
              </button>
            </form>

            {proposal ? (
              <article
                className="clarification-preview"
                data-testid="clarification-preview"
              >
                <header>
                  <span>我理解为</span>
                  <small>{proposal.provider} · {proposal.model}</small>
                </header>
                <p>{proposal.interpretation}</p>
                <dl>
                  {proposal.facts.map((fact, index) => (
                    <div key={`${fact.field}-${index}`}>
                      <dt>{fieldLabels[fact.field] ?? fact.field}</dt>
                      <dd>{factValue(fact)}</dd>
                    </div>
                  ))}
                </dl>
                <div className="clarification-preview__unresolved">
                  <b>仍需补充</b>
                  <span>
                    {proposal.unresolvedQuestionIds.length > 0
                      ? proposal.unresolvedQuestionIds.join("；")
                      : "无，当前回答可进入确认。"}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={confirm}
                  disabled={confirming || proposal.facts.length === 0}
                >
                  {confirming ? "正在重新评估" : "确认并重新评估"}
                </button>
              </article>
            ) : (
              <aside className="clarification__empty-preview">
                <span>自动核验优先</span>
                <p>
                  系统会先复用多模态截图识别并刷新公开行情；
                  仅剩用户私有事实时，才在这里显示理解预览。
                </p>
              </aside>
            )}
            {error ? <p className="clarification__error" role="alert">{error}</p> : null}
          </div>
        </div>
      ) : (
        <div className="clarification__resolved">
          {automaticRefreshRequired ? (
            <>
              <strong>当前阻塞应由系统自动处理，无需你填写数据。</strong>
              <p>
                系统将重新调用多模态模型读取原图，并刷新公开行情、截止时间和收盘状态。
              </p>
              <form onSubmit={interpret}>
                <button disabled={submitting}>
                  {submitting
                    ? "正在重新核验"
                    : "重新读取截图并刷新行情"}
                </button>
              </form>
            </>
          ) : (
            <>
              <strong>截图与公开行情已自动核验，当前无需用户补充。</strong>
              <p>系统已依据最新可用证据重新计算策略；账户私有信息仍以用户明确提交为准。</p>
            </>
          )}
          {error ? <p className="clarification__error" role="alert">{error}</p> : null}
        </div>
      )}
    </section>
  );
}
