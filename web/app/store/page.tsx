import Link from "next/link";
import { StrategyStoreCard } from "../../components/strategy-store-card";
import { getStoreStrategies } from "../../lib/api";

export const dynamic = "force-dynamic";

export default async function StorePage() {
  const strategies = await getStoreStrategies();

  return (
    <main className="store-page">
      <header className="store-header">
        <div>
          <span>STRATEGY STORE</span>
          <h1>策略商店</h1>
          <p>浏览策略的最近三个月表现，选择适合你的策略购买使用。</p>
        </div>
        <Link className="store-header__my" href="/my-strategies">我的策略</Link>
      </header>
      {strategies.length === 0 ? (
        <section className="store-empty">
          <p>暂无可用策略。</p>
        </section>
      ) : (
        <section className="store-grid">
          {strategies.map((strategy) => (
            <StrategyStoreCard key={strategy.strategy_id} strategy={strategy} />
          ))}
        </section>
      )}
    </main>
  );
}
