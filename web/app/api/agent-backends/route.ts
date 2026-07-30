import {
  proxyConfiguration,
  relayJson
} from "../../../lib/server-proxy";

export async function GET(): Promise<Response> {
  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "Agent proxy is not configured" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/agent-backends`,
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
      { detail: "unable to reach Agent service" },
      { status: 502 }
    );
  }
}
