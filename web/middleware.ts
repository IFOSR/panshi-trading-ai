import { NextRequest, NextResponse } from "next/server";

/**
 * 本地访问中间件（已取消登录强制）：
 * - 仅保留 loopback 来源检查（127.0.0.1 / localhost / panshi.localhost）
 * - 不再校验会话，所有请求直接放行
 */
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
  const loopback = [
    "127.0.0.1",
    "localhost",
    "panshi.localhost",
    "::1",
    "[::1]"
  ];
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
