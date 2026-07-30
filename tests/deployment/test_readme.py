from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
README_PATH = PROJECT_ROOT / "README.md"
README = (
    README_PATH.read_text(encoding="utf-8")
    if README_PATH.is_file()
    else ""
)


def test_readme_offers_complete_language_navigation() -> None:
    assert README_PATH.is_file()
    assert '<a id="language"></a>' in README
    assert "[中文](#中文)" in README
    assert "[English](#english)" in README
    assert '<a id="中文"></a>' in README
    assert '<a id="english"></a>' in README
    assert README.count("[返回语言选择](#language)") >= 1
    assert README.count("[Back to language selector](#language)") >= 1


def test_readme_explains_the_logical_architecture_and_trust_chain() -> None:
    required = (
        "```mermaid",
        "Next.js",
        "FastAPI",
        "SQLite",
        "Codex",
        "TqSdk",
        "AkShare",
        "Strategy Registry",
        "Risk Engine",
        "策略注册表",
        "风险引擎",
        "OpenCV",
        "local OCR",
        "本地 OCR",
        "cannot independently decide",
        "不能独立决定",
    )

    for text in required:
        assert text in README


def test_readme_contains_an_executable_local_installation_path() -> None:
    required = (
        "Python 3.10",
        "Node.js 20",
        "codex --version",
        "export CODE_CLI_API_KEY=<your-code-cli-api-key>",
        "./bin/trading-agent-local init",
        "./bin/trading-agent-local doctor",
        ". .local/env",
        ".local/venv/bin/panshi-user set-password <username>",
        "--password-stdin",
        "./trading-agent.sh start",
        "./trading-agent.sh stop",
        "./trading-agent.sh restart",
        "./bin/trading-agent-local status",
        "http://127.0.0.1:8989",
        "http://127.0.0.1:8000/docs",
    )

    for text in required:
        assert text in README


def test_readme_documents_public_repository_cloning() -> None:
    assert "git clone https://github.com/IFOSR/panshi-trading-ai.git" in README
    assert "公开仓库无需登录即可克隆" in README
    assert "The public repository can be cloned without signing in" in README
    assert "private repository" not in README


def test_readme_documents_persistence_accounts_and_operations() -> None:
    required = (
        ".local/data/trading-agent.db",
        ".local/data/images",
        ".local/logs/api.log",
        ".local/logs/web.log",
        "panshi-user disable <username>",
        "panshi-user enable <username>",
        "12 小时",
        "12-hour",
        "SQLite 备份",
        "SQLite backup",
        "服务器迁移",
        "server migration",
    )

    for text in required:
        assert text in README


def test_readme_documents_market_data_and_safety_defaults() -> None:
    required = (
        "TRADING_AGENT_TQSDK_USERNAME",
        "TRADING_AGENT_TQSDK_PASSWORD",
        "TRADING_AGENT_MARKET_DATA_PROVIDER=free",
        "AkShare fallback",
        "AkShare 降级",
        "TRADING_AGENT_ENABLE_ORDER_EXECUTION=false",
        "不连接实盘下单网关",
        "does not connect to a live order gateway",
    )

    for text in required:
        assert text in README
