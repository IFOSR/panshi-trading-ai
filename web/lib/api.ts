export type Milestone = {
  number: number;
  title: string;
  status: "CONFIRMED" | "CANDIDATE" | "BLOCKED" | "INVALIDATED";
  result: string;
  rules: string[];
  inputs: AuditField[];
  details: AuditField[];
  comparisons: StructuredComparison[];
  blockers: string[];
  nextConditions: string[];
  evidenceRefs: string[];
  evidence: MilestoneEvidence[];
  change: {
    changed: boolean;
    previous: MilestoneSnapshot | null;
    current: MilestoneSnapshot;
  };
};

export type AuditField = {
  label: string;
  value: string;
};

export type StructuredComparison = {
  label: string;
  actual: string;
  expected: string;
  result: string;
  source: string | null;
};

export type MilestoneSnapshot = {
  status: Milestone["status"];
  result: string;
};

export type EvidenceObservation = {
  id: string;
  kind: string;
  value: string;
  confidence: number;
  provenance: string;
  visibleText: string | null;
  description: string | null;
};

export type EvidenceImage = {
  role: string;
  provider: string;
  model: string;
  sha256: string;
  imageUrl: string | null;
  allowedUsage: string;
  promptVersion: string;
  observations: EvidenceObservation[];
  fieldProvenance: Record<string, string>;
};

export type MilestoneEvidence = {
  id: string;
  reference: string;
  kind: string;
  value: string;
  confidence: number | null;
  provenance: string | null;
  visibleText: string | null;
  description: string | null;
  imageUrl: string | null;
  imageRole: string | null;
  provider: string | null;
  model: string | null;
};

export type PositionBranch = {
  scope: "FLAT" | "LONG" | "SHORT";
  action: string;
  label: string;
  guidance: string;
};

export type ClarificationQuestion = {
  questionId: string;
  field: string;
  milestoneNumber: number;
  uncertainty: string;
  question: string;
  answerExamples: string[];
  blockingIssues: string[];
};

export type ClarificationFact = {
  questionId: string;
  field: string;
  value: boolean | number | string;
  explanation: string;
  resolvesBlockers: string[];
};

export type ClarificationHistoryItem = {
  clarificationId: string;
  sourceAnalysisId: string;
  userMessage: string;
  facts: ClarificationFact[];
  unresolvedQuestionIds: string[];
  interpretation: string;
  provider: string;
  model: string;
  status: "PENDING_CONFIRMATION" | "CONFIRMED";
  confirmedAt: string | null;
  resultAnalysisId: string | null;
};

export type ClarificationView = {
  sourceAnalysisId: string | null;
  questions: ClarificationQuestion[];
  history: ClarificationHistoryItem[];
};

export type StrategyManifest = {
  strategyId: string;
  displayName: string;
  version: string;
  status: "stable" | "test" | "disabled";
  processLabel: string;
  supportedMarkets: string[];
  supportedTimeframes: string[];
};

export type ConversationMessage = {
  messageId: string;
  role: "user" | "assistant" | "system";
  messageType: string;
  content: string;
  createdAt: string;
  analysisId: string | null;
  metadata: Record<string, unknown>;
};

export type ConversationSummary = {
  caseId: string;
  contract: string | null;
  instrument: string | null;
  strategyName: string;
  action: string | null;
  createdAt: string;
};

export type ConversationView = {
  caseId: string;
  currentAnalysisId: string | null;
  strategy: {
    strategyId: string;
    version: string;
    displayName: string;
  };
  messages: ConversationMessage[];
};

export type CaseView = {
  action: string;
  reason: string;
  marketState: string;
  strategy: string;
  progress: string;
  blockers: string[];
  hasBlockingSteps: boolean;
  nextMilestone: string;
  cutoff: string;
  barCloseStatus: string;
  change: {
    summary: string;
    previousAction: string | null;
    currentAction: string;
    changedSteps: number[];
  };
  evidence: EvidenceImage[];
  positionBranches: PositionBranch[];
  milestones: Milestone[];
  clarification: ClarificationView;
  strategyManifest: StrategyManifest;
};

export type CaseViewResult =
  | { status: "ready"; data: CaseView }
  | { status: "not-found" | "no-analysis" | "error"; message: string };

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

export const demoCase: CaseView = {
  action: "等待补齐数据",
  reason: "演示案例，仅用于显式 /cases/demo 路由。",
  marketState: "U",
  strategy: "暂未启用",
  progress: "第 1 / 8 步",
  blockers: ["真实合约待确认"],
  hasBlockingSteps: true,
  nextMilestone: "补齐阻断数据",
  cutoff: "截止时间未知",
  barCloseStatus: "收盘状态未知",
  change: {
    summary: "演示案例。",
    previousAction: null,
    currentAction: "WAIT_FOR_DATA",
    changedSteps: []
  },
  evidence: [{
    role: "STATE_DAILY",
    provider: "codex",
    model: "gpt-5.6-sol",
    sha256: "demo",
    imageUrl: null,
    allowedUsage: "BLOCKED",
    promptVersion: "chart-evidence-v2",
    observations: [],
    fieldProvenance: {}
  }],
  positionBranches: [
    { scope: "FLAT", action: "WAIT_FOR_DATA", label: "空仓分支", guidance: "不建立新仓。" },
    { scope: "LONG", action: "WAIT_FOR_DATA", label: "多仓分支", guidance: "先核对持仓。" },
    { scope: "SHORT", action: "WAIT_FOR_DATA", label: "空头持仓分支", guidance: "先核对持仓。" }
  ],
  clarification: {
    sourceAnalysisId: null,
    questions: [],
    history: []
  },
  strategyManifest: {
    strategyId: "structure_confirmation",
    displayName: "结构确认策略",
    version: "1.0.0",
    status: "stable",
    processLabel: "八步结构确认",
    supportedMarkets: ["CN_FUTURES"],
    supportedTimeframes: ["1d", "60m"]
  },
  milestones: Array.from({ length: 8 }, (_, index) => ({
    number: index + 1,
    title: `演示里程碑 ${index + 1}`,
    status: index === 1 ? "CONFIRMED" : "BLOCKED",
    result: "演示状态",
    rules: [index === 0 ? "DQ-001" : `RULE-${index + 1}`],
    inputs: [{ label: "输入", value: "演示输入" }],
    details: [],
    comparisons: [],
    blockers: index === 1 ? [] : ["演示阻断"],
    nextConditions: ["等待真实分析"],
    evidenceRefs: [],
    evidence: [],
    change: {
      changed: false,
      previous: null,
      current: {
        status: index === 1 ? "CONFIRMED" : "BLOCKED",
        result: "演示状态"
      }
    }
  }))
};

type ApiMilestone = {
  number: number;
  code: string;
  title?: string | null;
  status: Milestone["status"];
  result: string;
  rule_ids: string[];
  blockers: string[];
  next_conditions: string[];
  evidence_refs: string[];
  actual_inputs?: unknown;
  structured_comparisons?: unknown;
  details?: Record<string, unknown>;
};

type ApiEvidence = {
  image_role: string;
  cutoff_time: string | null;
  last_bar_closed: boolean | null;
  provider: string;
  model: string;
  prompt_version: string;
  image_sha256: string;
  source_image_id: string | null;
  allowed_usage: string;
  observations?: {
    evidence_id: string;
    kind: string;
    value: unknown;
    confidence: number;
    provenance: string;
    visible_text: string | null;
    evidence_description: string | null;
  }[];
  field_provenance?: Record<string, string>;
};

type ApiAnalysis = {
  analysis_id: string;
  milestones: ApiMilestone[];
  decision: {
    action: string;
    market_state: string;
    strategy: string | null;
    blocking_steps: number[];
    next_milestone: string | null;
    reason_codes: string[];
  };
  rendered: {
    summary: string;
    position_branches: PositionBranch[];
  };
  evidence: ApiEvidence;
  evidence_set?: ApiEvidence[];
  change_report?: {
    summary: string;
    previous_action: string | null;
    current_action: string;
    changed_steps: number[];
  };
  strategy_manifest?: {
    strategy_id: string;
    display_name: string;
    version: string;
    status?: "stable" | "test" | "disabled";
    process_label?: string;
    supported_markets?: string[];
    supported_timeframes?: string[];
  };
};

type ApiClarificationFact = {
  question_id: string;
  field: string;
  value: boolean | number | string;
  explanation: string;
  resolves_blockers: string[];
};

type ApiClarificationHistoryItem = {
  clarification_id: string;
  source_analysis_id: string;
  user_message: string;
  facts: ApiClarificationFact[];
  unresolved_question_ids: string[];
  interpretation: string;
  provider: string;
  model: string;
  status: "PENDING_CONFIRMATION" | "CONFIRMED";
  confirmed_at?: string | null;
  result_analysis_id?: string | null;
};

type ApiClarificationResponse = {
  source_analysis_id: string | null;
  questions: {
    question_id: string;
    field: string;
    milestone_number: number;
    uncertainty: string;
    question: string;
    answer_examples: string[];
    blocking_issues: string[];
  }[];
  history: ApiClarificationHistoryItem[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatValue(label: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (
      value >= 0
      && value <= 1
      && /(confidence|score|ratio|置信度|评分|比例)/i.test(label)
    ) {
      return `${Math.round(value * 100)}%`;
    }
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(label, item)).join("；") || "—";
  }
  if (isRecord(value)) {
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${formatValue(key, item)}`)
      .join("；") || "—";
  }
  return String(value);
}

function toAuditFields(value: unknown): AuditField[] {
  if (Array.isArray(value)) {
    return value.map((item, index) => ({
      label: isRecord(item) && typeof item.label === "string"
        ? item.label
        : `input_${index + 1}`,
      value: isRecord(item) && "value" in item
        ? formatValue(String(item.label ?? index + 1), item.value)
        : formatValue(String(index + 1), item)
    }));
  }
  if (isRecord(value)) {
    return Object.entries(value).map(([label, item]) => ({
      label,
      value: formatValue(label, item)
    }));
  }
  return value === undefined || value === null
    ? []
    : [{ label: "value", value: formatValue("value", value) }];
}

function toComparisons(value: unknown): StructuredComparison[] {
  const items = Array.isArray(value) ? value : value === undefined ? [] : [value];
  return items.map((item, index) => {
    if (!isRecord(item)) {
      return {
        label: `comparison_${index + 1}`,
        actual: formatValue("actual", item),
        expected: "—",
        result: "—",
        source: null
      };
    }
    const label = item.label ?? item.name ?? item.field ?? `comparison_${index + 1}`;
    const actual = item.actual ?? item.current ?? item.value;
    const expected = item.expected ?? item.threshold ?? item.reference;
    const result = item.result ?? item.status ?? item.outcome;
    const source = item.source ?? item.provenance;
    return {
      label: String(label),
      actual: formatValue("actual", actual),
      expected: formatValue("expected", expected),
      result: formatValue("result", result),
      source: source === null || source === undefined ? null : String(source)
    };
  });
}

function imageUrl(caseId: string, sourceImageId: string | null): string | null {
  return sourceImageId
    ? `/api/cases/${encodeURIComponent(caseId)}/images/${encodeURIComponent(sourceImageId)}`
    : null;
}

function mapEvidenceImage(
  evidence: ApiEvidence,
  caseId: string
): EvidenceImage {
  return {
    role: evidence.image_role,
    provider: evidence.provider,
    model: evidence.model,
    sha256: evidence.image_sha256,
    imageUrl: imageUrl(caseId, evidence.source_image_id),
    allowedUsage: evidence.allowed_usage,
    promptVersion: evidence.prompt_version,
    observations: (evidence.observations ?? []).map((item) => ({
      id: item.evidence_id,
      kind: item.kind,
      value: formatValue(item.kind, item.value),
      confidence: item.confidence,
      provenance: item.provenance,
      visibleText: item.visible_text,
      description: item.evidence_description
    })),
    fieldProvenance: evidence.field_provenance ?? {}
  };
}

function resolveMilestoneEvidence(
  refs: string[],
  evidenceImages: EvidenceImage[]
): MilestoneEvidence[] {
  const resolved: MilestoneEvidence[] = [];
  for (const reference of refs) {
    const matches: MilestoneEvidence[] = evidenceImages.flatMap((image) => (
      image.observations
        .filter((observation) => observation.id === reference)
        .map((observation) => ({
          ...observation,
          reference,
          imageUrl: observation.provenance === "user_confirmed"
            ? null
            : image.imageUrl,
          imageRole: image.role,
          provider: image.provider,
          model: image.model
        }))
    ));
    if (matches.length > 0) {
      resolved.push(...matches);
      continue;
    }
    resolved.push({
      id: reference,
      reference,
      kind: "UNRESOLVED_REFERENCE",
      value: "未在当前证据集中解析到该引用",
      confidence: null,
      provenance: null,
      visibleText: null,
      description: null,
      imageUrl: null,
      imageRole: null,
      provider: null,
      model: null
    });
  }
  return resolved;
}

export async function getCaseView(caseId: string): Promise<CaseViewResult> {
  if (caseId === "demo") return { status: "ready", data: demoCase };
  if (!SAFE_ID.test(caseId)) {
    return { status: "error", message: "案例标识无效。" };
  }
  const baseUrl = process.env.TRADING_API_URL;
  if (!baseUrl) {
    return { status: "error", message: "TRADING_API_URL 未配置，无法读取真实案例。" };
  }
  const apiToken = process.env.TRADING_AGENT_API_TOKEN;
  if (!apiToken) {
    return {
      status: "error",
      message: "TRADING_AGENT_API_TOKEN 未配置，无法访问分析服务。"
    };
  }
  try {
    const response = await fetch(`${baseUrl}/v1/cases/${caseId}/analyses`, {
      headers: {
        Authorization: `Bearer ${apiToken}`
      },
      cache: "no-store"
    });
    if (response.status === 404) {
      return { status: "not-found", message: "案例不存在。" };
    }
    if (!response.ok) {
      return { status: "error", message: `分析服务返回 ${response.status}。` };
    }
    const analyses = await response.json() as ApiAnalysis[];
    const latest = analyses.at(-1);
    if (!latest) {
      return { status: "no-analysis", message: "案例尚无分析结果。" };
    }
    const change = latest.change_report ?? {
      summary: "首次分析完成。",
      previous_action: null,
      current_action: latest.decision.action,
      changed_steps: []
    };
    const evidenceSet = latest.evidence_set?.length
      ? latest.evidence_set
      : [latest.evidence];
    const evidenceImages = evidenceSet.map((item) => (
      mapEvidenceImage(item, caseId)
    ));
    const previousMilestones = new Map(
      (analyses.at(-2)?.milestones ?? []).map((item) => [item.number, item])
    );
    let clarification: ClarificationView = {
      sourceAnalysisId: latest.analysis_id,
      questions: [],
      history: []
    };
    try {
      const clarificationResponse = await fetch(
        `${baseUrl}/v1/cases/${caseId}/clarifications`,
        {
          headers: {
            Authorization: `Bearer ${apiToken}`
          },
          cache: "no-store"
        }
      );
      if (clarificationResponse.ok) {
        const payload = await clarificationResponse.json() as ApiClarificationResponse;
        clarification = {
          sourceAnalysisId: payload.source_analysis_id,
          questions: payload.questions.map((item) => ({
            questionId: item.question_id,
            field: item.field,
            milestoneNumber: item.milestone_number,
            uncertainty: item.uncertainty,
            question: item.question,
            answerExamples: item.answer_examples,
            blockingIssues: item.blocking_issues
          })),
          history: payload.history.map((item) => ({
            clarificationId: item.clarification_id,
            sourceAnalysisId: item.source_analysis_id,
            userMessage: item.user_message,
            facts: item.facts.map((fact) => ({
              questionId: fact.question_id,
              field: fact.field,
              value: fact.value,
              explanation: fact.explanation,
              resolvesBlockers: fact.resolves_blockers
            })),
            unresolvedQuestionIds: item.unresolved_question_ids,
            interpretation: item.interpretation,
            provider: item.provider,
            model: item.model,
            status: item.status,
            confirmedAt: item.confirmed_at ?? null,
            resultAnalysisId: item.result_analysis_id ?? null
          }))
        };
      }
    } catch {
      // Analysis remains usable when the optional clarification endpoint is unavailable.
    }
    const action = latest.decision.action === "WAIT_FOR_DATA"
      ? clarification.questions.length > 0
        ? "等待你确认少量信息"
        : "系统需要重新核验数据"
      : latest.rendered.summary;
    return {
      status: "ready",
      data: {
        action,
        reason: latest.decision.reason_codes.join("；") || "当前规则已完成评估。",
        marketState: latest.decision.market_state,
        strategy: (
          latest.strategy_manifest?.display_name
          ?? "结构确认策略"
        ),
        progress: (
          `${latest.milestones.filter((item) => item.status !== "BLOCKED").length}`
          + ` / ${latest.milestones.length} 个里程碑`
        ),
        blockers: latest.milestones.flatMap((item) => item.blockers).slice(0, 5),
        hasBlockingSteps: latest.decision.blocking_steps.length > 0,
        nextMilestone: latest.decision.next_milestone ?? "等待下一次分析",
        cutoff: latest.evidence.cutoff_time ?? "截止时间未知",
        barCloseStatus: latest.evidence.last_bar_closed === true
          ? "K线已收盘"
          : latest.evidence.last_bar_closed === false
            ? "K线未收盘"
            : "收盘状态未知",
        change: {
          summary: change.summary,
          previousAction: change.previous_action,
          currentAction: change.current_action,
          changedSteps: change.changed_steps
        },
        evidence: evidenceImages,
        positionBranches: latest.rendered.position_branches,
        clarification,
        strategyManifest: {
          strategyId: (
            latest.strategy_manifest?.strategy_id
            ?? "structure_confirmation"
          ),
          displayName: (
            latest.strategy_manifest?.display_name
            ?? "结构确认策略"
          ),
          version: latest.strategy_manifest?.version ?? "1.0.0",
          status: latest.strategy_manifest?.status ?? "stable",
          processLabel: (
            latest.strategy_manifest?.process_label
            ?? "策略里程碑"
          ),
          supportedMarkets: (
            latest.strategy_manifest?.supported_markets
            ?? ["CN_FUTURES"]
          ),
          supportedTimeframes: (
            latest.strategy_manifest?.supported_timeframes
            ?? []
          )
        },
        milestones: latest.milestones.map((item) => {
          const rawDetails = item.details ?? {};
          const {
            actual_inputs: nestedInputs,
            inputs: legacyInputs,
            structured_comparisons: nestedComparisons,
            comparisons: legacyComparisons,
            ...remainingDetails
          } = rawDetails;
          const previous = previousMilestones.get(item.number);
          return {
            number: item.number,
            title: item.title ?? item.code,
            status: item.status,
            result: item.result,
            rules: item.rule_ids,
            inputs: toAuditFields(item.actual_inputs ?? nestedInputs ?? legacyInputs),
            details: toAuditFields(remainingDetails),
            comparisons: toComparisons(
              item.structured_comparisons
              ?? nestedComparisons
              ?? legacyComparisons
            ),
            blockers: item.blockers,
            nextConditions: item.next_conditions,
            evidenceRefs: item.evidence_refs,
            evidence: resolveMilestoneEvidence(item.evidence_refs, evidenceImages),
            change: {
              changed: change.changed_steps.includes(item.number),
              previous: previous ? {
                status: previous.status,
                result: previous.result
              } : null,
              current: {
                status: item.status,
                result: item.result
              }
            }
          };
        })
      }
    };
  } catch {
    return { status: "error", message: "无法连接分析服务。" };
  }
}

type ApiStrategyManifest = {
  strategy_id: string;
  display_name: string;
  version: string;
  status: "stable" | "test" | "disabled";
  process_label: string;
  supported_markets: string[];
  supported_timeframes: string[];
};

function mapStrategy(item: ApiStrategyManifest): StrategyManifest {
  return {
    strategyId: item.strategy_id,
    displayName: item.display_name,
    version: item.version,
    status: item.status,
    processLabel: item.process_label,
    supportedMarkets: item.supported_markets,
    supportedTimeframes: item.supported_timeframes
  };
}

function serverConfiguration(): { baseUrl: string; apiToken: string } | null {
  const baseUrl = process.env.TRADING_API_URL;
  const apiToken = process.env.TRADING_AGENT_API_TOKEN;
  return baseUrl && apiToken ? { baseUrl, apiToken } : null;
}

export async function getStrategies(): Promise<StrategyManifest[]> {
  const configuration = serverConfiguration();
  if (!configuration) return [];
  try {
    const response = await fetch(`${configuration.baseUrl}/v1/strategies`, {
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`
      },
      cache: "no-store"
    });
    if (!response.ok) return [];
    return (await response.json() as ApiStrategyManifest[]).map(mapStrategy);
  } catch {
    return [];
  }
}

export async function getRecentConversations(): Promise<ConversationSummary[]> {
  const configuration = serverConfiguration();
  if (!configuration) return [];
  try {
    const response = await fetch(`${configuration.baseUrl}/v1/cases`, {
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`
      },
      cache: "no-store"
    });
    if (!response.ok) return [];
    const cases = await response.json() as {
      case_id: string;
      contract: string | null;
      instrument: string | null;
      strategy?: { display_name?: string };
      current_decision?: { action?: string } | null;
      created_at: string;
    }[];
    return cases.map((item) => ({
      caseId: item.case_id,
      contract: item.contract,
      instrument: item.instrument,
      strategyName: item.strategy?.display_name ?? "结构确认策略",
      action: item.current_decision?.action ?? null,
      createdAt: item.created_at
    }));
  } catch {
    return [];
  }
}

export async function getConversation(
  caseId: string
): Promise<ConversationView | null> {
  if (!SAFE_ID.test(caseId)) return null;
  const configuration = serverConfiguration();
  if (!configuration) return null;
  try {
    const response = await fetch(
      `${configuration.baseUrl}/v1/cases/${caseId}/conversation`,
      {
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`
        },
        cache: "no-store"
      }
    );
    if (!response.ok) return null;
    const payload = await response.json() as {
      case_id: string;
      current_analysis_id: string | null;
      strategy: {
        strategy_id: string;
        version: string;
        display_name: string;
      };
      messages: {
        message_id: string;
        role: "user" | "assistant" | "system";
        message_type: string;
        content: string;
        created_at: string;
        analysis_id: string | null;
        metadata?: Record<string, unknown>;
      }[];
    };
    return {
      caseId: payload.case_id,
      currentAnalysisId: payload.current_analysis_id,
      strategy: {
        strategyId: payload.strategy.strategy_id,
        version: payload.strategy.version,
        displayName: payload.strategy.display_name
      },
      messages: payload.messages.map((message) => ({
        messageId: message.message_id,
        role: message.role,
        messageType: message.message_type,
        content: message.content,
        createdAt: message.created_at,
        analysisId: message.analysis_id,
        metadata: message.metadata ?? {}
      }))
    };
  } catch {
    return null;
  }
}
