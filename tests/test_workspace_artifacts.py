"""Saved report/raster format validation does not trust filenames alone."""

from io import BytesIO

import pytest
from lonora_agent.workspace_artifacts import export_media
from lonora_core.user_error import LonoraError
from PIL import Image


@pytest.mark.parametrize(
    "name,media,content",
    [
        ("report.md", "text/markdown", b"# Verified observations"),
        ("table.csv", "text/csv", b"time,close\n1,12\n"),
        ("table.tsv", "text/tab-separated-values", b"time\tclose\n"),
        ("data.json", "application/json", b'{"count":3}'),
        ("notes.txt", "text/plain", "ملاحظات".encode()),
    ],
)
def test_supported_text_reports(name: str, media: str, content: bytes) -> None:
    assert export_media(name, content) == media


@pytest.mark.parametrize(
    "fmt,suffix,media",
    [
        ("PNG", "png", "image/png"),
        ("JPEG", "jpg", "image/jpeg"),
        ("WEBP", "webp", "image/webp"),
        ("GIF", "gif", "image/gif"),
    ],
)
def test_supported_rasters_decode_real_pixels(fmt: str, suffix: str, media: str) -> None:
    stream = BytesIO()
    Image.new("RGB", (8, 6), "green").save(stream, format=fmt)
    assert export_media("analysis." + suffix, stream.getvalue()) == media


@pytest.mark.parametrize(
    "name,content,code",
    [
        ("data.json", b"invalid", "workspace_export_format_invalid"),
        ("report.md", b"\xff", "workspace_export_format_invalid"),
        ("report.html", b"<script>invalid</script>", "workspace_export_format_unsupported"),
        ("image.svg", b"<svg/>", "workspace_export_format_unsupported"),
        ("image.png", b"fake", "artifact_image_invalid"),
    ],
)
def test_unsupported_or_invalid_formats(name: str, content: bytes, code: str) -> None:
    with pytest.raises(LonoraError, match=code):
        export_media(name, content)


def test_disguised_raster_and_animation_are_not_visual_evidence() -> None:
    stream = BytesIO()
    Image.new("RGB", (8, 6), "green").save(stream, format="PNG")
    with pytest.raises(LonoraError, match="artifact_image_format_unsupported"):
        export_media("wrong.jpg", stream.getvalue())
    animated = BytesIO()
    Image.new("RGB", (8, 6), "green").save(
        animated,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (8, 6), "red")],
        duration=100,
    )
    with pytest.raises(LonoraError, match="artifact_image_format_unsupported"):
        export_media("animated.gif", animated.getvalue())
