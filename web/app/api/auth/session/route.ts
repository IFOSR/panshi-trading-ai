import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  browserCookieSecure,
  SESSION_COOKIE,
  validateSessionToken
} from "../../../../lib/auth";

export async function GET(): Promise<Response> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) {
    return Response.json(
      { detail: "authentication required" },
      { status: 401 }
    );
  }
  const result = await validateSessionToken(token);
  if (result.status === "unavailable") {
    return Response.json(
      { detail: "authentication service unavailable" },
      { status: 503 }
    );
  }
  if (result.status === "invalid") {
    const response = NextResponse.json(
      { detail: "authentication required" },
      { status: 401 }
    );
    response.cookies.set(SESSION_COOKIE, "", {
      httpOnly: true,
      sameSite: "strict",
      secure: browserCookieSecure(),
      path: "/",
      expires: new Date(0)
    });
    return response;
  }
  return Response.json({
    username: result.username,
    expires_at: result.expiresAt
  });
}
