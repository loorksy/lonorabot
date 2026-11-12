"""What an agent can read of an uploaded PDF: its text layer, or the image of a scan.

A strategy the owner uploads as a PDF becomes the agent's method (5.6). The text layer
is extracted once, on upload; a page without text is a scan, and its largest embedded
image is kept for the existing image observation path. A file pypdf cannot read yields
nothing: the upload itself never fails because of its content.

A PDF is untrusted input, and a few kilobytes can make pypdf work for hours, so the
upload route parses it in a child process with a wall-clock limit and a memory limit
(``extract``); a file that exceeds them yields nothing as well.
"""

import asyncio
import base64
import io
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import cast

from PIL import Image
from pypdf import PageObject, PdfReader

MAX_PAGES = 100
# The child process's budget: seconds of wall clock and bytes of address space.
EXTRACT_SECONDS = 30
EXTRACT_MEMORY = 1024 * 1024 * 1024
MAX_TEXT_CHARS = 400_000
MAX_PAGE_IMAGES = 8
IMAGE_SIDE = 2000

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfLayers:
    text: str = ""
    images: list[bytes] = field(default_factory=list[bytes])


def page_image(page: PageObject) -> bytes | None:
    """The page's largest embedded image as a JPEG, bounded in size; None if unreadable."""
    try:
        best: Image.Image | None = None
        for candidate in page.images:
            picture = cast(Image.Image | None, getattr(candidate, "image", None))
            if picture is not None and (
                best is None or picture.width * picture.height > best.width * best.height
            ):
                best = picture
        if best is None:
            return None
        best = best.convert("RGB")
        best.thumbnail((IMAGE_SIDE, IMAGE_SIDE))
        out = io.BytesIO()
        best.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception:  # noqa: BLE001 - an unreadable image is a page without one
        return None


def pdf_layers(content: bytes) -> PdfLayers:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            return PdfLayers()
        total = len(reader.pages)
        texts: list[str] = []
        images: list[bytes] = []
        skipped_scans = 0
        for number, page in enumerate(reader.pages[:MAX_PAGES], 1):
            text = (page.extract_text() or "").strip()
            if text:
                texts.append(f"[page {number}]\n{text}")
            elif len(images) >= MAX_PAGE_IMAGES:
                skipped_scans += 1
            elif (image := page_image(page)) is not None:
                images.append(image)
        # Say what was left out, so a partial strategy is never taken for the whole one.
        if total > MAX_PAGES:
            texts.append(f"[Pages {MAX_PAGES + 1} to {total} were not read.]")
        if skipped_scans:
            texts.append(f"[{skipped_scans} more scanned pages were not attached as images.]")
        text = "\n\n".join(texts)
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "\n[Text layer truncated.]"
        return PdfLayers(text, images)
    except Exception as error:  # noqa: BLE001 - malformed input is data, not a failure
        log.info("pdf_layers_unreadable", extra={"error": type(error).__name__})
        return PdfLayers()


def is_pdf(media_type: str, name: str) -> bool:
    """A file typed as PDF, or an untyped one named .pdf; never one stored as text."""
    return media_type == "application/pdf" or (
        media_type == "application/octet-stream" and name.lower().endswith(".pdf")
    )


async def extract(content: bytes) -> PdfLayers:
    """``pdf_layers`` in a child process, killed at EXTRACT_SECONDS; nothing on failure."""
    # -I ignores the working directory and PYTHONPATH; the child gets this process's own
    # import path, so it runs exactly the code the API runs.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        f"import sys; sys.path[:0] = {sys.path!r}; from {__name__} import main; main()",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(content), EXTRACT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        log.info("pdf_layers_timeout")
        return PdfLayers()
    if process.returncode != 0:
        log.warning("pdf_layers_failed", extra={"returncode": process.returncode})
        return PdfLayers()
    try:
        data = json.loads(output)
        return PdfLayers(str(data["text"]), [base64.b64decode(image) for image in data["images"]])
    except (ValueError, KeyError, TypeError):
        return PdfLayers()


def main() -> None:
    """The child process: a PDF on stdin, its layers as JSON on stdout."""
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (EXTRACT_MEMORY, EXTRACT_MEMORY))
    resource.setrlimit(resource.RLIMIT_CPU, (EXTRACT_SECONDS, EXTRACT_SECONDS))
    layers = pdf_layers(sys.stdin.buffer.read())
    json.dump(
        {
            "text": layers.text,
            "images": [base64.b64encode(image).decode() for image in layers.images],
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
