"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

export function LoginForm({ nextPath }: { nextPath: string }) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          next: nextPath
        })
      });
      if (response.status === 401) {
        setError("用户名或密码不正确。");
        return;
      }
      if (!response.ok) {
        setError("认证服务暂时不可用，请稍后重试。");
        return;
      }
      const payload = await response.json() as { next: string };
      router.replace(payload.next);
      router.refresh();
    } catch {
      setError("认证服务暂时不可用，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="login-form" onSubmit={(event) => void submit(event)}>
      <label>
        <span>用户名</span>
        <input
          autoComplete="username"
          autoFocus
          onChange={(event) => setUsername(event.target.value)}
          required
          value={username}
        />
      </label>
      <label>
        <span>密码</span>
        <input
          autoComplete="current-password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <button disabled={!hydrated || submitting} type="submit">
        {submitting ? "正在验证" : hydrated ? "登录" : "正在载入"}
      </button>
    </form>
  );
}
