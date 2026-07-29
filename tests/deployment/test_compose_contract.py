from pathlib import Path


COMPOSE = Path("docker-compose.yml").read_text(encoding="utf-8")
DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
ENV_EXAMPLE = Path(".env.example").read_text(encoding="utf-8")
RUNBOOK = Path("docs/runbook.md").read_text(encoding="utf-8")
EVALUATION = Path("docs/evaluation.md").read_text(encoding="utf-8")


def test_compose_connects_api_to_postgres() -> None:
    assert "TRADING_AGENT_DATABASE_URL: postgresql+psycopg://" in COMPOSE


def test_compose_runs_long_lived_temporal_worker() -> None:
    assert "python -m trading_agent.workflows.worker" in COMPOSE
    assert "TEMPORAL_ADDRESS: temporal:7233" in COMPOSE
    assert "condition: service_healthy" in COMPOSE
    assert "restart: unless-stopped" in COMPOSE


def test_compose_connects_web_to_api() -> None:
    assert "TRADING_API_URL: http://api:8000" in COMPOSE
    web_service = COMPOSE.split("  web:\n", 1)[1].split("\nvolumes:", 1)[0]
    assert "TRADING_AGENT_PRIVACY_REVIEW_TOKEN" in web_service
    assert "TRADING_AGENT_WEB_USERNAME" not in COMPOSE
    assert "TRADING_AGENT_WEB_PASSWORD" not in COMPOSE
    assert "TRADING_AGENT_WEB_USERNAME" not in ENV_EXAMPLE
    assert "TRADING_AGENT_WEB_PASSWORD" not in ENV_EXAMPLE


def test_compose_runs_migrations_and_shares_original_images() -> None:
    assert "alembic upgrade head && uvicorn" in COMPOSE
    assert "image-data:/app/data/images" in COMPOSE


def test_compose_wires_privacy_market_data_and_public_image_configuration() -> None:
    assert "TRADING_AGENT_PRIVACY_REVIEW_TOKEN" in COMPOSE
    assert "TRADING_AGENT_MARKET_DATA_URL" in COMPOSE
    assert "TRADING_PUBLIC_API_URL" in COMPOSE
    assert "TRADING_AGENT_API_TOKEN: ${TRADING_AGENT_API_TOKEN:?" in COMPOSE
    assert "TRADING_AGENT_API_TOKEN=replace-with-api-secret" in ENV_EXAMPLE


def test_evaluation_documents_independent_original_image_requirement() -> None:
    assert "unique original-image content hashes" in EVALUATION


def test_compose_uses_minimal_api_and_cli_enabled_worker_targets() -> None:
    assert "api:\n    build:\n      context: .\n      target: api" in COMPOSE
    assert "worker:\n    build:\n      context: .\n      target: worker" in COMPOSE


def test_worker_image_pins_and_validates_cli_runtime() -> None:
    assert "ARG NODE_VERSION=22.19.0" in DOCKERFILE
    assert "ARG CODEX_CLI_VERSION=0.144.6" in DOCKERFILE
    assert "ARG KIMI_CLI_VERSION=0.28.0" in DOCKERFILE
    assert "@openai/codex@${CODEX_CLI_VERSION}" in DOCKERFILE
    assert "@moonshot-ai/kimi-code@${KIMI_CLI_VERSION}" in DOCKERFILE
    assert 'test "$(codex --version)" = "codex-cli ${CODEX_CLI_VERSION}"' in DOCKERFILE
    assert 'test "$(kimi --version)" = "${KIMI_CLI_VERSION}"' in DOCKERFILE
    assert "FROM app-runtime AS worker" in DOCKERFILE
    assert "apt-get install --yes --no-install-recommends libatomic1 libstdc++6" in DOCKERFILE
    assert DOCKERFILE.rstrip().endswith(
        'CMD ["sh", "-c", "alembic upgrade head && uvicorn '
        'trading_agent.api.app:app --host 0.0.0.0 --port 8000"]'
    )


def test_worker_receives_auth_at_runtime_and_persists_kimi_config() -> None:
    assert "CODE_CLI_API_KEY: ${CODE_CLI_API_KEY:?required}" in COMPOSE
    assert "CODE_CLI_API_KEY" not in DOCKERFILE
    assert "kimi-config:/home/trading/.kimi-code" in COMPOSE
    assert "codex-config:/home/trading/.codex" in COMPOSE
    assert "kimi-config:" in COMPOSE
    assert "codex-config:" in COMPOSE
    assert "USER trading" in DOCKERFILE
    assert "mkdir -p /home/trading/.codex /home/trading/.kimi-code" in DOCKERFILE
    assert "chown -R trading:trading /home/trading" in DOCKERFILE


def test_worker_has_an_explicit_codex_provider_contract() -> None:
    for setting in (
        "TRADING_AGENT_CODEX_MODEL_PROVIDER",
        "TRADING_AGENT_CODEX_PROVIDER_BASE_URL",
        "TRADING_AGENT_CODEX_PROVIDER_ENV_KEY",
    ):
        assert setting in COMPOSE
        assert setting in ENV_EXAMPLE
    assert "TRADING_AGENT_CODEX_MODEL" in COMPOSE


def test_legacy_worker_build_contract_remains_self_contained() -> None:
    for setting in (
        "WORKER_NODE_VERSION=22.19.0",
        "CODEX_CLI_VERSION=0.144.6",
        "KIMI_CLI_VERSION=0.28.0",
        "CODE_CLI_API_KEY=",
    ):
        assert setting in ENV_EXAMPLE
    assert "docker compose" not in RUNBOOK.lower()
