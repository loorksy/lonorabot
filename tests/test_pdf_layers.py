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
        turns: list[Any] = [
            lambda version: ToolCall(
                id="method",
                name="memory_write",
                arguments={
                    "version": version,
                    "operations": [
                        {"action": "add", "section": "OPERATING.md", "content": "- " + rule}
                        for rule in RULES
                    ],
                },
            ),
        ]

        async def model(_: Any, messages: list[Any], *args: Any, **kwargs: Any):
            seen.append("\n".join(str(message.content) for message in messages))
            if turns:
                return ModelReply(tool_calls=[turns.pop(0)(1)]), ModelSelection(
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
        assert latest["from_owner_message"] is True
    finally:
        await fixture.close()
