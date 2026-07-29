import {
  proxyConfiguration,
  relayJson,
  requestIdempotencyKey,
  SAFE_ID,
  trustedLocalOrigin
} from "../../../../../lib/server-proxy";

const ALLOWED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_FILE_BYTES = 25 * 1024 * 1024;

type RouteContext = {
  params: Promise<{ caseId: string }>;
};

async function detail(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string };
    if (payload.detail) return payload.detail;
  } catch {
    // Use the status fallback for non-JSON upstream responses.
  }
  return `分析服务返回 ${response.status}`;
}

export async function POST(
  request: Request,
  context: RouteContext
): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面更新分析。" },
      { status: 403 }
    );
  }
  const { caseId } = await context.params;
  const key = requestIdempotencyKey(request);
  if (!SAFE_ID.test(caseId) || !key) {
    return Response.json(
      { detail: "invalid case identifier or idempotency key" },
      { status: 400 }
    );
  }
  const configuration = proxyConfiguration();
  const privacyToken = process.env.TRADING_AGENT_PRIVACY_REVIEW_TOKEN;
  if (!configuration || !privacyToken) {
    return Response.json(
      { detail: "analysis proxy is not configured" },
      { status: 503 }
    );
  }
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return Response.json({ detail: "invalid analysis update" }, { status: 400 });
  }
  const messageValue = formData.get("message");
  const message = typeof messageValue === "string" ? messageValue.trim() : "";
  const files = formData.getAll("images").filter(
    (item): item is File => item instanceof File && item.size > 0
  );
  if (!message || message.length > 4000 || files.length > 2) {
    return Response.json({ detail: "invalid analysis update" }, { status: 400 });
  }
  if (
    files.some((file) => (
      file.size > MAX_FILE_BYTES || !ALLOWED_IMAGE_TYPES.has(file.type)
    ))
  ) {
    return Response.json({ detail: "invalid analysis attachment" }, { status: 400 });
  }
  if (files.length > 0 && formData.get("privacyConfirmed") !== "on") {
    return Response.json(
      { detail: "请先确认新增截图的隐私与模型分析授权。" },
      { status: 400 }
    );
  }
  const upstream = async (
    path: string,
    init: RequestInit
  ): Promise<Response> => {
    const response = await fetch(`${configuration.baseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`,
        ...init.headers
      },
      cache: "no-store"
    });
    if (!response.ok) throw new Error(await detail(response));
    return response;
  };
  try {
    for (const [index, file] of files.entries()) {
      const upload = new FormData();
      upload.set("file", file, file.name);
      upload.set(
        "image_role",
        index === 0 ? "STATE_DAILY" : "EXECUTION_60M"
      );
      upload.set("role_confirmed", "true");
      upload.set("privacy_reviewed", "true");
      await upstream(
        `/v1/cases/${encodeURIComponent(caseId)}/images`,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": `${key}:image:${index}`,
            "X-Privacy-Review-Token": privacyToken
          },
          body: upload
        }
      );
    }
    await upstream(
      `/v1/cases/${encodeURIComponent(caseId)}/analysis-requests`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `${key}:request`
        },
        body: JSON.stringify({ message })
      }
    );
    const analysis = await upstream(
      `/v1/cases/${encodeURIComponent(caseId)}/analysis`,
      {
        method: "POST",
        headers: { "Idempotency-Key": `${key}:analysis` }
      }
    );
    return relayJson(analysis);
  } catch (error) {
    return Response.json(
      { detail: error instanceof Error ? error.message : "unable to update analysis" },
      { status: 502 }
    );
  }
}
