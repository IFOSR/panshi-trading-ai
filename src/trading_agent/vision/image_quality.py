from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class OriginalImageArtifact(BaseModel):
    path: Path
    sha256: str
    byte_size: int
    media_type: str
    is_accepted: bool = True
    transformed: bool = False


def _validate_signature(extension: str, content: bytes) -> None:
    if extension == ".png" and not content.startswith(PNG_SIGNATURE):
        raise ValueError("invalid PNG signature")
    if extension in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise ValueError("invalid JPEG signature")
    if extension == ".webp" and not (
        content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    ):
        raise ValueError("invalid WEBP signature")


def inspect_original_image(
    path: Path,
    *,
    storage_root: Path,
) -> OriginalImageArtifact:
    if path.is_symlink():
        raise ValueError("image symlinks are not allowed")
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ValueError("image path must be a regular file")

    resolved_root = storage_root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("image path is outside the configured storage root")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported image extension: {extension}")

    content = resolved_path.read_bytes()
    if not content:
        raise ValueError("image is empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds maximum byte size")
    _validate_signature(extension, content)

    media_type = "image/jpeg" if extension in {".jpg", ".jpeg"} else f"image/{extension[1:]}"
    return OriginalImageArtifact(
        path=path,
        sha256=sha256(content).hexdigest(),
        byte_size=len(content),
        media_type=media_type,
    )
