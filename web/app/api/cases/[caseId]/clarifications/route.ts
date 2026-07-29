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

export async function GET(
  _request: Request,
  context: RouteContext
): Promise<Response> {
  const { caseId } = await context.params;
  if (!SAFE_ID.test(caseId)) {
    return Response.json({ detail: "invalid case identifier" }, { status: 400 });
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "clarification proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/clarifications`,
      {
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`
        },
        cache: "no-store"
      }
    );
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach clarification service" },
      { status: 502 }
    );
  }
}

export async function POST(
  request: Request,
  context: RouteContext
): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面提交澄清。" },
      { status: 403 }
    );
  }
  const { caseId } = await context.params;
  if (!SAFE_ID.test(caseId)) {
    return Response.json({ detail: "invalid case identifier" }, { status: 400 });
  }
  const idempotencyKey = requestIdempotencyKey(request);
  if (!idempotencyKey) {
    return Response.json(
      { detail: "valid Idempotency-Key is required" },
      { status: 400 }
    );
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "clarification proxy is not configured" },
      { status: 503 }
    );
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ detail: "invalid clarification payload" }, { status: 400 });
  }
  if (
    typeof payload !== "object"
    || payload === null
    || Array.isArray(payload)
    || Object.keys(payload).some((key) => key !== "message")
    || typeof (payload as { message?: unknown }).message !== "string"
    || !(payload as { message: string }).message.trim()
    || (payload as { message: string }).message.length > 4000
  ) {
    return Response.json({ detail: "invalid clarification message" }, { status: 400 });
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/clarifications`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`,
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey
        },
        body: JSON.stringify({
          message: (payload as { message: string }).message.trim()
        }),
        cache: "no-store"
      }
    );
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach clarification service" },
      { status: 502 }
    );
  }
}
