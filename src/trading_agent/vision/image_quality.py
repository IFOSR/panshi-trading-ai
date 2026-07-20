from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class OriginalImageArtifact(BaseModel):
    path: Path
    sha256: str
    byte_size: int
    media_type: str
    is_accepted: bool = True
    transformed: bool = False


def inspect_original_image(path: Path) -> OriginalImageArtifact:
    if not path.exists():
        raise FileNotFoundError(path)
    extension = path.suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported image extension: {extension}")

    content = path.read_bytes()
    if not content:
        raise ValueError("image is empty")

    media_type = "image/jpeg" if extension in {".jpg", ".jpeg"} else f"image/{extension[1:]}"
    return OriginalImageArtifact(
        path=path,
        sha256=sha256(content).hexdigest(),
        byte_size=len(content),
        media_type=media_type,
    )

