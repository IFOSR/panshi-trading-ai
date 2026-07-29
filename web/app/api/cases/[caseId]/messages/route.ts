import {
  proxyConfiguration,
  relayJson,
  requestIdempotencyKey,
  SAFE_ID,
  trustedLocalOrigin
} from "../../../../../lib/server-proxy";

type RouteContext = {
  params: Promise<{ caseId: string }>;
};

export async function POST(
  request: Request,
  context: RouteContext
): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面提交追问。" },
      { status: 403 }
    );
  }
  const { caseId } = await context.params;
  if (!SAFE_ID.test(caseId)) {
    return Response.json({ detail: "invalid case identifier" }, { status: 400 });
  }
  const key = requestIdempotencyKey(request);
  if (!key) {
    return Response.json(
      { detail: "valid Idempotency-Key is required" },
      { status: 400 }
    );
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ detail: "invalid message payload" }, { status: 400 });
  }
  const message = (
    typeof payload === "object"
    && payload !== null
    && !Array.isArray(payload)
    && Object.keys(payload).every((item) => item === "message")
    && typeof (payload as { message?: unknown }).message === "string"
  )
    ? (payload as { message: string }).message.trim()
    : "";
  if (!message || message.length > 4000) {
    return Response.json({ detail: "invalid conversation message" }, { status: 400 });
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "conversation proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/messages`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`,
          "Content-Type": "application/json",
          "Idempotency-Key": key
        },
        body: JSON.stringify({ message }),
        cache: "no-store"
      }
    );
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach conversation service" },
      { status: 502 }
    );
  }
}
