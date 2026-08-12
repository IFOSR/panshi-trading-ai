import Link from "next/link";
import { notFound } from "next/navigation";
import { EntitlementBadge } from "../../../components/entitlement-badge";
import { PurchasePanel } from "../../../components/purchase-panel";
import { StrategyPerformanceView } from "../../../components/strategy-performance-view";
import { checkEntitlement, getMyEntitlements, getStoreStrategyDetail } from "../../../lib/api";

export const dynamic = "force-dynamic";

export default async function StrategyDetailPage({
  params
}: {
  params: Promise<{ strategyId: string }>;
}) {
  const { strategyId } = await params;
  const detail = await getStoreStrategyDetail(strategyId);
  if (!detail) notFound();

  const [entitlements, accessCheck] = await Promise.all([
    getMyEntitlements(),
    checkEntitlement(strategyId, detail.version)
  ]);

  const entitlement = entitlements.find(
    (item) => item.strategy_id === strategyId && item.status === "active"
  ) ?? (accessCheck.accessible ? {
    entitlement_id: accessCheck.entitlement_id ?? "",
    strategy_id: strategyId,
    version: detail.version,
    access_type: accessCheck.access_type as "free" | "onetime" | "subscription",
    status: "active" as const,
    expires_at: accessCheck.expires_at
  } : null);

  const isFree = !detail.pricing || detail.pricing.type === "free";

  return (
    <main className="store-detail">
      <header className="store-detail__header">
        <div>
          <span>{detail.category ?? "策略"} · {detail.status === "stable" ? "稳定版" : "测试版"}</span>
          <h1>{detail.display_name}</h1>
          <p>{detail.description ?? "暂无策略介绍。"}</p>
          <small>
            适用市场：{detail.supported_markets.join("、")} · {" "}
            适用周期：{detail.supported_timeframes.join("、")}
          </small>
        </div>
        <EntitlementBadge entitlement={isFree ? {
          entitlement_id: "",
          strategy_id: detail.strategy_id,
          version: detail.version,
          access_type: "free",
          status: "active",
          expires_at: null
        } : entitlement} />
      </header>
      <div className="store-detail__body">
        <div className="store-detail__main">
          <StrategyPerformanceView detail={detail} />
        </div>
        <aside className="store-detail__sidebar">
          <PurchasePanel detail={detail} entitlement={entitlement} />
          {entitlement && entitlement.status === "active" ? (
            <Link
              className="store-detail__use"
              href="/"
            >
              使用此策略开始分析 →
            </Link>
          ) : null}
          {!isFree && !entitlement ? (
            <p className="store-detail__notice">
              购买后即可在分析界面使用该策略。
            </p>
          ) : null}
        </aside>
      </div>
      <footer className="store-detail__footer">
        <Link href="/store">← 返回策略商店</Link>
      </footer>
    </main>
  );
}
