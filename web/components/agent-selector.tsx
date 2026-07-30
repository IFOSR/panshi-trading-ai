"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type {
  AgentBackendManifest,
  AgentModelManifest
} from "../lib/api";

function modelFor(
  backend: AgentBackendManifest | undefined,
  modelId: string
): AgentModelManifest | undefined {
  return backend?.models.find((model) => model.modelId === modelId);
}

export function AgentSelector({
  agents,
  backendId,
  modelId,
  caseId,
  disabled,
  onSelected
}: {
  agents: AgentBackendManifest[];
  backendId: string;
  modelId: string;
  caseId?: string;
  disabled?: boolean;
  onSelected?: (
    backend: AgentBackendManifest,
    model: AgentModelManifest
  ) => void;
}) {
  const router = useRouter();
  const [selectedBackendId, setSelectedBackendId] = useState(backendId);
  const [selectedModelId, setSelectedModelId] = useState(modelId);
  const [changing, setChanging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const backend = (
    agents.find((item) => item.backendId === selectedBackendId)
    ?? agents[0]
  );
  const model = modelFor(backend, selectedModelId);
  const unavailableMessages = [
    ...agents
      .filter((item) => !item.available)
      .map(
        (item) => (
          `${item.displayName}：${item.unavailableReason ?? "当前不可用"}`
        )
      ),
    ...(backend?.available
      ? backend.models
        .filter((item) => !item.available)
        .map(
          (item) => (
            `${item.displayName}：${item.unavailableReason ?? "当前不可用"}`
          )
        )
      : [])
  ];

  useEffect(() => {
    setSelectedBackendId(backendId);
    setSelectedModelId(modelId);
  }, [backendId, modelId]);

  async function applySelection(
    nextBackend: AgentBackendManifest,
    nextModel: AgentModelManifest
  ) {
    const previousBackendId = selectedBackendId;
    const previousModelId = selectedModelId;
    setSelectedBackendId(nextBackend.backendId);
    setSelectedModelId(nextModel.modelId);
    setError(null);
    if (!caseId) {
      onSelected?.(nextBackend, nextModel);
      return;
    }
    setChanging(true);
    try {
      const response = await fetch(
        `/api/cases/${encodeURIComponent(caseId)}/agent-backend`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID()
          },
          body: JSON.stringify({
            backend_id: nextBackend.backendId,
            model_id: nextModel.modelId
          })
        }
      );
      const payload = await response.json() as { detail?: string };
      if (!response.ok) {
        throw new Error(payload.detail ?? `Agent 服务返回 ${response.status}`);
      }
      onSelected?.(nextBackend, nextModel);
      router.refresh();
    } catch (requestError) {
      setSelectedBackendId(previousBackendId);
      setSelectedModelId(previousModelId);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Agent 切换失败。"
      );
      // A failed response can arrive after the backend committed the switch.
      // Refreshing reconciles the selector and messages with server truth.
      router.refresh();
    } finally {
      setChanging(false);
    }
  }

  function selectBackend(nextBackendId: string) {
    const nextBackend = agents.find(
      (item) => item.backendId === nextBackendId
    );
    if (!nextBackend) return;
    const nextModel = (
      modelFor(nextBackend, nextBackend.defaultModelId)
      ?? nextBackend.models[0]
    );
    setSelectedBackendId(nextBackend.backendId);
    setSelectedModelId(nextModel?.modelId ?? "");
    setError(null);
    if (nextModel?.available) {
      void applySelection(nextBackend, nextModel);
    }
  }

  function selectModel(nextModelId: string) {
    if (!backend) return;
    const nextModel = modelFor(backend, nextModelId);
    if (!nextModel?.available) return;
    void applySelection(backend, nextModel);
  }

  return (
    <div className="agent-selector">
      <label>
        <span>分析 Agent</span>
        <select
          aria-label="分析 Agent"
          disabled={disabled || changing || agents.length === 0}
          onChange={(event) => selectBackend(event.target.value)}
          value={backend?.backendId ?? ""}
        >
          {agents.map((item) => (
            <option
              disabled={!item.available}
              key={item.backendId}
              value={item.backendId}
            >
              {item.displayName}{!item.available ? " · 不可用" : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>分析模型</span>
        <select
          aria-label="分析模型"
          disabled={disabled || changing || !backend}
          onChange={(event) => selectModel(event.target.value)}
          value={model?.modelId ?? backend?.defaultModelId ?? ""}
        >
          {(backend?.models ?? []).map((item) => (
            <option
              disabled={!item.available}
              key={item.modelId}
              value={item.modelId}
            >
              {item.displayName}
              {!item.available ? ` · 不可用` : ""}
            </option>
          ))}
        </select>
      </label>
      {unavailableMessages.length > 0 ? (
        <small data-testid="agent-availability">
          {unavailableMessages.join("；")}
        </small>
      ) : null}
      {error ? <small className="agent-selector__error">{error}</small> : null}
    </div>
  );
}
