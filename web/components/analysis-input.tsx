"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type {
  ConversationSummary,
  StrategyManifest,
  UserEntitlement
} from "../lib/api";
import { ConversationSidebar } from "./conversation-sidebar";
import { StrategySelector, strategyAccess } from "./strategy-selector";

type SubmissionStatus = "pending" | "running" | "completed" | "failed";

const stages = [
  ["case", "创建会话"],
  ["position", "固化持仓"],
  ["risk", "应用风控"],
  ["images", "保存证据"],
  ["analysis", "执行策略"]
] as const;
const PENDING_SUBMISSION_KEY = "panshi.pendingSubmissionId";
const PENDING_CASE_KEY = "panshi.pendingCaseId";

export function AnalysisInput({
  strategies,
  conversations,
  entitlements = []
}: {
  strategies: StrategyManifest[];
  conversations: ConversationSummary[];
  entitlements?: UserEntitlement[];
}) {
  const router = useRouter();
  const submissionId = useRef<string | null>(null);
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [strategyValue, setStrategyValue] = useState(
    strategies[0]
      ? `${strategies[0].strategyId}@${strategies[0].version}`
      : "structure_confirmation@1.0.0"
  );
  const [privacyConfirmed, setPrivacyConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recoveryCaseId, setRecoveryCaseId] = useState<string | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [progress, setProgress] = useState<Record<string, {
    status: SubmissionStatus;
    message: string;
  }> | null>(null);

  const selectedStrategy = strategies.find(
    (strategy) => `${strategy.strategyId}@${strategy.version}` === strategyValue
  );
  const selectedAccess = selectedStrategy
    ? strategyAccess(selectedStrategy, entitlements)
    : { accessible: true, label: "", variant: "free" as const };
  const canSubmit = selectedAccess.accessible;

  useEffect(() => {
    setRecoveryCaseId(sessionStorage.getItem(PENDING_CASE_KEY));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || files.length === 0 || !privacyConfirmed) return;
    if (!submissionId.current) {
      submissionId.current = (
        sessionStorage.getItem(PENDING_SUBMISSION_KEY)
        ?? crypto.randomUUID()
      );
      sessionStorage.setItem(PENDING_SUBMISSION_KEY, submissionId.current);
    }
    const [strategyId, strategyVersion] = strategyValue.split("@");
    const formData = new FormData();
    formData.set("submissionId", submissionId.current);
    if (recoveryCaseId) formData.set("resumeCaseId", recoveryCaseId);
    formData.set(
      "message",
      message.trim() || "请基于截图和公开行情分析当前应该如何操作。"
    );
    formData.set("positionDirection", "AUTO");
    formData.set("privacyConfirmed", "on");
    formData.set("strategyId", strategyId);
    formData.set("strategyVersion", strategyVersion);
    formData.set("dailyImage", files[0], files[0].name);
    if (files[1]) {
      formData.set("executionImage", files[1], files[1].name);
    }
    setSubmitting(true);
    setError(null);
    setProgress(Object.fromEntries(
      stages.map(([id]) => [
        id,
        { status: "pending" as const, message: "等待执行" }
      ])
    ));
    try {
      const response = await fetch("/api/analysis", {
        method: "POST",
        body: formData
      });
      if (!response.ok) {
        const payload = await response.json() as { detail?: string };
        throw new Error(payload.detail ?? `分析服务返回 ${response.status}`);
      }
      if (!response.body) throw new Error("分析服务未返回进度。");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completedCaseId: string | null = null;
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const item = JSON.parse(line) as {
            type: "progress" | "complete" | "error";
            stage?: string;
            status?: SubmissionStatus;
            message?: string;
            caseId?: string;
          };
          if (item.type === "progress" && item.stage && item.status) {
            if (item.caseId) {
              sessionStorage.setItem(PENDING_CASE_KEY, item.caseId);
              setRecoveryCaseId(item.caseId);
            }
            setProgress((current) => ({
              ...(current ?? {}),
              [item.stage as string]: {
                status: item.status as SubmissionStatus,
                message: item.message ?? ""
              }
            }));
          }
          if (item.type === "error") {
            if (item.caseId) {
              sessionStorage.setItem(PENDING_CASE_KEY, item.caseId);
              setRecoveryCaseId(item.caseId);
            }
            throw new Error(item.message ?? "分析失败。");
          }
          if (item.type === "complete" && item.caseId) {
            completedCaseId = item.caseId;
          }
        }
        if (done || completedCaseId) break;
      }
      if (!completedCaseId) throw new Error("分析完成但未返回案例标识。");
      sessionStorage.removeItem(PENDING_SUBMISSION_KEY);
      sessionStorage.removeItem(PENDING_CASE_KEY);
      submissionId.current = null;
      router.push(`/cases/${completedCaseId}`);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "分析失败。"
      );
      setSubmitting(false);
    }
  }

  function abandonSubmission() {
    sessionStorage.removeItem(PENDING_SUBMISSION_KEY);
    sessionStorage.removeItem(PENDING_CASE_KEY);
    submissionId.current = null;
    setMessage("");
    setFiles([]);
    setPrivacyConfirmed(false);
    setSubmitting(false);
    setError(null);
    setRecoveryCaseId(null);
    setProgress(null);
    setFileInputKey((current) => current + 1);
  }

  return (
    <main className="chat-shell chat-shell--home">
      <ConversationSidebar conversations={conversations} />
      <section className="chat-workspace home-chat">
        <nav className="home-top-nav">
          <Link href="/store">策略商店</Link>
          <Link href="/my-strategies">我的策略</Link>
        </nav>
        <header className="home-chat__header">
          <span>CHINA FUTURES · MULTIMODAL</span>
          <h1>磐石交易AI</h1>
          <p>
            发一张完整行情截图，告诉我你关心的问题。系统自动读取图表、
            补齐公开行情，并按所选策略逐步生成可审计结论。
          </p>
        </header>
        <div className="home-chat__prompt">
          <div className="chat-avatar">磐</div>
          <div>
            <strong>开始前，请尽量保留完整图表</strong>
            <p>截图必须包含：</p>
            <ul>
              <li>合约或品种标题</li>
              <li>周期标识</li>
              <li>完整价格轴</li>
              <li>最新 K 线及日期或时间</li>
              <li>当前使用的指标区域</li>
            </ul>
            <small>
              收盘状态、持仓量和执行周期优先由公开行情自动补齐。
            </small>
          </div>
        </div>
        <form className="initial-composer" onSubmit={submit}>
          <textarea
            aria-label="告诉磐石你想分析什么"
            disabled={submitting}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="例如：分析 cf2609，我持有多单，当前应该继续持有、减仓还是退出？"
            rows={4}
            value={message}
          />
          {files.length > 0 ? (
            <div className="attachment-preview" data-testid="attachment-preview">
              {files.map((file, index) => (
                <span key={`${file.name}-${index}`}>
                  {index === 0 ? "日线" : "执行周期"} · {file.name}
                </span>
              ))}
            </div>
          ) : null}
          <div className="composer-controls">
            <label className="attach-control">
              <span>＋ 上传图表</span>
              <input
                accept="image/png,image/jpeg,image/webp"
                aria-label="上传图表截图"
                disabled={submitting}
                key={fileInputKey}
                multiple
                onChange={(event) => {
                  setFiles(Array.from(event.target.files ?? []).slice(0, 2));
                }}
                type="file"
              />
            </label>
            <StrategySelector
              disabled={submitting}
              entitlements={entitlements}
              onSelected={(strategy) => setStrategyValue(
                `${strategy.strategyId}@${strategy.version}`
              )}
              onUnauthorized={() => {}}
              strategies={strategies}
              value={strategyValue}
            />
            <button
              disabled={submitting || files.length === 0 || !privacyConfirmed || !canSubmit}
              type="submit"
            >
              {submitting ? "分析中" : "发送并分析"}
            </button>
          </div>
          {!selectedAccess.accessible && selectedStrategy ? (
            <p className="strategy-access-hint">
              {selectedStrategy.displayName} 需要购买后才能使用。
              <a href={`/store/${encodeURIComponent(selectedStrategy.strategyId)}`}>
                去策略商店购买 →
              </a>
            </p>
          ) : null}
          <label className="privacy-line">
            <input
              aria-label="已确认截图不含无关个人敏感信息"
              checked={privacyConfirmed}
              disabled={submitting}
              onChange={(event) => setPrivacyConfirmed(event.target.checked)}
              type="checkbox"
            />
            <span>
              已确认截图不含无关个人敏感信息，并同意交给本机配置的多模态模型分析。
            </span>
          </label>
          {progress ? (
            <div className="compact-progress" data-testid="submission-progress">
              {stages.map(([id, label]) => (
                <div className={`is-${progress[id]?.status}`} key={id}>
                  <b>{label}</b>
                  <span>{progress[id]?.message}</span>
                </div>
              ))}
            </div>
          ) : null}
          {recoveryCaseId && !error ? (
            <div className="submission-recovery">
              <span>检测到尚未完成的分析会话。</span>
              <a href={`/cases/${recoveryCaseId}`}>查看已创建会话</a>
            </div>
          ) : null}
          {error ? (
            <div className="composer-error" role="alert">
              <p>{error}</p>
              <div>
                {recoveryCaseId ? (
                  <a href={`/cases/${recoveryCaseId}`}>查看已创建会话</a>
                ) : null}
                <button onClick={abandonSubmission} type="button">
                  放弃并新建会话
                </button>
              </div>
            </div>
          ) : null}
        </form>
      </section>
      <aside className="home-principles">
        <span>分析原则</span>
        <strong>先证据，后策略，再动作</strong>
        <p>模型负责图像理解，策略插件负责里程碑，独立风控决定最终动作边界。</p>
        <dl>
          <div><dt>图像</dt><dd>Codex 优先</dd></div>
          <div><dt>数据</dt><dd>公开渠道自动补齐</dd></div>
          <div><dt>结论</dt><dd>与每一步严格对齐</dd></div>
        </dl>
      </aside>
    </main>
  );
}
