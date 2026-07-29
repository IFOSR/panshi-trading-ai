import {
  proxyConfiguration,
  relayJson,
  requestIdempotencyKey,
  SAFE_ID,
  trustedLocalOrigin
} from "../../../../../../../lib/server-proxy";

type RouteContext = {
  params: Promise<{
    caseId: string;
    clarificationId: string;
  }>;
};

export async function POST(
  request: Request,
  context: RouteContext
): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面确认澄清。" },
      { status: 403 }
    );
  }
  const { caseId, clarificationId } = await context.params;
  if (!SAFE_ID.test(caseId) || !SAFE_ID.test(clarificationId)) {
    return Response.json(
      { detail: "invalid clarification identifier" },
      { status: 400 }
    );
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
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/clarifications/${encodeURIComponent(clarificationId)}/confirm`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`,
          "Idempotency-Key": idempotencyKey
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
