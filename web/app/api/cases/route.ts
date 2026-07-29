import {
  proxyConfiguration,
  relayJson,
  trustedLocalOrigin
} from "../../../lib/server-proxy";

export async function GET(): Promise<Response> {
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "case proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(`${configuration.baseUrl}/v1/cases`, {
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`
      },
      cache: "no-store"
    });
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach case service" },
      { status: 502 }
    );
  }
}

export async function DELETE(request: Request): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json(
      { detail: "只允许从本机磐石页面清空对话。" },
      { status: 403 }
    );
  }
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "case proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(`${configuration.baseUrl}/v1/cases`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`
      },
      cache: "no-store"
    });
    return relayJson(upstream);
  } catch {
    return Response.json(
      { detail: "unable to reach case service" },
      { status: 502 }
    );
  }
}
