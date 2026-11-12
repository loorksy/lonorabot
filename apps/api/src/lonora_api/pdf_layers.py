"""What an agent can read of an uploaded PDF: its text layer, or the image of a scan.

A strategy the owner uploads as a PDF becomes the agent's method (5.6). The text layer
is extracted once, on upload; a page without text is a scan, and its largest embedded
image is kept for the existing image observation path. A file pypdf cannot read yields
nothing: the upload itself never fails because of its content.
"""

import io
import logging
from dataclasses import dataclass, field
from typing import cast

from PIL import Image
from pypdf import PageObject, PdfReader

MAX_PAGES = 200
MAX_TEXT_CHARS = 400_000
MAX_PAGE_IMAGES = 8
IMAGE_SIDE = 2000

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfLayers:
    text: str = ""
    images: list[bytes] = field(default_factory=list[bytes])


def page_image(page: PageObject) -> bytes | None:
    """The page's largest embedded image as a JPEG, bounded in size."""
    best: Image.Image | None = None
    try:
        for candidate in page.images:
            picture = cast(Image.Image | None, getattr(candidate, "image", None))
            if picture is not None and (
                best is None or picture.width * picture.height > best.width * best.height
            ):
                best = picture
    except Exception:  # noqa: BLE001 - an unreadable image is a page without one
        pass
    if best is None:
        return None
    best = best.convert("RGB")
    best.thumbnail((IMAGE_SIDE, IMAGE_SIDE))
    out = io.BytesIO()
    best.save(out, format="JPEG", quality=85)
    return out.getvalue()


def pdf_layers(content: bytes) -> PdfLayers:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            return PdfLayers()
        pages = reader.pages[:MAX_PAGES]
        texts: list[str] = []
        images: list[bytes] = []
        for number, page in enumerate(pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                texts.append(f"[page {number}]\n{text}")
            elif len(images) < MAX_PAGE_IMAGES and (image := page_image(page)) is not None:
                images.append(image)
        return PdfLayers("\n\n".join(texts)[:MAX_TEXT_CHARS], images)
    except Exception as error:  # noqa: BLE001 - malformed input is data, not a failure
        log.info("pdf_layers_unreadable", extra={"error": type(error).__name__})
        return PdfLayers()


def is_pdf(media_type: str, name: str) -> bool:
    return media_type == "application/pdf" or name.lower().endswith(".pdf")
