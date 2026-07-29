import { NextResponse } from "next/server";

import {
  authConfiguration,
  browserCookieSecure,
  safeNextPath,
  SESSION_COOKIE
} from "../../../../lib/auth";
import { trustedLocalOrigin } from "../../../../lib/server-proxy";

export async function POST(request: Request): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json({ detail: "forbidden" }, { status: 403 });
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ detail: "invalid login request" }, { status: 400 });
  }
  const body = typeof payload === "object" && payload !== null
    ? payload as Record<string, unknown>
    : {};
  if (
    Object.keys(body).some(
      (key) => !["username", "password", "next"].includes(key)
    )
    || typeof body.username !== "string"
    || typeof body.password !== "string"
    || (body.next !== undefined && typeof body.next !== "string")
  ) {
    return Response.json({ detail: "invalid login request" }, { status: 400 });
  }
  const configuration = authConfiguration();
  if (!configuration) {
    return Response.json(
      { detail: "authentication service unavailable" },
      { status: 503 }
    );
  }
  try {
    const upstream = await fetch(`${configuration.baseUrl}/v1/auth/login`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${configuration.apiToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        username: body.username,
        password: body.password
      }),
      cache: "no-store"
    });
    if (upstream.status === 401) {
      return Response.json(
        { detail: "invalid username or password" },
        { status: 401 }
      );
    }
    if (!upstream.ok) {
      return Response.json(
        { detail: "authentication service unavailable" },
        { status: 503 }
      );
    }
    const result = await upstream.json() as {
      username: string;
      session_token: string;
      expires_at: string;
    };
    const response = NextResponse.json({
      username: result.username,
      next: safeNextPath(
        typeof body.next === "string" ? body.next : undefined
      )
    });
    response.cookies.set(SESSION_COOKIE, result.session_token, {
      httpOnly: true,
      sameSite: "strict",
      secure: browserCookieSecure(),
      path: "/",
      expires: new Date(result.expires_at)
    });
    return response;
  } catch {
    return Response.json(
      { detail: "authentication service unavailable" },
      { status: 503 }
    );
  }
}
