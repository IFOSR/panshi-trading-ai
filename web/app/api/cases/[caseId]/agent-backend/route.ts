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
      { detail: "只允许从本机磐石页面切换 Agent。" },
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
    return Response.json({ detail: "invalid Agent payload" }, { status: 400 });
  }
  const record = typeof payload === "object" && payload !== null
    ? payload as Record<string, unknown>
    : {};
  if (
    Object.keys(record).some(
      (item) => !["backend_id", "model_id"].includes(item)
    )
    || typeof record.backend_id !== "string"
    || !record.backend_id
    || typeof record.model_id !== "string"
    || !record.model_id
  ) {
    return Response.json({ detail: "invalid Agent selection" }, { status: 400 });
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "Agent proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/agent-backend`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`,
          "Content-Type": "application/json",
          "Idempotency-Key": key
        },
        body: JSON.stringify(record),
        cache: "no-store"
      }
    );
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach Agent service" },
      { status: 502 }
    );
  }
}
