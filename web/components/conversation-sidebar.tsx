"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { ConversationSummary } from "../lib/api";

const FOCUS_NEW_CHAT_KEY = "panshi.focusNewChatAfterDeletion";

type PendingDeletion = {
  type: "one";
  caseId: string;
  label: string;
} | {
  type: "all";
};

export function ConversationSidebar({
  conversations,
  activeCaseId
}: {
  conversations: ConversationSummary[];
  activeCaseId?: string;
}) {
  const router = useRouter();
  const [items, setItems] = useState(conversations);
  const [pending, setPending] = useState<PendingDeletion | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const openerRef = useRef<HTMLButtonElement | null>(null);
  const fallbackFocusRef = useRef<HTMLElement | null>(null);
  const newChatRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    setItems(conversations);
  }, [conversations]);

  useEffect(() => {
    if (sessionStorage.getItem(FOCUS_NEW_CHAT_KEY) !== "true") return;
    sessionStorage.removeItem(FOCUS_NEW_CHAT_KEY);
    requestAnimationFrame(() => newChatRef.current?.focus());
  }, [activeCaseId]);

  useEffect(() => {
    if (!pending) return;
    const handleDialogKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (deleting) return;
        event.preventDefault();
        closeDeletionDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      const buttons = dialog
        ? Array.from(
            dialog.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")
          )
        : [];
      if (buttons.length === 0) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog?.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialog?.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleDialogKey);
    return () => document.removeEventListener("keydown", handleDialogKey);
  }, [deleting, pending]);

  useEffect(() => {
    if (pending && deleting) dialogRef.current?.focus();
  }, [deleting, pending]);

  function openDeletionDialog(
    next: PendingDeletion,
    opener: HTMLButtonElement
  ) {
    openerRef.current = opener;
    const row = opener.closest(".conversation-item");
    fallbackFocusRef.current = (
      row?.nextElementSibling?.querySelector<HTMLButtonElement>("button")
      ?? row?.previousElementSibling?.querySelector<HTMLButtonElement>("button")
      ?? newChatRef.current
    );
    setError(null);
    setPending(next);
  }

  function closeDeletionDialog() {
    setPending(null);
    requestAnimationFrame(() => {
      const target = openerRef.current?.isConnected
        ? openerRef.current
        : fallbackFocusRef.current?.isConnected
          ? fallbackFocusRef.current
          : newChatRef.current;
      target?.focus();
    });
  }

  async function confirmDeletion() {
    if (!pending || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      const endpoint = pending.type === "all"
        ? "/api/cases"
        : `/api/cases/${encodeURIComponent(pending.caseId)}`;
      const response = await fetch(endpoint, { method: "DELETE" });
      if (!response.ok) throw new Error(`delete failed: ${response.status}`);
      if (pending.type === "all") {
        setItems([]);
      } else {
        setItems((current) => current.filter(
          (item) => item.caseId !== pending.caseId
        ));
      }
      const deletingActive = (
        pending.type === "all"
          ? Boolean(activeCaseId)
          : pending.caseId === activeCaseId
      );
      closeDeletionDialog();
      if (deletingActive) {
        sessionStorage.setItem(FOCUS_NEW_CHAT_KEY, "true");
        router.push("/");
      } else {
        router.refresh();
      }
    } catch {
      closeDeletionDialog();
      setError("永久删除失败，请稍后重试。");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <aside className="conversation-sidebar" data-testid="conversation-sidebar">
      <Link className="sidebar-brand" href="/">
        <strong>磐石交易AI</strong>
        <span>PANSHI TRADING AI</span>
      </Link>
      <Link className="new-chat" href="/" ref={newChatRef}>＋ 新建分析</Link>
      <div className="conversation-list">
        <div className="conversation-list__header">
          <p>最近对话</p>
          {items.length > 0 ? (
            <button
              aria-label="清空全部对话"
              disabled={deleting}
              onClick={(event) => {
                openDeletionDialog({ type: "all" }, event.currentTarget);
              }}
              type="button"
            >
              清空
            </button>
          ) : null}
        </div>
        {items.length > 0 ? items.map((item) => {
          const label = item.contract ?? item.instrument ?? "未识别合约";
          return (
            <article
              className={
                `conversation-item${
                  item.caseId === activeCaseId ? " is-active" : ""
                }`
              }
              key={item.caseId}
            >
              <Link href={`/cases/${item.caseId}`}>
                <strong>{label}</strong>
                <span>{item.action ?? "等待分析"} · {item.strategyName}</span>
              </Link>
              <button
                aria-label={`删除 ${label} 对话`}
                disabled={deleting}
                onClick={(event) => {
                  openDeletionDialog(
                    {
                      type: "one",
                      caseId: item.caseId,
                      label
                    },
                    event.currentTarget
                  );
                }}
                title={`永久删除 ${label} 对话`}
                type="button"
              >
                ×
              </button>
            </article>
          );
        }) : (
          <small>还没有分析记录。</small>
        )}
        {error ? (
          <p className="conversation-list__error" role="alert">{error}</p>
        ) : null}
      </div>
      <footer>本地轻量模式 · 端口 8989</footer>
      {pending ? (
        <div className="delete-dialog-backdrop">
          <section
            aria-describedby="delete-dialog-description"
            aria-labelledby="delete-dialog-title"
            aria-modal="true"
            className="delete-dialog"
            ref={dialogRef}
            role="alertdialog"
            tabIndex={-1}
          >
            <span>永久删除</span>
            <h2 id="delete-dialog-title">
              {pending.type === "all" ? "清空全部对话？" : `删除 ${pending.label}？`}
            </h2>
            <p id="delete-dialog-description">
              {pending.type === "all"
                ? `将永久删除 ${items.length} 条对话及其全部截图、分析结果，无法恢复。`
                : "将永久删除此对话及相关截图、分析结果，无法恢复。"}
            </p>
            <div>
              <button
                autoFocus
                disabled={deleting}
                onClick={closeDeletionDialog}
                type="button"
              >
                取消
              </button>
              <button
                className="is-destructive"
                disabled={deleting}
                onClick={() => void confirmDeletion()}
                type="button"
              >
                {deleting
                  ? "正在删除"
                  : pending.type === "all"
                    ? "全部永久删除"
                    : "永久删除"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </aside>
  );
}
