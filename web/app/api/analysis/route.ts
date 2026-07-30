import {
  proxyConfiguration,
  trustedLocalOrigin
} from "../../../lib/server-proxy";

const CONTRACT_PATTERN = /^[A-Za-z]{1,3}\d{3,4}$/;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const POSITION_DIRECTIONS = new Set(["AUTO", "FLAT", "LONG", "SHORT", "UNKNOWN"]);
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_REQUEST_BYTES = 52 * 1024 * 1024;
const ALLOWED_FORM_FIELDS = new Set([
  "submissionId",
  "resumeCaseId",
  "contract",
  "message",
  "positionDirection",
  "quantity",
  "averageCost",
  "stopPrice",
  "accountRiskLimit",
  "proposedRisk",
  "maxStopDistance",
  "correlatedExposure",
  "privacyConfirmed",
  "dailyImage",
  "executionImage"
  ,"strategyId"
  ,"strategyVersion"
  ,"agentBackendId"
  ,"agentModelId"
]);
const ALLOWED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

type Stage = "case" | "position" | "risk" | "images" | "analysis";

class InputError extends Error {}

function requiredText(formData: FormData, name: string, label: string): string {
  const value = formData.get(name);
  if (typeof value !== "string" || !value.trim()) {
    throw new InputError(`${label}不能为空。`);
  }
  return value.trim();
}

function optionalText(formData: FormData, name: string): string | null {
  const value = formData.get(name);
  if (typeof value !== "string" || !value.trim()) return null;
  return value.trim();
}

function percentage(
  formData: FormData,
  name: string,
  label: string,
  strictPositive = false,
  defaultValue?: number
): number {
  const candidate = formData.get(name);
  const raw = typeof candidate === "string" && candidate.trim()
    ? candidate.trim()
    : defaultValue === undefined
      ? requiredText(formData, name, label)
      : String(defaultValue);
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new InputError(`${label}必须在 0% 到 100% 之间。`);
  }
  if (strictPositive && value === 0) {
    throw new InputError(`${label}必须大于 0%。`);
  }
  return value / 100;
}

function optionalPositiveNumber(
  formData: FormData,
  name: string,
  label: string
): number | null {
  const raw = formData.get(name);
  if (typeof raw !== "string" || !raw.trim()) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new InputError(`${label}必须大于 0。`);
  }
  return value;
}

function requiredFile(formData: FormData, name: string, label: string): File {
  const value = formData.get(name);
  if (!(value instanceof File) || value.size === 0) {
    throw new InputError(`请上传${label}。`);
  }
  if (value.size > MAX_FILE_BYTES) {
    throw new InputError(`${label}不能超过 25 MiB。`);
  }
  if (!ALLOWED_IMAGE_TYPES.has(value.type)) {
    throw new InputError(`${label}仅支持 PNG、JPEG 或 WebP。`);
  }
  return value;
}

function optionalFile(formData: FormData, name: string, label: string): File | null {
  const value = formData.get(name);
  if (!(value instanceof File) || value.size === 0) return null;
  if (value.size > MAX_FILE_BYTES) {
    throw new InputError(`${label}不能超过 25 MiB。`);
  }
  if (!ALLOWED_IMAGE_TYPES.has(value.type)) {
    throw new InputError(`${label}仅支持 PNG、JPEG 或 WebP。`);
  }
  return value;
}

async function sha256Hex(value: string | ArrayBuffer): Promise<string> {
  const bytes = typeof value === "string"
    ? new TextEncoder().encode(value)
    : value;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function upstreamDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string };
    if (payload.detail) return payload.detail;
  } catch {
    // Fall through to the HTTP status when the upstream body is not JSON.
  }
  return `分析服务返回 ${response.status}`;
}

export async function POST(request: Request): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面提交分析。" },
      { status: 403 }
    );
  }
  const contentLength = Number(request.headers.get("content-length"));
  if (
    !Number.isSafeInteger(contentLength)
    || contentLength <= 0
    || contentLength > MAX_REQUEST_BYTES
  ) {
    return Response.json(
      { detail: "提交内容大小无效或超过 52 MiB。" },
      { status: 413 }
    );
  }
  const configuration = proxyConfiguration();
  const privacyToken = process.env.TRADING_AGENT_PRIVACY_REVIEW_TOKEN;
  if (!configuration || !privacyToken) {
    return Response.json(
      { detail: "本地分析服务缺少 API 或隐私审核配置。" },
      { status: 503 }
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return Response.json({ detail: "无法读取提交内容。" }, { status: 400 });
  }
  for (const key of formData.keys()) {
    if (!ALLOWED_FORM_FIELDS.has(key)) {
      return Response.json({ detail: `不支持的输入字段：${key}` }, { status: 400 });
    }
  }
  if (
    formData.getAll("dailyImage").length !== 1
    || formData.getAll("executionImage").length > 1
  ) {
    return Response.json({ detail: "图表文件数量无效。" }, { status: 400 });
  }

  let input: {
    submissionId: string;
    submissionFingerprint: string;
    resumeCaseId: string | null;
    contract: string | null;
    message: string;
    position: {
      direction: string;
      quantity: number;
      average_cost: number | null;
      stop_price: number | null;
    } | null;
    risk: {
      account_risk_limit: number;
      proposed_risk: number;
      max_stop_distance_ratio: number;
      correlated_exposure_exceeded: boolean;
    };
    dailyImage: File;
    executionImage: File | null;
    strategyId: string;
    strategyVersion: string;
    agentBackendId: string;
    agentModelId: string;
  };
  try {
    const contract = optionalText(formData, "contract")?.toLowerCase() ?? null;
    if (contract && !CONTRACT_PATTERN.test(contract)) {
      throw new InputError("合约代码格式不正确，例如 rb2610。");
    }
    const submissionCandidate = formData.get("submissionId");
    const submissionId = typeof submissionCandidate === "string"
      && SAFE_ID.test(submissionCandidate)
      ? submissionCandidate
      : crypto.randomUUID();
    const resumeCandidate = formData.get("resumeCaseId");
    const resumeCaseId = typeof resumeCandidate === "string"
      && resumeCandidate
      ? resumeCandidate
      : null;
    if (resumeCaseId && !SAFE_ID.test(resumeCaseId)) {
      throw new InputError("恢复案例标识无效。");
    }
    const direction = optionalText(formData, "positionDirection") ?? "AUTO";
    if (!POSITION_DIRECTIONS.has(direction)) {
      throw new InputError("当前持仓状态不受支持。");
    }
    const hasPosition = direction === "LONG" || direction === "SHORT";
    const rawQuantity = Number(formData.get("quantity") ?? 0);
    const quantity = hasPosition ? rawQuantity : 0;
    if (hasPosition && (!Number.isInteger(quantity) || quantity <= 0)) {
      throw new InputError("持仓手数必须是大于 0 的整数。");
    }
    if (formData.get("privacyConfirmed") !== "on") {
      throw new InputError("请先确认图表隐私与模型分析授权。");
    }
    const message = optionalText(formData, "message")
      ?? "请基于截图和公开行情，严格按八步策略判断当前如何操作。";
    const position = direction === "AUTO" ? null : {
        direction,
        quantity,
        average_cost: hasPosition
          ? optionalPositiveNumber(formData, "averageCost", "持仓成本")
          : null,
        stop_price: hasPosition
          ? optionalPositiveNumber(formData, "stopPrice", "当前止损")
          : null
      };
    const risk = {
        account_risk_limit: percentage(
          formData,
          "accountRiskLimit",
          "账户单笔风险上限",
          true,
          1
        ),
        proposed_risk: percentage(
          formData,
          "proposedRisk",
          "本次计划风险",
          false,
          0.5
        ),
        max_stop_distance_ratio: percentage(
          formData,
          "maxStopDistance",
          "最大止损距离",
          true,
          3
        ),
        correlated_exposure_exceeded: formData.get("correlatedExposure") === "on"
      };
    const dailyImage = requiredFile(formData, "dailyImage", "完整日线图");
    const executionImage = optionalFile(
      formData,
      "executionImage",
      "执行周期图"
    );
    const strategyId = requiredText(formData, "strategyId", "分析策略");
    const strategyVersion = requiredText(
      formData,
      "strategyVersion",
      "策略版本"
    );
    const agentBackendId = requiredText(
      formData,
      "agentBackendId",
      "分析 Agent"
    );
    const agentModelId = requiredText(
      formData,
      "agentModelId",
      "分析模型"
    );
    const dailySha256 = await sha256Hex(await dailyImage.arrayBuffer());
    const executionSha256 = executionImage
      ? await sha256Hex(await executionImage.arrayBuffer())
      : null;
    const submissionFingerprint = await sha256Hex(JSON.stringify({
      contract,
      message,
      position,
      risk,
      dailyImage: {
        role: "STATE_DAILY",
        type: dailyImage.type,
        sha256: dailySha256
      },
      executionImage: executionImage
        ? {
            role: "EXECUTION_60M",
            type: executionImage.type,
            sha256: executionSha256
          }
        : null,
      strategyId,
      strategyVersion,
      agentBackendId,
      agentModelId
    }));
    input = {
      submissionId,
      submissionFingerprint,
      resumeCaseId,
      contract,
      message,
      position,
      risk,
      dailyImage,
      executionImage,
      strategyId,
      strategyVersion,
      agentBackendId,
      agentModelId
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "输入内容无效。";
    return Response.json({ detail }, { status: 400 });
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      let currentStage: Stage = "case";
      let caseId: string | null = null;
      const emit = (payload: object) => {
        controller.enqueue(encoder.encode(`${JSON.stringify(payload)}\n`));
      };
      const idempotencyKey = (stage: string) => (
        `${input.submissionId}:${stage}`.slice(0, 200)
      );
      const progress = (
        stage: Stage,
        status: "running" | "completed",
        message: string,
        progressCaseId?: string
      ) => {
        emit({
          type: "progress",
          stage,
          status,
          message,
          ...(progressCaseId ? { caseId: progressCaseId } : {})
        });
      };
      const apiFetch = async (
        path: string,
        init: RequestInit,
      ): Promise<Response> => {
        const response = await fetch(`${configuration.baseUrl}${path}`, {
          ...init,
          headers: {
            Authorization: `Bearer ${configuration.apiToken}`,
            ...init.headers
          },
          cache: "no-store"
        });
        if (!response.ok) {
          throw new Error(await upstreamDetail(response));
        }
        return response;
      };

      try {
        progress(
          "case",
          "running",
          input.resumeCaseId ? "正在校验并恢复可审计案例" : "正在创建可审计案例"
        );
        const instrument = input.contract?.match(/^[a-z]+/)?.[0] ?? null;
        const createdResponse = await apiFetch("/v1/cases", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("case")
          },
          body: JSON.stringify({
            instrument,
            contract: input.contract,
            message: input.message,
            submission_fingerprint: input.submissionFingerprint,
            strategy_id: input.strategyId,
            strategy_version: input.strategyVersion,
            agent_backend_id: input.agentBackendId,
            agent_model_id: input.agentModelId
          })
        });
        const created = await createdResponse.json() as { case_id: string };
        if (input.resumeCaseId && input.resumeCaseId !== created.case_id) {
          throw new Error("恢复案例与原始提交不一致，请新建分析。");
        }
        caseId = created.case_id;
        progress(
          "case",
          "completed",
          input.resumeCaseId ? `案例 ${caseId} 已恢复` : `案例 ${caseId} 已创建`,
          caseId
        );

        currentStage = "position";
        if (input.position) {
          progress("position", "running", "正在保存用户明确提供的持仓分支");
          await apiFetch(`/v1/cases/${encodeURIComponent(caseId)}/position`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": idempotencyKey("position")
            },
            body: JSON.stringify(input.position)
          });
          progress("position", "completed", "持仓状态已固化");
        } else {
          progress("position", "running", "正在从账户私有描述识别持仓");
          progress("position", "completed", "未提供结构化覆盖，保留自动识别结果");
        }

        currentStage = "risk";
        progress("risk", "running", "正在保存独立风控边界");
        await apiFetch(`/v1/cases/${encodeURIComponent(caseId)}/risk`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey("risk")
          },
          body: JSON.stringify(input.risk)
        });
        progress("risk", "completed", "风险参数已固化");

        currentStage = "images";
        progress("images", "running", "正在保存原图与证据角色");
        const images = [
          { file: input.dailyImage, role: "STATE_DAILY" },
          ...(input.executionImage
            ? [{ file: input.executionImage, role: "EXECUTION_60M" }]
            : [])
        ];
        for (const [index, image] of images.entries()) {
          const upload = new FormData();
          upload.set("file", image.file, image.file.name);
          upload.set("image_role", image.role);
          upload.set("role_confirmed", "true");
          upload.set("privacy_reviewed", "true");
          await apiFetch(`/v1/cases/${encodeURIComponent(caseId)}/images`, {
            method: "POST",
            headers: {
              "Idempotency-Key": idempotencyKey(`image-${index}-${image.role}`),
              "X-Privacy-Review-Token": privacyToken
            },
            body: upload
          });
        }
        progress("images", "completed", `${images.length} 张原图已进入证据链`);

        currentStage = "analysis";
        const agentName = input.agentBackendId === "kimi"
          ? "Kimi Code"
          : "Codex";
        progress(
          "analysis",
          "running",
          `${agentName} 正在执行多模态抽取与策略分析`
        );
        const analysisResponse = await apiFetch(
          `/v1/cases/${encodeURIComponent(caseId)}/analysis`,
          {
            method: "POST",
            headers: { "Idempotency-Key": idempotencyKey("analysis") }
          }
        );
        const analysis = await analysisResponse.json() as { analysis_id: string };
        progress("analysis", "completed", "策略里程碑与最终动作已生成");
        emit({
          type: "complete",
          caseId,
          analysisId: analysis.analysis_id
        });
      } catch (error) {
        emit({
          type: "error",
          stage: currentStage,
          message: error instanceof Error ? error.message : "分析提交失败。",
          caseId
        });
      } finally {
        controller.close();
      }
    }
  });

  return new Response(stream, {
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/x-ndjson; charset=utf-8"
    }
  });
}
