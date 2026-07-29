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
      { detail: "只允许从本机磐石页面切换策略。" },
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
    return Response.json({ detail: "invalid strategy payload" }, { status: 400 });
  }
  const record = typeof payload === "object" && payload !== null
    ? payload as Record<string, unknown>
    : {};
  if (
    Object.keys(record).some((item) => !["strategy_id", "version"].includes(item))
    || typeof record.strategy_id !== "string"
    || !record.strategy_id
    || (record.version !== undefined && typeof record.version !== "string")
  ) {
    return Response.json({ detail: "invalid strategy selection" }, { status: 400 });
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "strategy proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/strategy`,
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
      { detail: "unable to reach strategy service" },
      { status: 502 }
    );
  }
}
