import Link from "next/link";
import { EntitlementBadge } from "../../components/entitlement-badge";
import { getMyEntitlements, getStoreStrategies } from "../../lib/api";

export const dynamic = "force-dynamic";

export default async function MyStrategiesPage() {
  const [entitlements, strategies] = await Promise.all([
    getMyEntitlements(),
    getStoreStrategies()
  ]);

  const strategyMap = new Map(strategies.map((s) => [s.strategy_id, s]));

  return (
    <main className="my-strategies-page">
      <header className="my-strategies-header">
        <div>
          <span>MY STRATEGIES</span>
          <h1>我的策略</h1>
          <p>管理你已购买或免费的策略，续费订阅或去使用。</p>
        </div>
        <Link className="my-strategies-header__store" href="/store">去策略商店</Link>
      </header>
      {entitlements.length === 0 ? (
        <section className="my-strategies-empty">
          <p>你还没有任何策略授权。</p>
          <Link href="/store">去策略商店看看 →</Link>
        </section>
      ) : (
        <section className="my-strategies-list">
          {entitlements.map((entitlement) => {
            const strategy = strategyMap.get(entitlement.strategy_id);
            return (
              <article className="my-strategy-card" key={entitlement.entitlement_id}>
                <header>
                  <strong>{strategy?.display_name ?? entitlement.strategy_id}</strong>
                  <EntitlementBadge entitlement={entitlement} />
                </header>
                <p>版本：v{entitlement.version}</p>
                {entitlement.expires_at ? (
                  <p>到期时间：{new Date(entitlement.expires_at).toLocaleDateString("zh-CN")}</p>
                ) : null}
                <div className="my-strategy-card__actions">
                  <Link href="/">去使用</Link>
                  <Link href={`/store/${encodeURIComponent(entitlement.strategy_id)}`}>查看详情</Link>
                </div>
              </article>
            );
          })}
        </section>
      )}
    </main>
  );
}
