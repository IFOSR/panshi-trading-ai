from pathlib import Path

import pytest

from trading_agent.vision.image_quality import inspect_original_image


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


def test_original_chart_is_accepted_without_transformation() -> None:
    result = inspect_original_image(FIXTURE)

    assert result.is_accepted is True
    assert result.path == FIXTURE
    assert result.byte_size > 100_000
    assert len(result.sha256) == 64
    assert result.transformed is False


def test_unsupported_file_extension_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "chart.txt"
    source.write_text("not an image")

    with pytest.raises(ValueError, match="unsupported image extension"):
        inspect_original_image(source)


def test_missing_image_is_rejected() -> None:
    with pytest.raises(FileNotFoundError):
        inspect_original_image(Path("tests/fixtures/charts/missing.png"))
