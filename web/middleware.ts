import { NextRequest, NextResponse } from "next/server";

import {
  SESSION_COOKIE,
  validateSessionToken
} from "./lib/auth";

const PUBLIC_PATHS = new Set([
  "/login",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/session"
]);

export async function middleware(request: NextRequest): Promise<NextResponse> {
  const suppliedHost = request.headers.get("host");
  let headerHostname = "";
  try {
    headerHostname = suppliedHost
      ? new URL(`http://${suppliedHost}`).hostname
      : "";
  } catch {
    headerHostname = "";
  }
  const loopback = ["127.0.0.1", "localhost", "::1", "[::1]"];
  if (
    !loopback.includes(request.nextUrl.hostname)
    || !loopback.includes(headerHostname)
  ) {
    return new NextResponse("Local access only", {
      status: 403,
      headers: { "Cache-Control": "no-store" }
    });
  }
  if (PUBLIC_PATHS.has(request.nextUrl.pathname)) {
    return NextResponse.next();
  }
  const apiRequest = request.nextUrl.pathname.startsWith("/api/");
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    if (apiRequest) {
      return NextResponse.json(
        { detail: "authentication required" },
        { status: 401 }
      );
    }
    const login = new URL("/login", request.url);
    login.searchParams.set(
      "next",
      `${request.nextUrl.pathname}${request.nextUrl.search}`
    );
    return NextResponse.redirect(login);
  }
  const session = await validateSessionToken(token);
  if (session.status === "valid") return NextResponse.next();
  if (apiRequest) {
    return NextResponse.json(
      {
        detail: session.status === "unavailable"
          ? "authentication service unavailable"
          : "authentication required"
      },
      { status: session.status === "unavailable" ? 503 : 401 }
    );
  }
  const login = new URL("/login", request.url);
  login.searchParams.set(
    "next",
    `${request.nextUrl.pathname}${request.nextUrl.search}`
  );
  if (session.status === "unavailable") {
    login.searchParams.set("service", "unavailable");
  }
  const response = NextResponse.redirect(login);
  if (session.status === "invalid") response.cookies.delete(SESSION_COOKIE);
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|icon.svg|favicon.ico).*)"
  ]
};
