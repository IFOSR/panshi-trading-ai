import {
  proxyConfiguration,
  SAFE_ID
} from "../../../../../../lib/server-proxy";

type RouteContext = {
  params: Promise<{
    caseId: string;
    imageId: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const { caseId, imageId } = await context.params;
  if (!SAFE_ID.test(caseId) || !SAFE_ID.test(imageId)) {
    return Response.json({ detail: "invalid image identifier" }, { status: 400 });
  }

  const configuration = proxyConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "image proxy is not configured" },
      { status: 503 }
    );
  }

  try {
    const upstream = await fetch(
      `${configuration.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/images/${encodeURIComponent(imageId)}`,
      {
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`
        },
        cache: "no-store"
      }
    );
    const headers = new Headers({
      "Cache-Control": "no-store"
    });
    const contentType = upstream.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);

    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers
    });
  } catch {
    return Response.json(
      { detail: "unable to reach image service" },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" }
      }
    );
  }
}
