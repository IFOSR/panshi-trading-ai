from pathlib import Path


COMPOSE = Path("docker-compose.yml").read_text(encoding="utf-8")


def test_compose_connects_api_to_postgres() -> None:
    assert "TRADING_AGENT_DATABASE_URL: postgresql+psycopg://" in COMPOSE


def test_compose_runs_long_lived_temporal_worker() -> None:
    assert "python -m trading_agent.workflows.worker" in COMPOSE
    assert "TEMPORAL_ADDRESS: temporal:7233" in COMPOSE


def test_compose_connects_web_to_api() -> None:
    assert "TRADING_API_URL: http://api:8000" in COMPOSE
