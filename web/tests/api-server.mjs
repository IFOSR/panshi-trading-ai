import http from "node:http";
import { readFileSync } from "node:fs";

const wideDailyImage = readFileSync(
  new URL("../../tests/fixtures/charts/daily_boll_macd_volume.png", import.meta.url)
);

const milestoneCodes = [
  "DATA_VALIDITY",
  "MARKET_STATE",
  "STRATEGY_PERMISSION",
  "PRICE_LOCATION",
  "POSITION_BEHAVIOR",
  "MOMENTUM",
  "PRICE_CONFIRMATION",
  "RISK_AND_ACTION"
];

const previousMilestones = Array.from({ length: 8 }, (_, index) => ({
  number: index + 1,
  code: milestoneCodes[index],
  status: "BLOCKED",
  result: index === 0 ? "CONTRACT_MISSING" : "PENDING",
  rule_ids: [index === 0 ? "DQ-001" : `RULE-${index + 1}`],
  blockers: [`BLOCKER-${index + 1}`],
  next_conditions: [`NEXT-${index + 1}`],
  evidence_refs: [],
  details: {}
}));

const milestones = Array.from({ length: 8 }, (_, index) => ({
  number: index + 1,
  code: milestoneCodes[index],
  status: index === 1
    ? "CONFIRMED"
    : index === 6
      ? "CANDIDATE"
      : "BLOCKED",
  result: index === 1
    ? "U_BEARISH_BIAS"
    : index === 6
      ? "NOT_TRIGGERED"
      : "PENDING",
  rule_ids: [index === 0 ? "DQ-001" : `RULE-${index + 1}`],
  blockers: index === 1
    ? []
    : index === 6
      ? ["CONFIRMATION_DIRECTION_MISMATCH"]
      : [`BLOCKER-${index + 1}`],
  next_conditions: index === 6
    ? ["等待与策略同方向的执行周期价格确认"]
    : [`NEXT-${index + 1}`],
  evidence_refs: index === 0
    ? ["daily-contract"]
    : index === 6
      ? ["execution-breakout"]
      : [],
  actual_inputs: index === 0
    ? {
        contract: "rb2610",
        timeframe: "1d",
        last_bar_closed: true
      }
    : index === 6
      ? {
          timeframe: "60m",
          confirmation_pattern: "突破后回踩守住"
        }
      : {},
  structured_comparisons: index === 0
    ? [
        {
          label: "合约一致性",
          actual: "rb2610",
          expected: "rb2610",
          result: "MATCH",
          source: "structured_market_data"
        }
      ]
    : index === 6
      ? [
          {
            label: "执行周期确认",
            actual: "突破后回踩守住",
            expected: "已收盘 60m 确认",
            result: "MATCH",
            source: "execution-chart"
          }
        ]
      : [],
  details: index === 0
    ? {
        data_quality_score: 0.98,
        contract_resolution: "verified"
      }
    : index === 6
      ? {
          evidence_state: "KNOWN_TRUE",
          required_direction: "BEARISH",
          observed_direction: "BULLISH",
          confirmation_type: "PULLBACK",
          allowed_confirmation_types: ["PULLBACK", "HOLD"]
        }
    : index === 4
      ? {
          volume_state: "BELOW_BOTH_AVERAGES",
          visual_position_behavior: "POSITION_LIQUIDATION"
        }
      : {}
}));

const dailyEvidence = {
  image_role: "STATE_DAILY",
  cutoff_time: "2026-07-20",
  last_bar_closed: true,
  provider: "codex",
  model: "gpt-5.6-sol",
  prompt_version: "chart-evidence-v2",
  image_sha256: "daily-abc123",
  source_image_id: "image-daily",
  allowed_usage: "QUALITATIVE_ONLY",
  field_provenance: {
    contract: "structured_market_data",
    "strategy_facts.price_location": "structured_market_data"
  },
  observations: [
    {
      evidence_id: "daily-contract",
      kind: "CONTRACT",
      value: "rb2610",
      confidence: 0.99,
      provenance: "structured_market_data",
      visible_text: "螺纹钢2610",
      evidence_description: "日线图合约与案例合约一致。"
    },
    {
      evidence_id: "price-location",
      kind: "PRICE_LOCATION",
      value: "价格位于 BOLL 中轨下方",
      confidence: 0.94,
      provenance: "codex:gpt-5.6-sol",
      visible_text: "BOLL 16964.50",
      evidence_description: "日线价格面板可见价格处于中轨下方。"
    }
  ]
};

const executionEvidence = {
  image_role: "EXECUTION_60M",
  cutoff_time: "2026-07-20T14:00:00+08:00",
  last_bar_closed: true,
  provider: "kimi",
  model: "moonshot-v1",
  prompt_version: "chart-evidence-v2",
  image_sha256: "execution-def456",
  source_image_id: "image-execution",
  allowed_usage: "QUALITATIVE_ONLY",
  field_provenance: {
    "strategy_facts.price_confirmation": "vision_verified"
  },
  observations: [
    {
      evidence_id: "execution-breakout",
      kind: "PRICE_CONFIRMATION",
      value: "突破后回踩守住",
      confidence: 0.91,
      provenance: "kimi:moonshot-v1",
      visible_text: "60分钟",
      evidence_description: "执行图显示突破后回踩未跌回结构内。"
    }
  ]
};

const structureStrategy = {
  strategy_id: "structure_confirmation",
  display_name: "结构确认策略",
  version: "1.0.0",
  status: "stable",
  entrypoint: "fixture:StructureConfirmation",
  input_schema_version: "strategy-input-v1",
  output_schema_version: "strategy-result-v1",
  supported_markets: ["CN_FUTURES"],
  supported_timeframes: ["1d", "60m"],
  process_label: "八步结构确认",
  risk_profile_id: "china-futures-risk-v1"
};

const momentumStrategy = {
  ...structureStrategy,
  strategy_id: "momentum_breakout",
  display_name: "动量突破策略",
  version: "0.3.0",
  status: "test",
  entrypoint: "fixture:MomentumBreakout",
  process_label: "动量突破确认"
};
let strategyCatalogMode = "single";
let deletedCaseIds = new Set();
let historyCleared = false;
let deleteFailure = false;
let extraHistoryCount = 0;
const authSessions = new Set();
let authSessionSequence = 0;

const previousAnalysis = {
  analysis_id: "analysis-previous",
  created_at: "2026-07-28T08:00:00Z",
  strategy_manifest: structureStrategy,
  milestones: previousMilestones,
  decision: {
    action: "WAIT_FOR_DATA",
    market_state: "U",
    position_scope: "UNKNOWN",
    strategy: null,
    blocking_steps: [1, 2, 3, 4, 5, 6, 7, 8],
    next_milestone: "确认真实合约",
    reason_codes: ["CONTRACT_MISSING"]
  },
  rendered: {
    action: "WAIT_FOR_DATA",
    summary: "等待补齐数据",
    position_branches: []
  },
  evidence: dailyEvidence,
  evidence_set: [dailyEvidence]
};

const analysis = {
  analysis_id: "analysis-live",
  created_at: "2026-07-28T09:00:00Z",
  strategy_manifest: structureStrategy,
  milestones,
  decision: {
    action: "WAIT_FOR_DATA",
    market_state: "U",
    position_scope: "UNKNOWN",
    strategy: null,
    blocking_steps: [1, 3, 4, 5, 6, 7, 8],
    next_milestone: "补齐阻断数据",
    reason_codes: ["CONTRACT_MISSING"]
  },
  rendered: {
    action: "WAIT_FOR_DATA",
    summary: "等待补齐数据",
    position_branches: [
      { scope: "FLAT", action: "WAIT_FOR_DATA", label: "空仓分支", guidance: "不建立新仓。" },
      { scope: "LONG", action: "WAIT_FOR_DATA", label: "多仓分支", guidance: "先核对持仓与止损。" },
      { scope: "SHORT", action: "WAIT_FOR_DATA", label: "空头持仓分支", guidance: "先核对持仓与止损。" }
    ]
  },
  evidence: dailyEvidence,
  evidence_set: [dailyEvidence, executionEvidence],
  change_report: {
    summary: "新增日线与 60 分钟证据，动作保持等待补齐数据。",
    previous_action: "WAIT_FOR_DATA",
    current_action: "WAIT_FOR_DATA",
    changed_steps: [1, 2, 7]
  }
};

const observingAnalysis = {
  ...analysis,
  analysis_id: "analysis-observing",
  milestones: milestones.map((item) => ({
    ...item,
    status: item.status === "BLOCKED" ? "CANDIDATE" : item.status,
    blockers: item.number === 3 ? ["NO_ENABLED_STRATEGY"] : []
  })),
  decision: {
    ...analysis.decision,
    action: "HOLD",
    blocking_steps: [],
    next_milestone: "等待下一次策略状态更新",
    reason_codes: ["NO_ENABLED_STRATEGY"]
  },
  rendered: {
    ...analysis.rendered,
    action: "HOLD",
    summary: "继续持有并监控失效条件"
  },
  change_report: {
    summary: "当前数据完整，但策略条件尚未触发。",
    previous_action: "HOLD",
    current_action: "HOLD",
    changed_steps: []
  }
};

const clarificationQuestions = [
  {
    question_id: "clarify-state-bar-closed",
    field: "state_bar_closed",
    milestone_number: 1,
    uncertainty: "日线最后一根 K 线的收盘状态无法从截图可靠确认。",
    question: "请确认：日线最后一根 K 线是否已经收盘？",
    answer_examples: ["日线已收盘", "日线尚未收盘"],
    blocking_issues: ["UNCLOSED_STATE_BAR"]
  },
  {
    question_id: "clarify-execution-bar-closed",
    field: "execution_bar_closed",
    milestone_number: 1,
    uncertainty: "执行周期最后一根 K 线的收盘状态无法从截图可靠确认。",
    question: "请确认：60 分钟最后一根 K 线是否已经收盘？",
    answer_examples: ["60 分钟 K 线已收盘", "60 分钟 K 线尚未收盘"],
    blocking_issues: ["EXECUTION_CUTOFF_TIME_MISSING"]
  },
  {
    question_id: "clarify-position-behavior",
    field: "position_behavior_state",
    milestone_number: 1,
    uncertainty: "CCYD 或持仓行为标签无法可靠读取。",
    question: "请说明 CCYD 当前显示的持仓行为和可见数值。",
    answer_examples: ["多头减仓 4425", "空头增仓 3200"],
    blocking_issues: ["CCYD_UNCLEAR"]
  },
  {
    question_id: "clarify-open-interest-change",
    field: "open_interest_change",
    milestone_number: 5,
    uncertainty: "策略缺少可验证的持仓量变化。",
    question: "请提供当前可见的持仓量变化数值，增加为正数，减少为负数。",
    answer_examples: ["持仓量增加 1200", "持仓量减少 4425"],
    blocking_issues: ["OPEN_INTEREST_MISSING"]
  },
  {
    question_id: "clarify-price-confirmation",
    field: "price_confirmation",
    milestone_number: 7,
    uncertainty: "执行周期尚未形成可验证的价格确认。",
    question: "请确认已收盘执行周期是否出现突破、守住、回踩或结构失效，并说明方向。",
    answer_examples: ["向下突破后回踩未站回", "向上突破并守住", "尚未确认"],
    blocking_issues: ["PRICE_NOT_CONFIRMED"]
  }
];

const clarificationStates = new Map();

function clarificationState(caseId) {
  if (!clarificationStates.has(caseId)) {
    const state = {
      sequence: 0,
      proposals: [],
      confirmed: false,
      autoResolved: false,
      result: null
    };
    clarificationStates.set(caseId, state);
    if (caseId === "case-clarification-pending") {
      const proposal = clarificationProposal(
        caseId,
        "日线和 60 分钟都已收盘。"
      );
      proposal.interpretation = "日线和 60 分钟均已收盘";
    }
  }
  return clarificationStates.get(caseId);
}

function clarificationProposal(caseId, message) {
  const state = clarificationState(caseId);
  state.sequence += 1;
  const clarificationId = `clarification-${caseId}-${state.sequence}`;
  const corrected = message.includes("修正");
  const proposal = {
    clarification_id: clarificationId,
    source_analysis_id: "analysis-live",
    user_message: message,
    facts: [
      {
        question_id: "clarify-state-bar-closed",
        field: "state_bar_closed",
        value: true,
        explanation: "用户确认日线已经收盘。",
        resolves_blockers: ["UNCLOSED_STATE_BAR"]
      },
      {
        question_id: "clarify-execution-bar-closed",
        field: "execution_bar_closed",
        value: true,
        explanation: "用户确认 60 分钟 K 线已经收盘。",
        resolves_blockers: ["EXECUTION_CUTOFF_TIME_MISSING"]
      },
      {
        question_id: "clarify-position-behavior",
        field: "position_behavior_state",
        value: "POSITION_LIQUIDATION",
        explanation: "用户说明 CCYD 显示减仓。",
        resolves_blockers: ["CCYD_UNCLEAR"]
      },
      {
        question_id: "clarify-open-interest-change",
        field: "open_interest_change",
        value: -4425,
        explanation: "用户说明持仓量减少 4425。",
        resolves_blockers: ["OPEN_INTEREST_MISSING"]
      },
      {
        question_id: "clarify-price-confirmation",
        field: "price_confirmation",
        value: true,
        explanation: "用户确认已形成价格确认。",
        resolves_blockers: ["PRICE_NOT_CONFIRMED"]
      },
      {
        question_id: "clarify-price-confirmation",
        field: "price_confirmation_direction",
        value: "BEARISH",
        explanation: "用户确认方向向下。",
        resolves_blockers: ["PRICE_NOT_CONFIRMED"]
      },
      {
        question_id: "clarify-price-confirmation",
        field: "price_confirmation_type",
        value: "PULLBACK",
        explanation: "用户确认形态为回踩。",
        resolves_blockers: ["PRICE_NOT_CONFIRMED"]
      }
    ],
    unresolved_question_ids: [],
    interpretation: corrected
      ? "修正后，我理解为：日线和 60 分钟均已收盘，持仓量减少 4425，形成向下回踩确认。"
      : "我理解为：日线和 60 分钟均已收盘，持仓量减少 4425，形成向下回踩确认。",
    provider: "codex",
    model: "gpt-5.6-sol",
    status: "PENDING_CONFIRMATION"
  };
  state.proposals.push(proposal);
  return proposal;
}

function clarifiedAnalysis(caseId, clarificationId) {
  const openInterestEvidenceId = `user-confirmed-${clarificationId}-open_interest_change`;
  const positionEvidenceId = `user-confirmed-${clarificationId}-position_behavior_state`;
  const priceEvidenceId = `user-confirmed-${clarificationId}-price_confirmation`;
  const userObservations = [
    {
      evidence_id: openInterestEvidenceId,
      kind: "open_interest_change",
      value: -4425,
      confidence: 1,
      provenance: "user_confirmed",
      visible_text: null,
      evidence_description: `用户确认持仓量减少 4425。来源澄清记录 ${clarificationId}。`
    },
    {
      evidence_id: positionEvidenceId,
      kind: "position_behavior_state",
      value: "POSITION_LIQUIDATION",
      confidence: 1,
      provenance: "user_confirmed",
      visible_text: null,
      evidence_description: `用户确认 CCYD 显示减仓。来源澄清记录 ${clarificationId}。`
    }
  ];
  const executionUserObservations = [
    {
      evidence_id: priceEvidenceId,
      kind: "price_confirmation",
      value: true,
      confidence: 1,
      provenance: "user_confirmed",
      visible_text: null,
      evidence_description: `用户确认形成向下回踩。来源澄清记录 ${clarificationId}。`
    }
  ];
  const clarifiedDaily = {
    ...dailyEvidence,
    observations: [...dailyEvidence.observations, ...userObservations],
    field_provenance: {
      ...dailyEvidence.field_provenance,
      open_interest_change: "user_confirmed",
      "strategy_facts.position_behavior": "user_confirmed"
    }
  };
  const clarifiedExecution = {
    ...executionEvidence,
    observations: [
      ...executionEvidence.observations,
      ...executionUserObservations
    ],
    field_provenance: {
      ...executionEvidence.field_provenance,
      "strategy_facts.price_confirmation": "user_confirmed"
    }
  };
  const clarifiedMilestones = milestones.map((item) => {
    if (item.number === 5) {
      return {
        ...item,
        status: "CONFIRMED",
        result: "TOTAL_OPEN_INTEREST_DECREASED",
        blockers: [],
        evidence_refs: [openInterestEvidenceId, positionEvidenceId]
      };
    }
    if (item.number === 7) {
      return {
        ...item,
        status: "CONFIRMED",
        result: "BEARISH_PULLBACK",
        blockers: [],
        evidence_refs: [priceEvidenceId]
      };
    }
    if (item.number === 8) {
      return {
        ...item,
        status: "BLOCKED",
        result: "WAIT_FOR_SETUP",
        blockers: ["SETUP_NOT_COMPLETE"]
      };
    }
    return item;
  });
  return {
    ...analysis,
    analysis_id: `analysis-confirmed-${caseId}`,
    milestones: clarifiedMilestones,
    decision: {
      ...analysis.decision,
      action: "WAIT_FOR_SETUP",
      next_milestone: "等待完整策略条件",
      reason_codes: ["SETUP_NOT_COMPLETE"]
    },
    rendered: {
      ...analysis.rendered,
      summary: "等待策略条件"
    },
    evidence: clarifiedDaily,
    evidence_set: [clarifiedDaily, clarifiedExecution],
    clarification_ids: [clarificationId],
    clarification_evidence_ids: [
      openInterestEvidenceId,
      positionEvidenceId,
      priceEvidenceId
    ],
    change_report: {
      summary: "用户确认事实进入证据链，第 5、7、8 步已重新评估。",
      previous_action: "WAIT_FOR_DATA",
      current_action: "WAIT_FOR_SETUP",
      changed_steps: [5, 7, 8]
    }
  };
}

let createdCaseSequence = 0;
const createdCases = new Map();
const caseCreations = new Map();
const liveConversation = {
  strategy: {
    strategy_id: structureStrategy.strategy_id,
    version: structureStrategy.version,
    display_name: structureStrategy.display_name
  },
  messages: [
    {
      message_id: "message-user-1",
      role: "user",
      message_type: "USER_MESSAGE",
      content: "请分析这张 cf2609 图表，告诉我当前应该如何操作。",
      created_at: "2026-07-28T08:59:00Z",
      analysis_id: null,
      metadata: {}
    },
    {
      message_id: "message-system-1",
      role: "system",
      message_type: "STRATEGY_CHANGE",
      content: "使用结构确认策略 v1.0.0",
      created_at: "2026-07-28T08:59:10Z",
      analysis_id: null,
      metadata: {}
    },
    {
      message_id: "analysis:analysis-previous",
      role: "assistant",
      message_type: "STRATEGY_CONCLUSION",
      content: "等待补齐数据",
      created_at: "2026-07-28T08:59:20Z",
      analysis_id: "analysis-previous",
      metadata: {
        action: "WAIT_FOR_DATA",
        strategy_id: structureStrategy.strategy_id,
        strategy_version: structureStrategy.version
      }
    },
    {
      message_id: "analysis:analysis-live",
      role: "assistant",
      message_type: "STRATEGY_CONCLUSION",
      content: "等待补齐数据",
      created_at: "2026-07-28T09:00:00Z",
      analysis_id: "analysis-live",
      metadata: {
        action: "WAIT_FOR_DATA",
        strategy_id: structureStrategy.strategy_id,
        strategy_version: structureStrategy.version
      }
    }
  ]
};
const liveAnalyses = [previousAnalysis, analysis];
let liveAnalysisSequence = 0;

function appendLiveAnalysis(strategy = null) {
  liveAnalysisSequence += 1;
  const selected = strategy ?? liveConversation.strategy;
  const next = {
    ...analysis,
    analysis_id: `analysis-live-v${liveAnalysisSequence}`,
    created_at: `2026-07-28T09:${String(10 + liveAnalysisSequence).padStart(2, "0")}:00Z`,
    strategy_manifest: selected.strategy_id === momentumStrategy.strategy_id
      ? momentumStrategy
      : structureStrategy,
    change_report: {
      summary: "根据新增证据或最新公开行情创建了新的分析版本。",
      previous_action: liveAnalyses.at(-1).decision.action,
      current_action: analysis.decision.action,
      changed_steps: [1, 5, 7]
    }
  };
  liveAnalyses.push(next);
  liveConversation.messages.push({
    message_id: `analysis:${next.analysis_id}`,
    role: "assistant",
    message_type: "STRATEGY_CONCLUSION",
    content: next.rendered.summary,
    created_at: next.created_at,
    analysis_id: next.analysis_id,
    metadata: {
      action: next.decision.action,
      strategy_id: next.strategy_manifest.strategy_id,
      strategy_version: next.strategy_manifest.version
    }
  });
  return next;
}

function sendJson(response, payload, statusCode = 200) {
  response.setHeader("Content-Type", "application/json");
  response.statusCode = statusCode;
  response.end(JSON.stringify(payload));
}

async function consume(request) {
  const chunks = [];
  for await (const _chunk of request) {
    chunks.push(_chunk);
  }
  return Buffer.concat(chunks);
}

http.createServer(async (request, response) => {
  if (
    request.method === "POST"
    && request.url === "/__test/strategy-catalog"
  ) {
    const payload = JSON.parse((await consume(request)).toString("utf8"));
    strategyCatalogMode = payload.mode === "multi" ? "multi" : "single";
    sendJson(response, { mode: strategyCatalogMode });
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/__test/reset-history"
  ) {
    deletedCaseIds = new Set();
    historyCleared = false;
    deleteFailure = false;
    extraHistoryCount = 0;
    createdCases.clear();
    sendJson(response, { reset: true });
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/__test/history-size"
  ) {
    const payload = JSON.parse((await consume(request)).toString("utf8"));
    extraHistoryCount = Math.max(0, Number(payload.extra ?? 0));
    sendJson(response, { extra: extraHistoryCount });
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/__test/delete-failure"
  ) {
    const payload = JSON.parse((await consume(request)).toString("utf8"));
    deleteFailure = payload.enabled === true;
    sendJson(response, { enabled: deleteFailure });
    return;
  }
  if (
    request.url?.startsWith("/v1/")
    && request.headers.authorization !== "Bearer test-api-token"
  ) {
    sendJson(response, { detail: "unauthorized" }, 401);
    return;
  }
  if (request.method === "POST" && request.url === "/v1/auth/login") {
    const payload = JSON.parse((await consume(request)).toString("utf8"));
    if (
      payload.username !== "ylfego"
      || payload.password !== "test-password"
    ) {
      sendJson(response, { detail: "invalid username or password" }, 401);
      return;
    }
    authSessionSequence += 1;
    const token = `test-session-${authSessionSequence}`;
    authSessions.add(token);
    sendJson(response, {
      username: "ylfego",
      session_token: token,
      expires_at: "2026-07-30T00:00:00Z"
    });
    return;
  }
  if (request.method === "GET" && request.url === "/v1/auth/session") {
    const token = request.headers["x-panshi-session"];
    if (typeof token !== "string" || !authSessions.has(token)) {
      sendJson(response, { detail: "invalid session" }, 401);
      return;
    }
    sendJson(response, {
      username: "ylfego",
      expires_at: "2026-07-30T00:00:00Z"
    });
    return;
  }
  if (request.method === "POST" && request.url === "/v1/auth/logout") {
    const token = request.headers["x-panshi-session"];
    if (typeof token === "string") authSessions.delete(token);
    sendJson(response, { ok: true });
    return;
  }
  if (request.method === "GET" && request.url === "/v1/strategies") {
    sendJson(
      response,
      strategyCatalogMode === "multi"
        ? [structureStrategy, momentumStrategy]
        : [structureStrategy]
    );
    return;
  }
  if (request.method === "GET" && request.url === "/v1/cases") {
    const cases = [
      ...[...createdCases.entries()].reverse().map(([caseId, state]) => ({
        case_id: caseId,
        contract: null,
        instrument: null,
        strategy: state.strategy,
        current_decision: state.analyzed ? analysis.decision : null,
        lifecycle: "OBSERVING",
        created_at: "2026-07-28T10:00:00Z"
      })),
      {
        case_id: "case-delete-a",
        contract: "au2612",
        instrument: "AU",
        strategy: structureStrategy,
        current_decision: analysis.decision,
        lifecycle: "OBSERVING",
        created_at: "2026-07-28T09:30:00Z"
      },
      {
        case_id: "case-delete-b",
        contract: "ag2612",
        instrument: "AG",
        strategy: structureStrategy,
        current_decision: analysis.decision,
        lifecycle: "OBSERVING",
        created_at: "2026-07-28T09:15:00Z"
      },
      {
        case_id: "case-live",
        contract: "cf2609",
        instrument: "CF",
        strategy: liveConversation.strategy,
        current_decision: analysis.decision,
        lifecycle: "OBSERVING",
        created_at: "2026-07-28T09:00:00Z"
      },
      ...Array.from({ length: extraHistoryCount }, (_, index) => ({
        case_id: `case-extra-${index + 1}`,
        contract: `zz${String(index + 1).padStart(4, "0")}`,
        instrument: "ZZ",
        strategy: structureStrategy,
        current_decision: analysis.decision,
        lifecycle: "OBSERVING",
        created_at: "2026-07-28T08:00:00Z"
      }))
    ].filter((item) => !deletedCaseIds.has(item.case_id));
    sendJson(response, historyCleared ? [] : cases);
    return;
  }
  if (request.method === "DELETE" && request.url === "/v1/cases") {
    if (deleteFailure) {
      sendJson(response, { detail: "permanent deletion failed" }, 503);
      return;
    }
    const current = historyCleared
      ? []
      : [
          ...createdCases.keys(),
          "case-delete-a",
          "case-delete-b",
          "case-live",
          ...Array.from(
            { length: extraHistoryCount },
            (_, index) => `case-extra-${index + 1}`
          )
        ].filter((caseId) => !deletedCaseIds.has(caseId));
    historyCleared = true;
    createdCases.clear();
    sendJson(response, { deleted: current.length });
    return;
  }
  const deleteCaseMatch = request.url?.match(/^\/v1\/cases\/([^/]+)$/);
  if (request.method === "DELETE" && deleteCaseMatch) {
    if (deleteFailure) {
      sendJson(response, { detail: "permanent deletion failed" }, 503);
      return;
    }
    const caseId = decodeURIComponent(deleteCaseMatch[1]);
    const exists = !historyCleared && (
      createdCases.has(caseId)
      || ["case-delete-a", "case-delete-b", "case-live"].includes(caseId)
    ) && !deletedCaseIds.has(caseId);
    if (exists) {
      deletedCaseIds.add(caseId);
      createdCases.delete(caseId);
    }
    sendJson(response, { deleted: exists ? 1 : 0 });
    return;
  }
  if (request.method === "POST" && request.url === "/v1/cases") {
    const body = await consume(request);
    const payload = JSON.parse(body.toString("utf8"));
    const idempotencyKey = request.headers["idempotency-key"];
    const serializedPayload = JSON.stringify(payload);
    if (!payload.strategy_id || !payload.strategy_version) {
      sendJson(response, { detail: "strategy selection is required" }, 400);
      return;
    }
    if (typeof idempotencyKey === "string" && caseCreations.has(idempotencyKey)) {
      const previous = caseCreations.get(idempotencyKey);
      if (previous.payload !== serializedPayload) {
        sendJson(response, { detail: "idempotency key payload mismatch" }, 409);
        return;
      }
      sendJson(response, { case_id: previous.caseId }, 201);
      return;
    }
    createdCaseSequence += 1;
    const caseId = `case-created-${createdCaseSequence}`;
    const selectedStrategy = payload.strategy_id === momentumStrategy.strategy_id
      ? momentumStrategy
      : structureStrategy;
    createdCases.set(caseId, {
      position: false,
      risk: false,
      images: 0,
      roles: new Set(),
      failAnalysisOnce: String(payload.message ?? "").includes("FAIL_ONCE"),
      failedAnalysis: false,
      analyzed: false,
      strategy: {
        strategy_id: selectedStrategy.strategy_id,
        version: selectedStrategy.version,
        display_name: selectedStrategy.display_name
      },
      initialMessage: String(payload.message ?? "请分析这张图。"),
      messages: []
    });
    if (typeof idempotencyKey === "string") {
      caseCreations.set(idempotencyKey, { caseId, payload: serializedPayload });
    }
    sendJson(response, { case_id: caseId }, 201);
    return;
  }
  const positionMatch = request.url?.match(
    /^\/v1\/cases\/(case-created-\d+)\/position$/
  );
  if (request.method === "POST" && positionMatch) {
    await consume(request);
    const state = createdCases.get(positionMatch[1]);
    if (!state) return sendJson(response, { detail: "case not found" }, 404);
    state.position = true;
    sendJson(response, { direction: "LONG", quantity: 2 });
    return;
  }
  const riskMatch = request.url?.match(
    /^\/v1\/cases\/(case-created-\d+)\/risk$/
  );
  if (request.method === "POST" && riskMatch) {
    const risk = JSON.parse((await consume(request)).toString("utf8"));
    const state = createdCases.get(riskMatch[1]);
    if (!state) return sendJson(response, { detail: "case not found" }, 404);
    if (
      risk.account_risk_limit !== 0.01
      || risk.proposed_risk !== 0.005
      || risk.max_stop_distance_ratio !== 0.03
    ) {
      return sendJson(response, { detail: "unexpected risk defaults" }, 400);
    }
    state.risk = risk;
    sendJson(response, risk);
    return;
  }
  const uploadMatch = request.url?.match(
    /^\/v1\/cases\/(case-created-\d+)\/images$/
  );
  if (request.method === "POST" && uploadMatch) {
    const body = await consume(request);
    const state = createdCases.get(uploadMatch[1]);
    if (!state) return sendJson(response, { detail: "case not found" }, 404);
    if (request.headers["x-privacy-review-token"] !== "test-privacy-token") {
      return sendJson(response, { detail: "privacy review required" }, 403);
    }
    const bodyText = body.toString("latin1");
    for (const role of ["STATE_DAILY", "EXECUTION_60M"]) {
      if (bodyText.includes(role)) state.roles.add(role);
    }
    state.images += 1;
    sendJson(response, { image_id: `image-${state.images}` }, 201);
    return;
  }
  const analysisMatch = request.url?.match(
    /^\/v1\/cases\/(case-created-\d+)\/analysis$/
  );
  if (request.method === "POST" && analysisMatch) {
    await consume(request);
    const state = createdCases.get(analysisMatch[1]);
    if (!state) return sendJson(response, { detail: "case not found" }, 404);
    if (!state.risk || !state.roles.has("STATE_DAILY")) {
      return sendJson(response, { detail: "input pipeline incomplete" }, 400);
    }
    if (state.failAnalysisOnce && !state.failedAnalysis) {
      state.failedAnalysis = true;
      return sendJson(response, { detail: "temporary analysis failure" }, 503);
    }
    state.analyzed = true;
    state.messages = [
      {
        message_id: `message-${analysisMatch[1]}`,
        role: "user",
        message_type: "USER_MESSAGE",
        content: state.initialMessage,
        created_at: "2026-07-28T10:00:00Z",
        analysis_id: null,
        metadata: {}
      },
      {
        message_id: `analysis:${analysis.analysis_id}`,
        role: "assistant",
        message_type: "STRATEGY_CONCLUSION",
        content: analysis.rendered.summary,
        created_at: "2026-07-28T10:00:05Z",
        analysis_id: analysis.analysis_id,
        metadata: {}
      }
    ];
    sendJson(response, analysis);
    return;
  }
  if (
    request.method === "GET"
    && request.url === "/v1/cases/case-live/conversation"
  ) {
    sendJson(response, {
      case_id: "case-live",
      strategy: liveConversation.strategy,
      messages: liveConversation.messages,
      current_analysis_id: liveAnalyses.at(-1).analysis_id
    });
    return;
  }
  const clarificationConversationMatch = request.url?.match(
    /^\/v1\/cases\/(case-(?:(?:clarification|auto-resolve|retry-key|stale-proposal)-desktop|clarification-pending))\/conversation$/
  );
  if (request.method === "GET" && clarificationConversationMatch) {
    const state = clarificationState(clarificationConversationMatch[1]);
    sendJson(response, {
      case_id: clarificationConversationMatch[1],
      strategy: {
        strategy_id: structureStrategy.strategy_id,
        version: structureStrategy.version,
        display_name: structureStrategy.display_name
      },
      messages: [
        {
          message_id: `message-${clarificationConversationMatch[1]}`,
          role: "user",
          message_type: "USER_MESSAGE",
          content: "请分析当前图表。",
          created_at: "2026-07-28T08:59:00Z",
          analysis_id: null,
          metadata: {}
        },
        {
          message_id: `analysis-${clarificationConversationMatch[1]}`,
          role: "assistant",
          message_type: "STRATEGY_CONCLUSION",
          content: state.confirmed
            ? state.result.rendered.summary
            : analysis.rendered.summary,
          created_at: "2026-07-28T09:00:00Z",
          analysis_id: state.confirmed
            ? state.result.analysis_id
            : analysis.analysis_id,
          metadata: {}
        }
      ],
      current_analysis_id: state.confirmed
        ? state.result.analysis_id
        : analysis.analysis_id
    });
    return;
  }
  const createdConversationMatch = request.url?.match(
    /^\/v1\/cases\/(case-created-\d+)\/conversation$/
  );
  if (request.method === "GET" && createdConversationMatch) {
    const state = createdCases.get(createdConversationMatch[1]);
    if (!state) return sendJson(response, { detail: "case not found" }, 404);
    sendJson(response, {
      case_id: createdConversationMatch[1],
      strategy: state.strategy,
      messages: state.messages,
      current_analysis_id: state.analyzed ? "analysis-live" : null
    });
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/v1/cases/case-live/messages"
  ) {
    const body = JSON.parse((await consume(request)).toString("utf8"));
    liveConversation.messages.push(
      {
        message_id: `message-user-${liveConversation.messages.length}`,
        role: "user",
        message_type: "USER_MESSAGE",
        content: body.message,
        created_at: "2026-07-28T09:05:00Z",
        analysis_id: liveAnalyses.at(-1).analysis_id,
        metadata: {}
      },
      {
        message_id: `message-assistant-${liveConversation.messages.length + 1}`,
        role: "assistant",
        message_type: "STRATEGY_EXPLANATION",
        content: "退出结论来自市场状态、策略方向和当前多仓冲突。",
        created_at: "2026-07-28T09:05:01Z",
        analysis_id: liveAnalyses.at(-1).analysis_id,
        metadata: {}
      }
    );
    sendJson(response, {
      source_analysis_id: liveAnalyses.at(-1).analysis_id,
      answer: "退出结论来自市场状态、策略方向和当前多仓冲突。",
      suggested_questions: ["什么条件下可以重新入场？"],
      provider: "fake",
      model: "fixture"
    });
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/v1/cases/case-live/strategy"
  ) {
    const body = JSON.parse((await consume(request)).toString("utf8"));
    const selected = body.strategy_id === momentumStrategy.strategy_id
      ? momentumStrategy
      : structureStrategy;
    liveConversation.strategy = {
      strategy_id: selected.strategy_id,
      version: selected.version,
      display_name: selected.display_name
    };
    liveConversation.messages.push({
      message_id: `strategy-${liveConversation.messages.length}`,
      role: "system",
      message_type: "STRATEGY_CHANGE",
      content: `已切换至${selected.display_name} v${selected.version}`,
      created_at: "2026-07-28T09:06:00Z",
      analysis_id: null,
      metadata: {}
    });
    const reanalysis = appendLiveAnalysis(liveConversation.strategy);
    sendJson(response, {
      ...liveConversation.strategy,
      analysis_id: reanalysis.analysis_id
    });
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/v1/cases/case-live/images"
  ) {
    await consume(request);
    sendJson(response, { image_id: `image-live-${Date.now()}` }, 201);
    return;
  }
  if (
    request.method === "POST"
    && request.url === "/v1/cases/case-live/analysis-requests"
  ) {
    const body = JSON.parse((await consume(request)).toString("utf8"));
    const message = {
      message_id: `analysis-request-${liveConversation.messages.length}`,
      role: "user",
      message_type: "ANALYSIS_REQUEST",
      content: String(body.message ?? ""),
      created_at: "2026-07-28T09:10:00Z",
      analysis_id: liveAnalyses.at(-1).analysis_id,
      metadata: {}
    };
    liveConversation.messages.push(message);
    sendJson(response, message);
    return;
  }
  if (
    request.method === "POST"
    && request.url?.startsWith("/v1/cases/case-live/analysis")
  ) {
    await consume(request);
    sendJson(response, appendLiveAnalysis());
    return;
  }
  if (request.url === "/v1/cases/case-live/images/image-daily") {
    response.setHeader("Content-Type", "image/png");
    response.end(wideDailyImage);
    return;
  }
  if (request.url === "/v1/cases/case-live/images/image-execution") {
    response.setHeader("Content-Type", "image/svg+xml");
    response.end("<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480'><rect width='640' height='480' fill='#eee9da'/><path d='M20 330 L150 330 L220 170 L340 230 L440 160 L620 150' fill='none' stroke='#b53428' stroke-width='8'/></svg>");
    return;
  }
  if (request.url === "/v1/cases/case-live/analyses") {
    sendJson(response, liveAnalyses);
    return;
  }
  if (request.url === "/v1/cases/case-observing/analyses") {
    sendJson(response, [observingAnalysis]);
    return;
  }
  if (request.url === "/v1/cases/case-observing/clarifications") {
    sendJson(response, {
      source_analysis_id: observingAnalysis.analysis_id,
      questions: [],
      history: []
    });
    return;
  }
  const clarificationAnalysesMatch = request.url?.match(
    /^\/v1\/cases\/(case-(?:(?:clarification|auto-resolve|retry-key|stale-proposal)-(?:desktop|mobile)|clarification-pending))\/analyses$/
  );
  if (request.method === "GET" && clarificationAnalysesMatch) {
    const state = clarificationState(clarificationAnalysesMatch[1]);
    sendJson(
      response,
      state.confirmed || state.autoResolved
        ? [previousAnalysis, analysis, state.result]
        : [previousAnalysis, analysis]
    );
    return;
  }
  const clarificationsMatch = request.url?.match(
    /^\/v1\/cases\/(case-(?:(?:clarification|auto-resolve|retry-key|stale-proposal)-(?:desktop|mobile)|clarification-pending)|case-clarification-proxy)\/clarifications$/
  );
  if (clarificationsMatch && request.method === "GET") {
    const state = clarificationState(clarificationsMatch[1]);
    if (
      clarificationsMatch[1].startsWith("case-stale-proposal-")
      && state.proposals.length === 0
    ) {
      const stale = clarificationProposal(
        clarificationsMatch[1],
        "旧分析中的补充说明"
      );
      stale.source_analysis_id = "analysis-previous";
    }
    sendJson(response, {
      source_analysis_id: state.confirmed || state.autoResolved
        ? state.result.analysis_id
        : "analysis-live",
      questions: state.confirmed || state.autoResolved
        ? []
        : clarificationQuestions,
      history: state.proposals
    });
    return;
  }
  if (clarificationsMatch && request.method === "POST") {
    const body = JSON.parse((await consume(request)).toString("utf8"));
    if (body.message === "RETURN_502") {
      sendJson(
        response,
        { detail: "clarification model returned invalid output" },
        502
      );
      return;
    }
    if (clarificationsMatch[1].startsWith("case-auto-resolve-")) {
      const state = clarificationState(clarificationsMatch[1]);
      state.autoResolved = true;
      state.result = {
        ...observingAnalysis,
        analysis_id: `analysis-auto-resolved-${clarificationsMatch[1]}`
      };
      sendJson(response, {
        clarification_id: `clarification-auto-${clarificationsMatch[1]}`,
        source_analysis_id: "analysis-live",
        result_analysis_id: state.result.analysis_id,
        user_message: String(body.message ?? ""),
        facts: [],
        resolved_question_ids: clarificationQuestions.map(
          (item) => item.question_id
        ),
        unresolved_question_ids: [],
        interpretation: "系统已重新读取截图并刷新公开行情，当前不再需要用户补充。",
        provider: "automatic-evidence-refresh",
        model: "deterministic",
        status: "AUTO_RESOLVED"
      });
      return;
    }
    sendJson(
      response,
      clarificationProposal(clarificationsMatch[1], String(body.message ?? ""))
    );
    return;
  }
  const clarificationConfirmMatch = request.url?.match(
    /^\/v1\/cases\/(case-clarification-(?:desktop|mobile|pending))\/clarifications\/([^/]+)\/confirm$/
  );
  if (clarificationConfirmMatch && request.method === "POST") {
    await consume(request);
    const state = clarificationState(clarificationConfirmMatch[1]);
    const proposal = state.proposals.find(
      (item) => item.clarification_id === clarificationConfirmMatch[2]
    );
    if (!proposal) {
      sendJson(response, { detail: "clarification not found" }, 404);
      return;
    }
    const result = clarifiedAnalysis(
      clarificationConfirmMatch[1],
      clarificationConfirmMatch[2]
    );
    proposal.status = "CONFIRMED";
    proposal.confirmed_at = "2026-07-22T08:30:00Z";
    proposal.result_analysis_id = result.analysis_id;
    state.confirmed = true;
    state.result = result;
    sendJson(response, result);
    return;
  }
  const createdAnalysesMatch = request.url?.match(
    /^\/v1\/cases\/(case-created-\d+)\/analyses$/
  );
  if (createdAnalysesMatch) {
    const state = createdCases.get(createdAnalysesMatch[1]);
    if (!state?.analyzed) {
      sendJson(response, { detail: "case not found" }, 404);
      return;
    }
    sendJson(response, [analysis]);
    return;
  }
  sendJson(response, { detail: "case not found" }, 404);
}).listen(3199, "127.0.0.1");
