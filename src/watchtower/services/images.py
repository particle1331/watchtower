"""Validate image uploads and choose content-addressed repository paths."""

import hashlib
import re
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .workspace import ServiceError

MAX_FIGURE_BYTES = 20 * 1024 * 1024


def portfolio_figure(artifact_id: str, data: bytes) -> str:
    return uploaded_image("portfolio", artifact_id, data)


def uploaded_image(collection: str, identity: str, data: bytes) -> str:
    if collection not in {"portfolio", "courses", "photos"}:
        raise ServiceError("Unsupported image collection.")
    if not data or len(data) > MAX_FIGURE_BYTES:
        raise ServiceError("Choose an image no larger than 20 MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}.get(image.format or "")
            if extension is None:
                raise ServiceError("Choose a PNG, JPEG, WebP, or GIF image.")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ServiceError("The uploaded file is not a valid PNG, JPEG, WebP, or GIF image.") from error
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", identity.split("/")[-1]).strip(".-")[:80] or "image"
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()[:12]
    content = hashlib.sha256(data).hexdigest()
    return f"backend/assets/{collection}/{slug}-{identity_hash}-{content}.{extension}"
