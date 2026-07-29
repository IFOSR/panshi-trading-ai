"use client";

import { useRouter } from "next/navigation";
import {
  useEffect,
  useId,
  useRef,
  useState
} from "react";

import type { StrategyManifest } from "../lib/api";

function valueOf(strategy: StrategyManifest): string {
  return `${strategy.strategyId}@${strategy.version}`;
}

function statusLabel(status: StrategyManifest["status"]): string {
  return {
    stable: "稳定版",
    test: "测试版",
    disabled: "已停用"
  }[status];
}

export function StrategySelector({
  strategies,
  value,
  caseId,
  disabled,
  onSelected
}: {
  strategies: StrategyManifest[];
  value: string;
  caseId?: string;
  disabled?: boolean;
  onSelected?: (strategy: StrategyManifest) => void;
}) {
  const router = useRouter();
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [selected, setSelected] = useState(value);
  const [open, setOpen] = useState(false);
  const [changing, setChanging] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const current = (
    strategies.find((strategy) => valueOf(strategy) === selected)
    ?? strategies[0]
  );

  useEffect(() => {
    setSelected(value);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (
        event.target instanceof Node
        && !rootRef.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener(
      "pointerdown",
      closeOnOutsideClick
    );
  }, [open]);

  function focusOption(index: number) {
    const bounded = Math.max(0, Math.min(index, strategies.length - 1));
    setActiveIndex(bounded);
    requestAnimationFrame(() => optionRefs.current[bounded]?.focus());
  }

  function openList() {
    if (disabled || changing || strategies.length === 0) return;
    const currentIndex = Math.max(
      0,
      strategies.findIndex((strategy) => valueOf(strategy) === selected)
    );
    setActiveIndex(currentIndex);
    setOpen(true);
  }

  function closeList() {
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  }

  async function choose(strategy: StrategyManifest) {
    const nextValue = valueOf(strategy);
    if (nextValue === selected) {
      closeList();
      return;
    }
    const previousValue = selected;
    setSelected(nextValue);
    setOpen(false);
    setError(null);
    if (!caseId) {
      onSelected?.(strategy);
      triggerRef.current?.focus();
      return;
    }
    setChanging(true);
    try {
      const response = await fetch(
        `/api/cases/${encodeURIComponent(caseId)}/strategy`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID()
          },
          body: JSON.stringify({
            strategy_id: strategy.strategyId,
            version: strategy.version
          })
        }
      );
      if (!response.ok) {
        const payload = await response.json() as { detail?: string };
        throw new Error(payload.detail ?? `策略服务返回 ${response.status}`);
      }
      onSelected?.(strategy);
      router.refresh();
    } catch (requestError) {
      setSelected(previousValue);
      setError(
        requestError instanceof Error ? requestError.message : "策略切换失败。"
      );
    } finally {
      setChanging(false);
      requestAnimationFrame(() => triggerRef.current?.focus());
    }
  }

  return (
    <div className="strategy-selector" ref={rootRef}>
      <span>分析策略</span>
      <button
        aria-controls={listboxId}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={
          current
            ? `分析策略：${current.displayName} v${current.version}`
            : "分析策略"
        }
        className="strategy-selector__trigger"
        disabled={disabled || changing || !current}
        onClick={() => open ? closeList() : openList()}
        onKeyDown={(event) => {
          if (event.key === "Escape" && open) {
            event.preventDefault();
            closeList();
          } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            openList();
            focusOption(
              event.key === "ArrowDown" ? activeIndex : strategies.length - 1
            );
          }
        }}
        ref={triggerRef}
        type="button"
      >
        <span>
          <strong>{current?.displayName ?? "暂无可用策略"}</strong>
          {current ? (
            <small>
              v{current.version} · {statusLabel(current.status)}
            </small>
          ) : null}
        </span>
        <b aria-hidden="true">{changing ? "…" : open ? "↑" : "↓"}</b>
      </button>
      {open ? (
        <div
          aria-label="分析策略"
          className="strategy-selector__list"
          id={listboxId}
          role="listbox"
        >
          {strategies.map((strategy, index) => {
            const strategyValue = valueOf(strategy);
            const isSelected = strategyValue === selected;
            return (
              <button
                aria-selected={isSelected}
                className={isSelected ? "is-selected" : ""}
                key={strategyValue}
                onClick={() => void choose(strategy)}
                onFocus={() => setActiveIndex(index)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    closeList();
                  } else if (event.key === "ArrowDown") {
                    event.preventDefault();
                    focusOption((index + 1) % strategies.length);
                  } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    focusOption(
                      (index - 1 + strategies.length) % strategies.length
                    );
                  }
                }}
                ref={(node) => {
                  optionRefs.current[index] = node;
                }}
                role="option"
                tabIndex={index === activeIndex ? 0 : -1}
                type="button"
              >
                <span>
                  <strong>{strategy.displayName}</strong>
                  <small>
                    v{strategy.version} · {statusLabel(strategy.status)}
                  </small>
                </span>
                <b aria-hidden="true">{isSelected ? "✓" : ""}</b>
              </button>
            );
          })}
        </div>
      ) : null}
      {error ? <small className="strategy-selector__error">{error}</small> : null}
    </div>
  );
}
