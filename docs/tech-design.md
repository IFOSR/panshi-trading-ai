# 磐石交易AI 技术设计方案

> 对应 PRD：`docs/PRD.md` v2.1  
> 状态：草稿，待评审  
> 范围：后端、前端、数据、策略运行时

---

## 1. 设计目标

基于 PRD v2.1 中定义的策略商店 + 策略化预测分析助手定位，技术设计需要实现以下目标：

1. **策略商品化**：策略可以上架、定价、购买、授权使用。
2. **表现透明化**：每个策略展示最近三个月的表现数据。
3. **购买驱动分析**：只有已购买/免费的策略才能在对话中使用。
4. **自然语言交互**：用户通过对话完成策略选择、标的指定、信息补充、结果追问。
5. **策略可扩展**：新策略通过标准接口接入，不修改核心系统。
6. **与现有系统兼容**：尽量复用现有的 FastAPI、数据库、策略运行时、对话流程。

---

## 2. 设计原则

### 2.1 最小侵入

- 尽量复用现有 `Case`、`Analysis`、`StrategyPlugin` 等模型和流程。
- 新增策略商店、授权、订单、表现跟踪模块，不破坏现有分析流程。

### 2.2 策略与商业化解耦

- 策略插件只负责分析逻辑和表现计算。
- 商业化逻辑（价格、购买、订阅）由独立模块处理。
- 策略运行时不感知用户是否付费，只校验调用方是否传入有效授权。

### 2.3 表现数据预计算

- 最近三个月表现数据每日预计算并缓存。
- 前端展示时直接读取预计算结果，避免实时计算带来的延迟。

### 2.4 数据一致性

- 授权、订单、用户策略库使用关系型数据库事务保证一致性。
- 分析版本保持不可变，购买状态变化不影响历史分析。

### 2.5 可审计

- 所有购买记录、授权变更、策略表现数据保存审计日志。
- 每次分析记录策略版本、授权状态、数据时间。

---

## 3. 总体架构

### 3.1 逻辑架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Next.js Web 前端                            │
│  策略商店  │  策略详情  │  我的策略  │  对话界面  │  可视化展示      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI API 层                              │
│  商店路由  │  授权路由  │  订单路由  │  分析路由  │  会话路由        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌─────────────────┐  ┌─────────────────────┐  ┌──────────────────┐
│  策略商店服务    │  │  用户授权服务        │  │  策略表现跟踪服务 │
│  StrategyStore  │  │  StrategyEntitlement│  │  PerformanceTracker│
└─────────────────┘  └─────────────────────┘  └──────────────────┘
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐  ┌─────────────────────┐  ┌──────────────────┐
│  订单/支付服务   │  │  策略运行时          │  │  数据能力平台     │
│  OrderService   │  │  StrategyRuntime    │  │  DataPlatform    │
└─────────────────┘  └─────────────────────┘  └──────────────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │     SQLite / PostgreSQL        │
                  │  策略 │ 授权 │ 订单 │ 表现 │ 会话 │
                  └───────────────────────────────┘
```

### 3.2 与现有架构的关系

- 现有 `FastAPI`、`CaseRepository`、`AnalysisWorkflow` 继续保留。
- 新增 `StrategyStore`、`EntitlementService`、`OrderService`、`PerformanceTracker` 模块。
- 在 `api/app.py` 的分析入口增加授权检查。
- 在 `StrategyManifest` 中增加商业化字段和表现配置。

---

## 4. 数据模型设计

### 4.1 新增数据库表

#### 4.1.1 策略表（strategies）

| 字段 | 类型 | 说明 |
|---|---|---|
| strategy_id | String(80), PK | 策略唯一标识 |
| display_name | String(120) | 展示名称 |
| description | Text | 策略描述 |
| category | String(40) | 分类：趋势/反转/事件驱动等 |
| supported_markets | JSON | 适用市场列表 |
| supported_timeframes | JSON | 适用周期列表 |
| status | String(20) | stable / test / disabled |
| entrypoint | String(240) | 策略入口类路径 |
| input_schema_version | String(40) | 输入Schema版本 |
| output_schema_version | String(40) | 输出Schema版本 |
| risk_profile_id | String(120) | 风险模型ID |
| process_label | String(120) | 流程标签 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 4.1.2 策略版本表（strategy_versions）

| 字段 | 类型 | 说明 |
|---|---|---|
| version_id | String(120), PK | strategy_id@version |
| strategy_id | String(80), FK | 策略ID |
| version | String(20) | 版本号 |
| manifest | JSON | 完整策略清单 |
| pricing_type | String(20) | free / onetime / subscription |
| monthly_price | Integer | 月订阅价格（分） |
| yearly_price | Integer | 年订阅价格（分） |
| lifetime_price | Integer | 单次购买价格（分） |
| status | String(20) | stable / test / disabled |
| released_at | DateTime | 发布时间 |
| created_at | DateTime | 创建时间 |

#### 4.1.3 用户授权表（user_entitlements）

| 字段 | 类型 | 说明 |
|---|---|---|
| entitlement_id | String(36), PK | 授权记录ID |
| user_id | String(36), FK | 用户ID |
| strategy_id | String(80) | 策略ID |
| version | String(20) | 授权版本 |
| access_type | String(20) | free / onetime / subscription |
| status | String(20) | active / expired / revoked |
| started_at | DateTime | 授权开始时间 |
| expires_at | DateTime | 授权过期时间（单次购买为NULL） |
| order_id | String(36), FK | 关联订单 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 4.1.4 订单表（orders）

| 字段 | 类型 | 说明 |
|---|---|---|
| order_id | String(36), PK | 订单ID |
| user_id | String(36), FK | 用户ID |
| strategy_id | String(80) | 策略ID |
| version | String(20) | 策略版本 |
| pricing_type | String(20) | onetime / subscription |
| subscription_period | String(20) | monthly / yearly / NULL |
| amount | Integer | 支付金额（分） |
| currency | String(10) | 货币 |
| status | String(20) | pending / paid / refunded / cancelled |
| paid_at | DateTime | 支付时间 |
| expires_at | DateTime | 订阅过期时间 |
| refund_reason | String | 退款原因 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 4.1.5 策略表现记录表（strategy_performance_signals）

| 字段 | 类型 | 说明 |
|---|---|---|
| signal_id | String(36), PK | 信号ID |
| strategy_id | String(80) | 策略ID |
| version | String(20) | 策略版本 |
| contract | String(80) | 标的 |
| signal_date | Date | 信号日期 |
| direction | String(20) | LONG / SHORT / FLAT / WAIT |
| entry_price | Float | 入场价格 |
| exit_price | Float | 出场价格 |
| return_pct | Float | 本次信号收益率 |
| status | String(20) | open / closed |
| closed_date | Date | 平仓日期 |
| evidence | JSON | 信号依据摘要 |
| created_at | DateTime | 创建时间 |

#### 4.1.6 策略表现汇总表（strategy_performance_summaries）

| 字段 | 类型 | 说明 |
|---|---|---|
| summary_id | String(120), PK | strategy_id@version@period |
| strategy_id | String(80) | 策略ID |
| version | String(20) | 策略版本 |
| period | String(20) | 统计周期，如 last_3_months |
| start_date | Date | 统计开始日期 |
| end_date | Date | 统计结束日期 |
| total_return | Float | 累计收益率 |
| annualized_return | Float | 年化收益率 |
| max_drawdown | Float | 最大回撤 |
| signal_count | Integer | 信号次数 |
| win_count | Integer | 盈利次数 |
| loss_count | Integer | 亏损次数 |
| win_rate | Float | 胜率 |
| avg_win | Float | 平均盈利 |
| avg_loss | Float | 平均亏损 |
| equity_curve | JSON | 权益曲线数据 |
| updated_at | DateTime | 更新时间 |

### 4.2 扩展现有表

#### 4.2.1 cases 表扩展

在 `state` JSON 中增加：

```json
{
  "user_id": "...",
  "entitlement_check": {
    "strategy_id": "...",
    "version": "...",
    "entitlement_id": "...",
    "checked_at": "..."
  }
}
```

#### 4.2.2 analyses 表扩展

在 `payload` JSON 中增加：

```json
{
  "entitlement_info": {
    "strategy_id": "...",
    "version": "...",
    "entitlement_id": "..."
  }
}
```

### 4.3 数据库迁移

使用 Alembic 新增迁移脚本，创建上述表。`alembic/env.py` 已经配置 `target_metadata = Base.metadata`，只需在 `db/models.py` 中定义新模型并运行 `alembic revision --autogenerate`。

---

## 5. 模块设计

### 5.1 策略商店服务（StrategyStoreService）

**职责**：

- 查询策略列表和详情。
- 管理策略上下架状态。
- 返回策略卡片和详情页所需数据（含最近三个月表现）。

**接口**：

```python
class StrategyStoreService:
    def list_strategies(
        self,
        *,
        category: str | None = None,
        market: str | None = None,
        sort_by: str = "recent_return",
        limit: int = 50,
    ) -> list[StrategyCard]: ...

    def get_strategy_detail(self, strategy_id: str, version: str | None = None) -> StrategyDetail: ...

    def get_recent_performance(self, strategy_id: str, version: str) -> PerformanceSummary: ...
```

### 5.2 用户授权服务（EntitlementService）

**职责**：

- 检查用户是否拥有某策略的使用权。
- 管理用户授权记录。
- 处理订阅到期检查。

**接口**：

```python
class EntitlementService:
    def check_access(
        self,
        user_id: str,
        strategy_id: str,
        version: str | None = None,
    ) -> EntitlementResult: ...

    def grant_access(
        self,
        user_id: str,
        strategy_id: str,
        version: str,
        access_type: str,
        order_id: str,
        expires_at: datetime | None = None,
    ) -> UserEntitlement: ...

    def list_user_entitlements(self, user_id: str) -> list[UserEntitlement]: ...

    def expire_overdue_entitlements(self) -> int: ...
```

### 5.3 订单/支付服务（OrderService）

**职责**：

- 创建订单。
- 处理支付回调。
- 支付成功后调用授权服务开通权限。
- 处理退款。

**接口**：

```python
class OrderService:
    def create_order(
        self,
        user_id: str,
        strategy_id: str,
        version: str,
        pricing_type: str,
        subscription_period: str | None = None,
    ) -> Order: ...

    def mark_paid(self, order_id: str, payment_id: str) -> Order: ...

    def refund(self, order_id: str, reason: str) -> Order: ...

    def list_orders(self, user_id: str) -> list[Order]: ...
```

### 5.4 策略表现跟踪服务（PerformanceTracker）

**职责**：

- 每日运行策略，生成最近三个月的信号记录。
- 计算表现汇总指标。
- 更新 `strategy_performance_summaries` 表。

**接口**：

```python
class PerformanceTracker:
    def track_strategy(
        self,
        strategy_id: str,
        version: str,
        start_date: date,
        end_date: date,
    ) -> PerformanceSummary: ...

    def update_all_strategies(self) -> None: ...

    def get_summary(
        self,
        strategy_id: str,
        version: str,
        period: str = "last_3_months",
    ) -> PerformanceSummary | None: ...
```

### 5.5 策略运行时（StrategyRuntime）

**职责**：

- 加载策略插件。
- 调用 `evaluate()` 生成分析结果。
- 调用 `track_performance()` 生成表现数据。

**接口**：

```python
class StrategyRuntime:
    def evaluate(
        self,
        strategy_id: str,
        version: str | None,
        snapshot: StrategyInputSnapshot,
    ) -> StrategyRun: ...

    def track_performance(
        self,
        strategy_id: str,
        version: str,
        start_date: date,
        end_date: date,
    ) -> PerformanceTrack: ...
```

### 5.6 信息抽取引擎（FactExtractor）

**职责**：

- 根据策略的 `required_facts` 声明，从对话和附件中抽取信息。
- 判断缺失字段。
- 生成澄清问题。

**接口**：

```python
class FactExtractor:
    def extract_facts(
        self,
        strategy_id: str,
        version: str,
        conversation: list[dict],
        attachments: list[dict],
    ) -> FactExtractionResult: ...

    def build_clarification_questions(
        self,
        required_facts: list[FactRequirement],
        extracted_facts: dict,
    ) -> list[ClarificationQuestion]: ...
```

### 5.7 对话引擎（ConversationEngine）

**职责**：

- 维护会话状态。
- 理解用户意图。
- 调度信息抽取、策略运行、结果渲染。

**接口**：

```python
class ConversationEngine:
    def process_message(
        self,
        case_id: str,
        user_id: str,
        message: str,
        attachments: list[dict],
    ) -> ConversationResponse: ...
```

---

## 6. API 设计

### 6.1 策略商店 API

#### 6.1.1 获取策略列表

```http
GET /v1/store/strategies
```

查询参数：

- `category`：策略分类
- `market`：适用市场
- `sort_by`：`recent_return` | `win_rate` | `price`
- `limit`：数量

响应：

```json
{
  "strategies": [
    {
      "strategy_id": "trend_breakout",
      "version": "1.0.0",
      "display_name": "趋势突破策略",
      "category": "趋势",
      "supported_markets": ["CN_FUTURES"],
      "supported_timeframes": ["1d", "60m"],
      "pricing": {
        "type": "subscription",
        "monthly_price": 9900,
        "yearly_price": 89900
      },
      "recent_performance": {
        "period": "近3个月",
        "total_return": 0.125,
        "signal_count": 24,
        "win_rate": 0.625,
        "max_drawdown": 0.051
      }
    }
  ]
}
```

#### 6.1.2 获取策略详情

```http
GET /v1/store/strategies/:strategy_id
```

查询参数：

- `version`：版本号，不传则使用最新稳定版

响应：

```json
{
  "strategy_id": "trend_breakout",
  "version": "1.0.0",
  "display_name": "趋势突破策略",
  "description": "...",
  "category": "趋势",
  "pricing": {...},
  "recent_performance": {
    "period": "近3个月",
    "start_date": "2025-05-12",
    "end_date": "2025-08-12",
    "total_return": 0.125,
    "annualized_return": 0.52,
    "signal_count": 24,
    "win_count": 15,
    "loss_count": 9,
    "win_rate": 0.625,
    "max_drawdown": 0.051,
    "equity_curve": [...],
    "signals": [...]
  }
}
```

### 6.2 授权 API

#### 6.2.1 获取我的策略

```http
GET /v1/entitlements
```

响应：

```json
{
  "entitlements": [
    {
      "entitlement_id": "...",
      "strategy_id": "trend_breakout",
      "version": "1.0.0",
      "display_name": "趋势突破策略",
      "access_type": "subscription",
      "status": "active",
      "expires_at": "2026-08-12T00:00:00Z"
    }
  ]
}
```

#### 6.2.2 检查策略访问权限

```http
GET /v1/entitlements/:strategy_id/check?version=1.0.0
```

响应：

```json
{
  "accessible": true,
  "entitlement_id": "...",
  "access_type": "subscription",
  "expires_at": "2026-08-12T00:00:00Z"
}
```

### 6.3 订单 API

#### 6.3.1 创建订单

```http
POST /v1/orders
```

请求体：

```json
{
  "strategy_id": "trend_breakout",
  "version": "1.0.0",
  "pricing_type": "subscription",
  "subscription_period": "monthly"
}
```

响应：

```json
{
  "order_id": "...",
  "status": "pending",
  "amount": 9900,
  "currency": "CNY",
  "payment_url": "https://..."
}
```

#### 6.3.2 支付回调

```http
POST /v1/orders/:order_id/paid
```

请求体：

```json
{
  "payment_id": "...",
  "paid_at": "2025-08-12T10:00:00Z"
}
```

### 6.4 对话/分析 API（改造现有接口）

#### 6.4.1 创建会话

现有 `POST /v1/cases` 增加 `user_id` 绑定和策略授权检查。

#### 6.4.2 选择策略

现有 `POST /v1/cases/:case_id/strategy` 增加授权检查：

- 如果用户未购买该策略，返回 `402 Payment Required` 或 `403 Forbidden`。
- 如果策略已过期，提示续费。

#### 6.4.3 发送消息

现有 `POST /v1/cases/:case_id/messages` 保持逻辑，但在运行策略前校验授权。

### 6.5 表现跟踪 API（内部）

#### 6.5.1 触发策略表现更新

```http
POST /v1/admin/performance/update
```

由定时任务调用，无需用户鉴权（使用 admin token）。

---

## 7. 关键流程设计

### 7.1 策略上架流程

```text
1. 策略开发者在 src/trading_agent/strategies/ 下实现策略
2. 策略实现 track_performance() 方法
3. 在 configured_strategy_registry() 中注册策略
4. 系统在 strategies 表和 strategy_versions 表中插入记录
5. PerformanceTracker 运行策略，生成最近三个月表现数据
6. 策略状态设置为 stable，上架策略商店
```

### 7.2 用户购买流程

```text
1. 用户浏览策略商店
2. 查看策略详情和最近三个月表现
3. 点击购买/订阅
4. OrderService 创建订单
5. 用户完成支付
6. 支付回调触发 OrderService.mark_paid()
7. OrderService 调用 EntitlementService.grant_access()
8. 用户在「我的策略」中看到已购买的策略
```

### 7.3 策略表现每日更新流程

```text
1. 定时任务（每天收盘后）调用 PerformanceTracker.update_all_strategies()
2. 对每个 stable 策略：
   a. 计算最近三个月时间范围
   b. 调用策略的 track_performance() 方法
   c. 保存信号记录到 strategy_performance_signals
   d. 计算汇总指标
   e. 更新 strategy_performance_summaries
3. 前端展示时直接读取汇总表
```

### 7.4 分析流程（改造后）

```text
1. 用户发起分析请求
2. 系统识别策略、标的、时间范围
3. EntitlementService 检查用户是否有策略使用权
   - 无权限：提示去商店购买
   - 有权限：继续
4. FactExtractor 根据策略 required_facts 抽取信息
5. 如有缺失信息，生成澄清问题返回给用户
6. 信息完整后，从 DataPlatform 获取数据
7. StrategyRuntime 调用策略 evaluate() 方法
8. 渲染结果：自然语言 + 可视化
9. 保存分析版本，记录授权信息
```

---

## 8. 与现有代码集成

### 8.1 需要新增的文件

```text
src/trading_agent/
├── store/
│   ├── __init__.py
│   ├── service.py          # StrategyStoreService
│   ├── models.py           # 商店相关 Pydantic 模型
│   └── repository.py       # 策略商店数据访问
├── entitlement/
│   ├── __init__.py
│   ├── service.py          # EntitlementService
│   ├── models.py
│   └── repository.py
├── order/
│   ├── __init__.py
│   ├── service.py          # OrderService
│   ├── models.py
│   └── repository.py
├── performance/
│   ├── __init__.py
│   ├── tracker.py          # PerformanceTracker
│   ├── models.py
│   └── repository.py
└── db/
    └── models.py           # 新增 StrategyRecord 等模型
```

### 8.2 需要修改的文件

```text
src/trading_agent/
├── strategies/contracts.py        # StrategyManifest 增加商业化字段
├── strategies/registry.py         # 保持不变，继续手动注册
├── api/app.py                     # 增加商店/授权/订单路由，分析入口增加授权检查
├── config.py                      # 增加商店/支付相关配置
└── db/models.py                   # 新增模型
```

### 8.3 策略契约扩展

在 `src/trading_agent/strategies/contracts.py` 中扩展：

```python
class StrategyManifest(BaseModel):
    # 原有字段...
    pricing: StrategyPricing | None = None
    performance_config: PerformanceConfig | None = None


class StrategyPlugin(Protocol):
    manifest: StrategyManifest

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun: ...

    def track_performance(
        self,
        start_date: date,
        end_date: date,
        market_data: MarketDataBundle,
    ) -> PerformanceTrack: ...
```

### 8.4 现有 StructureConfirmationStrategy 适配

需要为现有策略补充 `track_performance()` 方法，生成最近三个月信号记录。如果短期内无法精确计算，可以先基于历史分析记录或简化规则生成表现数据。

---

## 9. 安全设计

### 9.1 授权校验

- 所有分析请求必须校验用户是否有策略使用权。
- 授权检查在 API 层完成，策略运行时不直接访问授权表。
- 授权结果缓存到会话状态中，避免每次消息都查询数据库。

### 9.2 支付安全

- 支付信息不存储在平台数据库。
- 使用第三方支付服务（如 Stripe、支付宝、微信支付）。
- 支付回调必须校验签名，防止伪造。

### 9.3 数据隔离

- 用户只能看到自己的授权记录和订单。
- 策略表现数据是公开的（所有用户可见）。
- 用户持仓等敏感信息不用于策略表现计算。

### 9.4 审计日志

- 记录所有购买、退款、授权变更。
- 记录每次分析的授权信息。

---

## 10. 性能设计

### 10.1 预计算

- 策略最近三个月表现每日收盘后预计算。
- 商店列表和详情页直接读取汇总表，不实时计算。

### 10.2 缓存

- 策略列表可缓存 5 分钟。
- 策略详情可缓存 1 分钟。
- 用户授权列表缓存到会话中。

### 10.3 异步处理

- 支付回调异步处理。
- 策略表现更新使用定时任务异步执行。
- 订单创建和授权开通需要在支付回调中原子完成。

---

## 11. 实施计划

### 11.1 第一阶段：基础商店 + 表现展示（2-3 周）

1. 设计并实现数据库模型（策略、版本、表现信号、表现汇总）。
2. 扩展 `StrategyManifest` 和 `StrategyPlugin`。
3. 实现 `PerformanceTracker` 和定时任务。
4. 为现有策略补充 `track_performance()` 方法。
5. 实现 `StrategyStoreService` 和商店 API。
6. 前端实现策略商店列表页和详情页。

### 11.2 第二阶段：授权 + 购买流程（2-3 周）

1. 实现 `EntitlementService` 和授权表。
2. 实现 `OrderService` 和订单表。
3. 接入 mock 支付（后续替换为真实支付）。
4. 在分析流程中增加授权检查。
5. 实现「我的策略」页面。
6. 前端实现购买流程和支付页。

### 11.3 第三阶段：对话流程改造（2-3 周）

1. 实现 `FactExtractor`，根据策略 `required_facts` 抽取信息。
2. 改造对话流程，支持策略驱动信息抽取。
3. 实现澄清问题生成和用户信息确认。
4. 优化结果展示：结论卡片、可视化、策略链路。
5. 支持追问和策略切换。

### 11.4 第四阶段：支付接入与优化（2-3 周）

1. 接入真实支付渠道。
2. 实现退款流程。
3. 增加订阅到期提醒和自动续费（可选）。
4. 性能优化和缓存策略。
5. 安全审计和日志完善。

---

## 12. 风险与假设

### 12.1 风险

- **策略表现数据不准确**：如果 `track_performance()` 实现有 bug，会误导用户购买决策。
- **支付合规**：需要确保支付流程符合当地法规。
- **用户投诉**：购买后策略表现不佳可能引发退款和投诉。

### 12.2 假设

- 策略提供者（目前为平台自己）会正确实现 `track_performance()`。
- 第三方支付服务可用。
- 用户可以接受先付费后使用策略的模式。

---

## 13. 附录

### 13.1 相关文档

- `docs/PRD.md`：产品需求文档
- `docs/product-manual.md`：产品说明书
- `docs/architecture_diagram.png`：系统逻辑架构图

### 13.2 术语对照

| PRD 术语 | 技术实现 |
|---|---|
| 策略商店 | `StrategyStoreService` + `store` 模块 |
| 用户授权 | `EntitlementService` + `user_entitlements` 表 |
| 最近三个月表现 | `PerformanceTracker` + `strategy_performance_*` 表 |
| 购买/订阅 | `OrderService` + `orders` 表 + 第三方支付 |
| 信息抽取 | `FactExtractor` |
| 策略运行时 | `StrategyRuntime` + 现有 `AnalysisWorkflow` |
