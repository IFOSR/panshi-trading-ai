import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest): NextResponse {
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
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|icon.svg|favicon.ico).*)"
  ]
};
