import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  authConfiguration,
  browserCookieSecure,
  SESSION_COOKIE
} from "../../../../lib/auth";
import { trustedLocalOrigin } from "../../../../lib/server-proxy";

export async function POST(request: Request): Promise<Response> {
  if (!trustedLocalOrigin(request)) {
    return Response.json({ detail: "forbidden" }, { status: 403 });
  }
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  const configuration = authConfiguration();
  if (token) {
    if (!configuration) {
      return Response.json(
        { detail: "authentication service unavailable" },
        { status: 503 }
      );
    }
    try {
      const upstream = await fetch(`${configuration.baseUrl}/v1/auth/logout`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${configuration.apiToken}`,
          "X-Panshi-Session": token
        },
        cache: "no-store"
      });
      if (!upstream.ok) {
        return Response.json(
          { detail: "authentication service unavailable" },
          { status: 503 }
        );
      }
    } catch {
      return Response.json(
        { detail: "authentication service unavailable" },
        { status: 503 }
      );
    }
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: browserCookieSecure(),
    path: "/",
    expires: new Date(0)
  });
  return response;
}
