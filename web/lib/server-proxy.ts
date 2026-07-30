const LOOPBACK_HOSTS = new Set([
  "127.0.0.1",
  "localhost",
  "panshi.localhost",
  "[::1]"
]);
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;

export const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

export function trustedLocalOrigin(request: Request): boolean {
  const requestUrl = new URL(request.url);
  const originHeader = request.headers.get("origin");
  if (!originHeader) return false;
  let originUrl: URL;
  try {
    originUrl = new URL(originHeader);
  } catch {
    return false;
  }
  const effectivePort = (url: URL) => (
    url.port || (url.protocol === "https:" ? "443" : "80")
  );
  return (
    LOOPBACK_HOSTS.has(requestUrl.hostname)
    && LOOPBACK_HOSTS.has(originUrl.hostname)
    && originUrl.protocol === requestUrl.protocol
    && effectivePort(originUrl) === effectivePort(requestUrl)
  );
}

export function proxyConfiguration(): {
  baseUrl: string;
  apiToken: string;
} | null {
  const baseUrl = process.env.TRADING_API_URL;
  const apiToken = process.env.TRADING_AGENT_API_TOKEN;
  if (!baseUrl || !apiToken) return null;
  try {
    const parsed = new URL(baseUrl);
    if (
      !["http:", "https:"].includes(parsed.protocol)
      || !LOOPBACK_HOSTS.has(parsed.hostname)
      || parsed.username
      || parsed.password
    ) {
      return null;
    }
    return { baseUrl: parsed.origin, apiToken };
  } catch {
    return null;
  }
}

export function requestIdempotencyKey(request: Request): string | null {
  const key = request.headers.get("Idempotency-Key");
  return key && IDEMPOTENCY_KEY.test(key) ? key : null;
}

export async function relayJson(upstream: Response): Promise<Response> {
  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": upstream.headers.get("content-type") ?? "application/json"
    }
  });
}
