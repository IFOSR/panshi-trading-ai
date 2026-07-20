from pathlib import Path

import pytest

from trading_agent.vision.image_quality import inspect_original_image


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


def test_original_chart_is_accepted_without_transformation() -> None:
    result = inspect_original_image(FIXTURE, storage_root=FIXTURE.parent)

    assert result.is_accepted is True
    assert result.path == FIXTURE
    assert result.byte_size > 100_000
    assert len(result.sha256) == 64
    assert result.transformed is False


def test_unsupported_file_extension_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "chart.txt"
    source.write_text("not an image")

    with pytest.raises(ValueError, match="unsupported image extension"):
        inspect_original_image(source, storage_root=tmp_path)


def test_missing_image_is_rejected() -> None:
    with pytest.raises(FileNotFoundError):
        inspect_original_image(
            Path("tests/fixtures/charts/missing.png"),
            storage_root=FIXTURE.parent,
        )


def test_fake_png_signature_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "fake.png"
    source.write_bytes(b"not really a png")

    with pytest.raises(ValueError, match="signature"):
        inspect_original_image(source, storage_root=tmp_path)


def test_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "real.png"
    target.write_bytes(FIXTURE.read_bytes())
    link = tmp_path / "link.png"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        inspect_original_image(link, storage_root=tmp_path)


def test_path_outside_storage_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage root"):
        inspect_original_image(FIXTURE, storage_root=tmp_path)
