"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { StrategyStoreDetail, UserEntitlement } from "../lib/api";
import { createOrder, formatPriceYuan, markOrderPaid } from "../lib/api";

export function PurchasePanel({
  detail,
  entitlement
}: {
  detail: StrategyStoreDetail;
  entitlement: UserEntitlement | null;
}) {
  const router = useRouter();
  const [period, setPeriod] = useState<"monthly" | "yearly" | "lifetime">("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pricing = detail.pricing;

  if (!pricing || pricing.type === "free") {
    return <div className="purchase-panel"><strong>免费策略</strong></div>;
  }

  if (entitlement && entitlement.status === "active") {
    return (
      <div className="purchase-panel purchase-panel--owned">
        <strong>已购买</strong>
        <p>
          授权类型：{entitlement.access_type === "onetime" ? "永久" : "订阅"}
          {entitlement.expires_at ? `，到期时间 ${new Date(entitlement.expires_at).toLocaleDateString("zh-CN")}` : null}
        </p>
        <button onClick={() => router.push("/")} type="button">
          去使用
        </button>
      </div>
    );
  }

  const selectedPrice =
    period === "lifetime"
      ? pricing.lifetime_price
      : period === "yearly"
        ? pricing.yearly_price
        : pricing.monthly_price;

  async function buy() {
    if (busy || selectedPrice === null) return;
    setBusy(true);
    setError(null);
    const order = await createOrder(
      detail.strategy_id,
      detail.version,
      period === "lifetime" ? "onetime" : "subscription",
      period === "lifetime" ? undefined : period
    );
    if (!order) {
      setBusy(false);
      setError("创建订单失败，请稍后重试。");
      return;
    }
    // Mock payment flow: immediately mark paid for demo.
    const paid = await markOrderPaid(order.order_id);
    setBusy(false);
    if (!paid) {
      setError("支付处理失败，请稍后重试。");
      return;
    }
    router.refresh();
  }

  return (
    <div className="purchase-panel">
      <strong>选择方案</strong>
      <div className="purchase-options">
        {pricing.type !== "onetime" ? (
          <>
            <label className={period === "monthly" ? "is-selected" : ""}>
              <input
                checked={period === "monthly"}
                name="purchase-period"
                onChange={() => setPeriod("monthly")}
                type="radio"
              />
              <span>月度订阅</span>
              <b>{formatPriceYuan(pricing.monthly_price)}</b>
            </label>
            <label className={period === "yearly" ? "is-selected" : ""}>
              <input
                checked={period === "yearly"}
                name="purchase-period"
                onChange={() => setPeriod("yearly")}
                type="radio"
              />
              <span>年度订阅</span>
              <b>{formatPriceYuan(pricing.yearly_price)}</b>
            </label>
          </>
        ) : null}
        {pricing.type === "onetime" || pricing.lifetime_price ? (
          <label className={period === "lifetime" ? "is-selected" : ""}>
            <input
              checked={period === "lifetime"}
              name="purchase-period"
              onChange={() => setPeriod("lifetime")}
              type="radio"
            />
            <span>{pricing.type === "onetime" ? "单次购买" : "永久购买"}</span>
            <b>{formatPriceYuan(pricing.lifetime_price ?? pricing.monthly_price)}</b>
          </label>
        ) : null}
      </div>
      <button disabled={busy || selectedPrice === null} onClick={() => void buy()} type="button">
        {busy ? "处理中…" : `立即购买 ${selectedPrice !== null ? formatPriceYuan(selectedPrice) : ""}`}
      </button>
      {error ? <p className="purchase-error">{error}</p> : null}
      <p className="purchase-tip">当前为演示支付，点击后立即开通使用权。</p>
    </div>
  );
}
