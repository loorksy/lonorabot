"""5.6: a strategy PDF the owner uploads reaches the agent.

The server extracts the PDF's text layer on upload (lead decision Q9 a). A scanned
page has no text layer: its page image goes to the existing image observation path.
"""

import io
import os
import zlib
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from lonora_api.pdf_layers import pdf_layers
from PIL import Image


def pdf(objects: list[bytes]) -> bytes:
    """A minimal valid PDF from numbered object bodies (1 is the catalog)."""
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def stream(data: bytes, extra: bytes = b"") -> bytes:
    return b"<< /Length %d %s >>\nstream\n" % (len(data), extra) + data + b"\nendstream"


def text_pdf(lines: list[str]) -> bytes:
    content = (
        b"BT /F1 12 Tf 72 720 Td 14 TL "
        + b" ".join(b"(" + line.encode() + b") '" for line in lines)
        + b" ET"
    )
    return pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            stream(content),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
    )


def scanned_pdf() -> bytes:
    picture = Image.new("RGB", (40, 20), (200, 30, 30))
    raw = zlib.compress(picture.tobytes())
    return pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /XObject << /Im1 5 0 R >> >> >>",
            stream(b"q 612 0 0 792 0 0 cm /Im1 Do Q"),
            stream(
                raw,
                b"/Type /XObject /Subtype /Image /Width 40 /Height 20 /ColorSpace /DeviceRGB "
                b"/BitsPerComponent 8 /Filter /FlateDecode",
            ),
        ]
    )


RULES = [
    "Gold strategy: buy pullbacks to the H4 50 EMA.",
    "Add the second position without confirmation once the first is at break-even.",
]


def test_the_text_layer_of_a_strategy_pdf_is_extracted():
    layers = pdf_layers(text_pdf(RULES))
    for rule in RULES:
        assert rule in layers.text
    assert layers.text.startswith("[page 1]") and layers.images == []


def test_a_scanned_page_yields_its_image():
    layers = pdf_layers(scanned_pdf())
    assert layers.text == ""
    assert len(layers.images) == 1
    image = Image.open(io.BytesIO(layers.images[0]))
    assert image.format == "JPEG" and image.size == (40, 20)


def test_a_broken_file_yields_nothing_and_never_raises():
    for content in (b"", b"%PDF-1.4 garbage", b"not a pdf at all"):
        layers = pdf_layers(content)
        assert layers.text == "" and layers.images == []


def slow_pdf(pages: int) -> bytes:
    """A few kilobytes that make text extraction work for seconds per page."""
    content = zlib.compress(b"BT /F1 1 Tf " + b"(a) Tj " * 300_000 + b"ET")
    kids = " ".join(f"{3 + index} 0 R" for index in range(pages)).encode()
    page = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
        b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (3 + pages, 4 + pages)
    )
    return pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % pages,
            *[page] * pages,
            stream(content, b"/Filter /FlateDecode"),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
    )


@pytest.mark.asyncio
async def test_extraction_runs_in_a_child_process_and_a_slow_file_is_cut_off(
    monkeypatch: pytest.MonkeyPatch,
):
    import time

    from lonora_api import pdf_layers as module

    found = await module.extract(text_pdf(RULES))
    assert all(rule in found.text for rule in RULES)
    monkeypatch.setattr(module, "EXTRACT_SECONDS", 2)
    started = time.monotonic()
    slow = await module.extract(slow_pdf(40))
    assert slow.text == "" and slow.images == []
    assert time.monotonic() - started < 10


def mixed_pdf() -> bytes:
    """Page 1 has a text layer, page 2 is a scan."""
    picture = Image.new("RGB", (40, 20), (30, 30, 200))
    return pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
            b"/Resources << /Font << /F1 6 0 R >> >> >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 7 0 R "
            b"/Resources << /XObject << /Im1 8 0 R >> >> >>",
            stream(b"BT /F1 12 Tf 72 720 Td (" + RULES[0].encode() + b") Tj ET"),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            stream(b"q 612 0 0 792 0 0 cm /Im1 Do Q"),
            stream(
                zlib.compress(picture.tobytes()),
                b"/Type /XObject /Subtype /Image /Width 40 /Height 20 /ColorSpace /DeviceRGB "
                b"/BitsPerComponent 8 /Filter /FlateDecode",
            ),
        ]
    )


def test_an_unconvertible_image_never_loses_the_text_of_other_pages(
    monkeypatch: pytest.MonkeyPatch,
):
    both = pdf_layers(mixed_pdf())
    assert RULES[0] in both.text and len(both.images) == 1

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise OSError("truncated image")

    monkeypatch.setattr(Image.Image, "convert", broken)
    layers = pdf_layers(mixed_pdf())
    assert RULES[0] in layers.text and layers.images == []


def test_only_pdf_typed_or_untyped_pdf_files_get_sidecars():
    from lonora_api.pdf_layers import is_pdf

    assert is_pdf("application/pdf", "strategy")
    assert is_pdf("application/octet-stream", "Strategy.PDF")
    assert not is_pdf("text/plain", "x.pdf")


def test_left_out_text_is_named_never_silent():
    from lonora_agent.context.attachments import ATTACHMENT_CHARS, bounded

    assert bounded("short", "a1") == "short"
    long = bounded("x" * (ATTACHMENT_CHARS + 10), "a1")
    assert long.startswith("x" * ATTACHMENT_CHARS)
    assert f"offset {ATTACHMENT_CHARS}" in long and "a1" in long
    many = pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids ["
            + b" ".join(b"%d 0 R" % (3 + index) for index in range(102))
            + b"] /Count 102 >>",
            *[
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 105 0 R "
                b"/Resources << /Font << /F1 106 0 R >> >> >>"
            ]
            * 102,
            stream(b"BT /F1 12 Tf 72 720 Td (rule) Tj ET"),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
    )
    assert "[Pages 101 to 102 were not read.]" in pdf_layers(many).text


def test_readers_ignore_forged_sidecar_keys(tmp_path: Any):
    from lonora_agent.context.attachments import sidecar

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "t.text").write_text("layer")
    assert sidecar(tmp_path, "a/t.text") is not None
    for forged in (".", "", "../etc/passwd", "/etc/passwd", 7, ["a/t.text"], None, "a/none"):
        assert sidecar(tmp_path, forged) is None


# --- PostgreSQL: section 16 step 3, a strategy PDF becomes the agent's method ----------


@pytest.mark.asyncio
async def test_an_uploaded_strategy_pdf_ends_as_a_method_version_quoting_its_rules():
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The upload-to-method path uses the real migrated PostgreSQL schema.")
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelReply, ToolCall
    from lonora_agent.executor import execute_run
    from lonora_contracts.model_routing import ModelSelection
    from lonora_memory.method import method_history
    from lonora_tools.loader import load_tools

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Gold strategy " + uuid4().hex[:6])
        thread = await fixture.conversation(agent)
        upload = await fixture.client.post(
            "/api/artifacts/upload",
            files={"file": ("gold-strategy.pdf", text_pdf(RULES), "application/pdf")},
            data={"thread_id": thread["id"]},
        )
        assert upload.status_code == 201, upload.text
        artifact = upload.json()
        assert artifact["payload"]["text_chars"] > 0
        sent = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "هذه استراتيجيتي، اعتمدها",
                "attachment_ids": [artifact["id"]],
                "client_nonce": "strategy-" + uuid4().hex,
            },
        )
        run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        context = await fixture.lease(run)
        seen: list[str] = []
        write = ToolCall(
            id="method",
            name="memory_write",
            arguments={
                "version": 1,
                "operations": [
                    {"action": "add", "section": "OPERATING.md", "content": "- " + rule}
                    for rule in RULES
                ],
            },
        )
        # Text in a file is someone else's words (6.10): the run no longer stands for the
        # owner's typed message, so a setting only the owner's word changes is refused.
        injected = ToolCall(
            id="prefs", name="owner_preferences_update", arguments={"reach_me": "activity"}
        )
        turns = [write, injected]

        async def model(_: Any, messages: list[Any], *args: Any, **kwargs: Any):
            seen.append("\n".join(str(message.content) for message in messages))
            if turns:
                return ModelReply(tool_calls=[turns.pop(0)]), ModelSelection(
                    provider="openai", model="scripted-strategy"
                )
            return ModelReply(text="حفظت الاستراتيجية في منهجي وسأطبقها."), ModelSelection(
                provider="openai", model="scripted-strategy"
            )

        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(context, load_tools(), 120, 8)
        # The model read the strategy's rules from the PDF's text layer.
        assert all(rule in seen[0] for rule in RULES)
        async with fixture.runtime.db.sessions() as session:
            history = await method_history(session, fixture.owner, agent["id"])
            latest = history["versions"][0]
            text = (
                await method_history(session, fixture.owner, agent["id"], version=latest["version"])
            )["version"]["text"]
        # A rule about adding without waiting for the first position is saved as written.
        assert all(rule in text for rule in RULES)
        assert latest["from_owner_message"] is False
        assert "owner_preferences_require_owner_message" in seen[-1]
    finally:
        await fixture.close()
