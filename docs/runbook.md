# Trading Agent 本地运行手册

本项目的默认运行方式是本机轻量模式。运行时只有两个长期进程：

```text
Browser -> Next.js :8989 -> FastAPI :8000
                              |-> SQLite
                              |-> .local/data/images
                              |-> local Codex CLI
                              `-> inline strategy analysis
```

不启动独立 Worker，也不需要 PostgreSQL、Redis、MinIO、Temporal 或 OTel
Collector。未设置 `TEMPORAL_ADDRESS` 时，FastAPI 会在当前进程内依次执行
原图多模态抽取、八步策略评估、独立风控和最终动作生成。

## 前置条件

- Python 3.10 或更高版本。
- Node.js 20 或更高版本，以及 npm。
- 本机可执行 `codex --version`，并配置了可通过环境变量传入的模型供应商凭据。
- `8000` 和 `8989` 端口可用。
- 保持 `TRADING_AGENT_ENABLE_ORDER_EXECUTION=false`。本项目不连接实盘下单网关。

Codex 是默认且优先的多模态模型。运行时直接把用户原图交给 Codex CLI，不使用
OpenCV、本地 OCR、图表切片或坐标重建。Kimi 仅作为失效关闭的备用路径；本地
配置默认不会启用 Kimi，因为仅有 CLI 和临时目录不构成可信隔离边界。

## 首次初始化

从项目根目录执行：

```sh
./bin/trading-agent-local init
./bin/trading-agent-local doctor
```

`init` 会完成以下操作：

1. 创建项目私有的 `.local/venv` Python 环境并安装后端和测试依赖。
2. 执行 `npm ci` 和生产前端构建。
3. 生成权限为 `0600` 的 `.local/env`，其中包含随机 API 和隐私审核密钥。
4. 把 SQLite 数据库和原图目录固定到 `.local/data` 的绝对路径。
5. 执行 `alembic upgrade head`。
6. 从当前 shell 读取 `CODE_CLI_API_KEY` 并写入私有环境文件。

初始化完成后创建第一个 SQLite 登录用户：

```sh
set -a
. .local/env
set +a
.local/venv/bin/panshi-user set-password <username>
```

命令会两次隐藏读取密码。自动化初始化可使用
`.local/venv/bin/panshi-user set-password <username> --password-stdin`，
但密码只能通过标准输入传入，不能作为命令行参数或环境变量保存。

`.env.local.example` 仅用于说明字段。实际运行读取 `.local/env`，不要把该文件
提交到版本库。本地模式会为每次图片分析创建隔离的临时 `CODEX_HOME`，因此不会
复制或读取 `~/.codex/auth.json` 中的 OAuth 登录态。运行 `init` 前必须在当前
shell 中导出 `CODE_CLI_API_KEY`；如使用其他供应商，则在 `.local/env` 中同时
修改 `TRADING_AGENT_CODEX_MODEL_PROVIDER`、`TRADING_AGENT_CODEX_PROVIDER_BASE_URL`
和 `TRADING_AGENT_CODEX_PROVIDER_ENV_KEY`，并写入该 `env_key` 对应的凭据。

## 免费中国期货数据

本地模式默认设置 `TRADING_AGENT_MARKET_DATA_PROVIDER=free`：

- TqSdk 是主数据源，配置免费的快期账户后启用。
- AkShare 无需账号，作为自动降级数据源。
- 已收盘日线会在交易所日报可用时执行盘后校验。
- 数据源、校验来源和质量告警会展示在第 1 步数据有效性详情中。
- 所有免费源都不可用或发生数据冲突时，策略保留阻断状态，不会生成精确入场结论。

如需启用 TqSdk，在 `.local/env` 中设置：

```sh
TRADING_AGENT_TQSDK_USERNAME=your-free-tq-account
TRADING_AGENT_TQSDK_PASSWORD=your-free-tq-password
```

这些是后端服务凭据，不会增加产品登录，也不会下发到浏览器。未配置时系统直接
使用 AkShare。`init` 会安装并检查 AkShare 和 TqSdk 运行依赖。

## 启停与状态

```sh
./trading-agent.sh start
./trading-agent.sh stop
./trading-agent.sh restart
```

根目录脚本只提供日常启停；首次初始化、诊断和状态查看仍使用底层运行器：

```sh
./bin/trading-agent-local start
./bin/trading-agent-local status
./bin/trading-agent-local stop
```

`start` 会先执行 `doctor` 和数据库迁移，然后启动：

- API：`http://127.0.0.1:8000/docs`
- Web：`http://127.0.0.1:8989`

Web 使用 SQLite 账户登录。浏览器只保存 12 小时绝对有效期的 HttpOnly 会话
Cookie；FastAPI 数据库只保存会话令牌的 SHA-256 摘要。服务端访问 API 时使用
`.local/env` 中的 Bearer Token，该密钥不会下发到浏览器 JavaScript。

## 用户与会话管理

先加载本地数据库地址，再执行用户管理命令：

```sh
set -a
. .local/env
set +a

.local/venv/bin/panshi-user set-password <username>
.local/venv/bin/panshi-user disable <username>
.local/venv/bin/panshi-user enable <username>
```

- `set-password` 创建用户或执行密码轮换。密码轮换会删除该用户的全部现有会话，
  所有浏览器立即会话失效，需要使用新密码重新登录。
- `disable` 停用账户并立即删除全部会话。
- `enable` 重新启用账户，但不会恢复旧会话，用户仍需重新登录。
- 用户名会去除首尾空格并转换为小写；密码只以带随机盐的 scrypt 哈希保存。
- 会话采用 12 小时绝对有效期，不会因持续使用而无限延期。

## 用户交互

打开 `http://127.0.0.1:8989` 后先使用 SQLite 用户登录。登录后的首页是桌面
对话工作台。左侧显示最近对话，
中间是与磐石交易AI的主对话，右侧显示当前策略原则。用户选择策略、输入问题并
上传一至两张完整行情截图即可开始；合约、收盘状态、持仓量和执行周期行情优先由
多模态模型与公开数据源自动识别或补齐。

提交期间页面展示创建会话、固化持仓、应用风控、保存证据和执行策略五个阶段。
完成后进入同一案例的持续对话：

1. 最终动作作为 assistant 结论消息展示，并与策略里程碑严格对齐。
2. 底部输入框始终可用，用户可继续追问结论、步骤、证据或风险依据。
3. 追问只解释绑定的不可变分析，不会修改原始动作。
4. 只有公开数据和截图仍无法消除的真实歧义才进入对话澄清。
5. 用户确认澄清理解后，系统重新执行完整策略分析并产生新分析版本。
6. “查看策略审计”抽屉按需展示动态数量的里程碑、原图证据和变化记录。

策略由后端注册表提供，案例固定到精确策略版本。前端不假设固定八步，也不识别
具体策略步骤编号；步骤标题和过程名称由策略插件输出。当前默认插件为
`结构确认策略 v1.0.0`，后续策略可独立安装、升级、禁用和回滚。

浏览器不会接触 API Token 或隐私审核 Token。Web 入口只接受回环地址和同源提交；
本机审核操作员逐张确认图表角色与隐私后，Next.js 服务端代理才注入这两个密钥。
FastAPI 仍保持无 Bearer Token 返回 `401` 的保护。中间阶段失败时页面保留已创建
案例并允许使用稳定幂等键继续，不会重新创建案例。首次提交会对诉求、持仓、
风控参数和每张原图内容生成统一指纹；恢复时表单锁定并复用首次快照，刷新页面后
重新选择相同原图也会恢复同一案例。只要任一字段或图片发生变化，服务端就拒绝
沿用旧案例，用户必须点击“放弃本次并新建分析”，从而避免最终结论对应旧输入。

进程 PID、元数据和日志位置：

```text
.local/run/api.pid
.local/run/web.pid
.local/logs/api.log
.local/logs/web.log
```

修改 Python、前端或 `.local/env` 后执行：

```sh
./bin/trading-agent-local restart
```

前端源码变化需要先重新构建：

```sh
cd web
npm run build
cd ..
./bin/trading-agent-local restart
```

## 诊断

随时执行：

```sh
./bin/trading-agent-local doctor
```

诊断项包括 Python、Node、npm、Codex CLI、虚拟环境、前端构建、密钥、SQLite
绝对路径、图片目录写权限、内联分析约束和端口占用。任一必需项失败时，`start`
拒绝启动。

常见问题：

- `codex` 不可用：确认 `codex --version` 成功，并检查本机登录状态和
  `~/.codex/config.toml`。
- API 启动失败：查看 `.local/logs/api.log`。
- Web 启动失败：查看 `.local/logs/web.log`，并确认已经执行生产构建。
- 端口被其他程序占用：先停止占用 `8000` 或 `8989` 的程序，再重新启动。
- 数据库需要重建：先停止服务，备份 `.local/data`，再处理 SQLite 文件并重新
  执行 `init`。不要在运行中删除数据库或原图。
- 登录后立即返回登录页：确认 API 已启动，并检查账户是否被停用、会话是否超过
  12 小时；必要时执行密码轮换后重新登录。

## SQLite 备份、恢复与服务器迁移

SQLite 备份必须在停止服务后执行，确保数据库与原图处于一致状态：

```sh
./trading-agent.sh stop
cp -p .local/data/trading-agent.db /安全备份目录/trading-agent.db
cp -R .local/data/images /安全备份目录/images
```

恢复时先停止服务，把数据库和图片目录放回 `.local/data`，确认目录仅对运行用户
可读写，然后执行 `./bin/trading-agent-local init` 和
`./bin/trading-agent-local doctor`。`init` 会将旧数据库迁移到当前 Alembic
版本，不会要求把账户密码重新写入源码或环境文件。

迁移到其他服务器有两种方式：

1. 停止旧服务器，复制 `.local/data/trading-agent.db` 与
   `.local/data/images` 到新服务器同一运行目录，再执行初始化和诊断。用户哈希
   与未过期会话会随 SQLite 数据库迁移；如不希望保留会话，迁移后执行一次密码
   轮换。
2. 在新服务器执行初始化得到空数据库，再运行 `panshi-user set-password`
   创建用户，并单独迁移需要保留的业务数据与原图。

恢复或迁移完成后，依次验证登录、刷新保持、退出、错误密码和重新登录，再开始
新的策略分析。

## 验收

本地迁移完成后的最小验收顺序：

```sh
./bin/trading-agent-local doctor
./bin/trading-agent-local start
./bin/trading-agent-local status
```

随后验证 API 鉴权、创建案例、上传原始截图、执行真实 Codex 多模态分析、动态
策略里程碑、最终动作与步骤严格对齐、持续追问、对话澄清、策略切换、审计抽屉
和原图代理访问。本阶段只验收桌面页面。完成后执行
`./bin/trading-agent-local stop`。
