import {
  proxyConfiguration,
  relayJson,
  SAFE_ID,
  trustedLocalOrigin
} from "../../../../lib/server-proxy";

type RouteContext = {
  params: Promise<{ caseId: string }>;
};

export async function DELETE(
  request: Request,
  context: RouteContext
): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面删除对话。" },
      { status: 403 }
    );
  }
  const { caseId } = await context.params;
  if (!SAFE_ID.test(caseId)) {
    return Response.json({ detail: "invalid case identifier" }, { status: 400 });
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "case proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}`,
      {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`
        },
        cache: "no-store"
      }
    );
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach case service" },
      { status: 502 }
    );
  }
}
