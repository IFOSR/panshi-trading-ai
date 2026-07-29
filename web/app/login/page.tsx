import { LoginForm } from "../../components/login-form";
import { safeNextPath } from "../../lib/auth";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams
}: {
  searchParams: Promise<{ next?: string; service?: string }>;
}) {
  const query = await searchParams;
  return (
    <main className="login-shell">
      <section className="login-mark">
        <span>PANSHI / AUTHENTICATION</span>
        <strong aria-hidden="true">磐</strong>
        <p>策略结论、关键里程碑与证据链，仅对已授权用户开放。</p>
      </section>
      <section className="login-panel">
        <header>
          <span>本地 SQLite 账户</span>
          <h1>登录磐石交易AI</h1>
          <p>登录后继续你的中国期货策略分析与历史对话。</p>
        </header>
        {query.service === "unavailable" ? (
          <p className="login-service-error" role="alert">
            认证服务暂时不可用，请确认本地 API 已启动。
          </p>
        ) : null}
        <LoginForm nextPath={safeNextPath(query.next)} />
        <footer>会话凭据仅保存在 HttpOnly Cookie 中。</footer>
      </section>
    </main>
  );
}
