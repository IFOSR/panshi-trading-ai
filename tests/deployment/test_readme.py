from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHINESE_PATH = PROJECT_ROOT / "README.md"
ENGLISH_PATH = PROJECT_ROOT / "README.en.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


CHINESE = _read(CHINESE_PATH)
ENGLISH = _read(ENGLISH_PATH)


def test_readmes_are_separate_pages_with_chinese_as_default() -> None:
    assert CHINESE_PATH.is_file()
    assert ENGLISH_PATH.is_file()
    assert "**中文** | [English](README.en.md)" in CHINESE
    assert "[中文](README.md) | **English**" in ENGLISH
    assert '<a id="中文"></a>' not in CHINESE
    assert '<a id="english"></a>' not in CHINESE
    assert "# English" not in CHINESE
    assert "# 中文" not in ENGLISH
    assert "What is Panshi Trading AI?" not in CHINESE
    assert "磐石交易AI是什么" not in ENGLISH


def test_each_page_explains_the_logical_architecture_and_trust_chain() -> None:
    shared = (
        "```mermaid",
        "Next.js",
        "FastAPI",
        "SQLite",
        "DeepSeek",
        "TqSdk",
        "AkShare",
        "OpenCV",
    )
    chinese = (
        "逻辑架构",
        "策略注册表",
        "风险引擎",
        "本地 OCR",
        "不能独立决定",
    )
    english = (
        "Logical architecture",
        "Strategy Registry",
        "Risk Engine",
        "local OCR",
        "cannot independently decide",
    )

    for text in shared:
        assert text in CHINESE
        assert text in ENGLISH
    for text in chinese:
        assert text in CHINESE
    for text in english:
        assert text in ENGLISH


def test_each_page_contains_an_executable_local_installation_path() -> None:
    shared = (
        "Python 3.10",
        "Node.js 20",
        "export DEEPSEEK_API_KEY=<your-deepseek-api-key>",
        "git clone https://github.com/IFOSR/panshi-trading-ai.git",
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
        "http://127.0.0.1:8005/docs",
    )

    for text in shared:
        assert text in CHINESE
        assert text in ENGLISH
    assert "公开仓库无需登录即可克隆" in CHINESE
    assert "The public repository can be cloned without signing in" in ENGLISH


def test_each_page_documents_accounts_runtime_paths_and_sessions() -> None:
    shared = (
        ".local/data/trading-agent.db",
        ".local/data/images",
        ".local/logs/api.log",
        ".local/logs/web.log",
        "panshi-user disable <username>",
        "panshi-user enable <username>",
    )

    for text in shared:
        assert text in CHINESE
        assert text in ENGLISH
    assert "12 小时" in CHINESE
    assert "12-hour" in ENGLISH


def test_each_page_documents_market_data_and_safety_defaults() -> None:
    shared = (
        "TRADING_AGENT_TQSDK_USERNAME",
        "TRADING_AGENT_TQSDK_PASSWORD",
        "TRADING_AGENT_MARKET_DATA_PROVIDER=free",
        "TRADING_AGENT_ENABLE_ORDER_EXECUTION=false",
    )

    for text in shared:
        assert text in CHINESE
        assert text in ENGLISH
    assert "AkShare 降级" in CHINESE
    assert "AkShare fallback" in ENGLISH
    assert "不连接实盘下单网关" in CHINESE
    assert "does not connect to a live order gateway" in ENGLISH


def test_excluded_operational_sections_are_absent() -> None:
    forbidden_chinese = (
        "### SQLite 备份",
        "### 恢复",
        "### 服务器迁移",
        "/safe/backup/panshi",
        ".before-restore-",
        "rm -rf",
    )
    forbidden_english = (
        "### SQLite backup",
        "### Restore",
        "### Server migration",
        "/safe/backup/panshi",
        ".before-restore-",
        "rm -rf",
    )

    for text in forbidden_chinese:
        assert text not in CHINESE
    for text in forbidden_english:
        assert text not in ENGLISH
