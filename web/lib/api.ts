export type Milestone = {
  number: number;
  title: string;
  status: "CONFIRMED" | "CANDIDATE" | "BLOCKED" | "INVALIDATED";
  result: string;
  rule: string;
  input: string;
  evidence: string;
  next: string;
};

export const demoCase = {
  action: "等待补齐数据",
  marketState: "U · 偏空过渡",
  strategy: "暂未启用",
  progress: "第 5 / 8 步",
  blockers: ["真实合约待确认", "日线收盘状态未知", "缺少 60 分钟执行图"],
  nextMilestone: "确认真实合约，并以 60 分钟价格结构验证方向",
  cutoff: "2026-07-20 15:00 CST",
  changes: "新增日线原图；价格位置与动量候选成立；动作仍为等待数据。",
  milestones: [
    ["数据有效性", "BLOCKED", "关键元数据不完整", "DQ-001", "原图、合约、周期、收盘状态", "Codex / gpt-5.6-sol · 原图哈希已记录", "补齐合约与收盘状态"],
    ["市场状态", "CONFIRMED", "U · 偏空过渡", "MS-001", "日线结构、BOLL 位置", "价格位于 BOLL 中轨下方", "等待已收盘日线确认"],
    ["策略许可", "BLOCKED", "无可执行策略", "SP-001", "市场状态与数据门禁", "过渡状态禁止启用趋势策略", "进入 T- 或区间边界"],
    ["价格位置", "CONFIRMED", "中轨下方、下轨上方", "PL-001", "BOLL(20,2)", "中轨 16964.50 / 下轨 15847.29", "观察关键边界反应"],
    ["量仓行为", "CANDIDATE", "缩量，持仓含义待核验", "PB-001", "成交量与总持仓", "量 77430 / 均量 229404.80", "补充结构化持仓数据"],
    ["动量", "CANDIDATE", "空头动能修复", "MO-001", "MACD(12,26,9)", "DIF -129.60 / DEA -153.87", "不得单独触发入场"],
    ["价格确认", "BLOCKED", "执行周期未确认", "PC-001", "60 分钟突破、回踩、守住", "尚未上传执行图", "等待 60 分钟结构确认"],
    ["风险与动作", "BLOCKED", "等待补齐数据", "RK-001", "数据、策略、价格、风险", "独立风控阻断精确动作", "风险通过后重新计算动作"]
  ].map((item, index) => ({
    number: index + 1,
    title: item[0],
    status: item[1],
    result: item[2],
    rule: item[3],
    input: item[4],
    evidence: item[5],
    next: item[6]
  })) as Milestone[]
};

type ApiMilestone = {
  number: number;
  code: string;
  status: Milestone["status"];
  result: string;
  rule_ids: string[];
  blockers: string[];
  next_conditions: string[];
  evidence_refs: string[];
};

type ApiAnalysis = {
  milestones: ApiMilestone[];
  decision: {
    action: string;
    market_state: string;
    strategy: string | null;
    blocking_steps: number[];
    next_milestone: string | null;
  };
  rendered: { summary: string };
  evidence: { cutoff_time: string | null; last_bar_closed: boolean | null; provider: string; model: string };
};

export async function getCaseView(caseId: string): Promise<typeof demoCase> {
  const baseUrl = process.env.TRADING_API_URL;
  if (!baseUrl) return demoCase;
  try {
    const response = await fetch(`${baseUrl}/v1/cases/${caseId}/analyses`, { cache: "no-store" });
    if (!response.ok) return demoCase;
    const analyses = await response.json() as ApiAnalysis[];
    const latest = analyses.at(-1);
    if (!latest) return demoCase;
    return {
      action: latest.rendered.summary,
      marketState: latest.decision.market_state,
      strategy: latest.decision.strategy ?? "暂未启用",
      progress: `第 ${latest.milestones.filter((item) => item.status !== "BLOCKED").length} / 8 步`,
      blockers: latest.milestones.flatMap((item) => item.blockers).slice(0, 3),
      nextMilestone: latest.decision.next_milestone ?? "等待下一次分析",
      cutoff: latest.evidence.cutoff_time ?? "截止时间未知",
      changes: "已从案例事件库载入最新分析。",
      milestones: latest.milestones.map((item) => ({
        number: item.number,
        title: item.code,
        status: item.status,
        result: item.result,
        rule: item.rule_ids.join(", ") || "BLOCKER",
        input: item.blockers.join("；") || "输入已通过当前规则",
        evidence: `${latest.evidence.provider} / ${latest.evidence.model} · ${item.evidence_refs.join(", ") || "结构化状态"}`,
        next: item.next_conditions.join("；") || "保持当前状态"
      }))
    };
  } catch {
    return demoCase;
  }
}
