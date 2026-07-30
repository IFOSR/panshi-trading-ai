export const SESSION_COOKIE = "panshi_session";

const LOOPBACK_HOSTS = new Set([
  "127.0.0.1",
  "localhost",
  "panshi.localhost",
  "[::1]"
]);

export function safeNextPath(value: string | null | undefined): string {
  if (
    !value
    || !value.startsWith("/")
    || value.startsWith("//")
    || value.startsWith("/login")
  ) {
    return "/";
  }
  try {
    const parsed = new URL(value, "http://127.0.0.1");
    return LOOPBACK_HOSTS.has(parsed.hostname)
      ? `${parsed.pathname}${parsed.search}${parsed.hash}`
      : "/";
  } catch {
    return "/";
  }
}

export function authConfiguration(): {
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

export async function validateSessionToken(token: string): Promise<{
  status: "valid";
  username: string;
  expiresAt: string;
} | {
  status: "invalid";
} | {
  status: "unavailable";
}> {
  const configuration = authConfiguration();
  if (!configuration) return { status: "unavailable" };
  try {
    const response = await fetch(`${configuration.baseUrl}/v1/auth/session`, {
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`,
        "X-Panshi-Session": token
      },
      cache: "no-store"
    });
    if (response.status === 401) return { status: "invalid" };
    if (!response.ok) return { status: "unavailable" };
    const payload = await response.json() as {
      username: string;
      expires_at: string;
    };
    return {
      status: "valid",
      username: payload.username,
      expiresAt: payload.expires_at
    };
  } catch {
    return { status: "unavailable" };
  }
}

export function browserCookieSecure(): boolean {
  return process.env.TRADING_AGENT_ENVIRONMENT !== "local";
}
