"""The Gateway's client of the workspace supervisor.

Every answer is decoded through one `SecretScan` before anything else sees it: command
output, file contents, process lists and job command lines alike (7.2.6; map Q11 (b)).
A file whose bytes are returned raw (an export) is refused when it carries a secret,
because bytes cannot be rewritten.
"""

import base64
import codecs
import os
from typing import Any

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.secrets import SecretScan

SOCKET = "/run/lonora-workspace/supervisor.sock"
# Longer than any encoded form of a secret (16,000 characters, percent-encoded): text
# around a cut is read or dropped by this much so no secret is ever half seen.
MARGIN = 49152
# The shortest start of a secret form treated as that secret when a stream ends in it.
PARTIAL = 6


def chars(prefix: bytes) -> int:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    return len(decoder.decode(prefix, final=False))


def merged(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for start, end, name in sorted(spans):
        if out and start < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end), out[-1][2])
        else:
            out.append((start, end, name))
    return out


def window(scan: SecretScan, text: str, start: int, end: int) -> str:
    """text[start:end] with every secret that touches it replaced, including one that
    crosses either edge (its marker stands at the edge)."""
    pieces: list[str] = []
    position = start
    for first, last, name in merged(scan.spans(text)):
        if last <= start or first >= end:
            continue
        if first > position:
            pieces.append(text[position:first])
        pieces.append(f"[secret:{name}]")
        position = max(position, last)
    if position < end:
        pieces.append(text[position:end])
    return "".join(pieces)


def trailing(scan: SecretScan, text: str) -> str:
    """Replace an end of `text` that is the start of a secret form (at least
    PARTIAL characters): a stream killed mid-print, a file cut mid-value."""
    forms = [form.text for form in (*scan.plain, *scan.wrapped)]
    best: tuple[int, str] | None = None
    for form, name in zip(forms, [f.name for f in (*scan.plain, *scan.wrapped)], strict=True):
        tail = text[-(len(form) - 1) :] if len(form) > 1 else ""
        start = 0
        while (start := tail.find(form[0], start)) >= 0:
            piece = tail[start:]
            if len(piece) >= PARTIAL and form.startswith(piece):
                if best is None or len(piece) > best[0]:
                    best = (len(piece), name)
                break
            start += 1
    if best is None:
        return text
    return text[: len(text) - best[0]] + f"[secret:{best[1]}]"


def cut_output(result: dict[str, Any]) -> dict[str, Any]:
    """A stream the supervisor cut, or one whose command was killed, may end inside a
    secret: drop its last MARGIN characters before scanning, and count them as dropped."""
    for stream in ("stdout", "stderr"):
        dropped = result.get(f"{stream}_dropped_bytes", 0)
        text = result.get(stream)
        if (dropped or result.get("timed_out")) and isinstance(text, str):
            kept = text[:-MARGIN] if len(text) > MARGIN else ""
            result[stream] = kept
            result[f"{stream}_dropped_bytes"] = dropped + len(text[len(kept) :].encode())
    return result


class WorkspaceClient:
    def __init__(
        self, socket_path: str = SOCKET, transport: httpx.AsyncBaseTransport | None = None
    ):
        # A transport per call: closing a client closes its transport, and one client of
        # this class serves every concurrent run.
        self.socket_path = None if transport else socket_path
        self.fixed = transport

    def present(self) -> bool:
        """Whether the supervisor's socket is there (presentation only)."""
        return self.socket_path is None or os.path.exists(self.socket_path)

    async def _call(
        self, method: str, path: str, body: dict[str, Any] | None, seconds: float
    ) -> dict[str, Any]:
        transport = self.fixed or httpx.AsyncHTTPTransport(uds=self.socket_path or SOCKET)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://workspace", timeout=seconds
        ) as client:
            try:
                response = await client.request(method, path, json=body)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                raise LonoraError("workspace_unavailable", 503) from None
            except httpx.TransportError:
                # Sent, but no answer: the command may be running or done. Look at the
                # processes before running it again.
                raise LonoraError("workspace_outcome_unknown", 504) from None
        if response.status_code == 422 or response.status_code == 503:
            code = response.json().get("code") if response.content else None
            raise LonoraError(str(code or "workspace_request_invalid"), response.status_code)
        if response.status_code != 200:
            raise LonoraError("workspace_unavailable", 503)
        value = response.json()
        if not isinstance(value, dict):
            raise LonoraError("workspace_unavailable", 503)
        return value  # pyright: ignore[reportUnknownVariableType]

    async def run(
        self,
        scan: SecretScan,
        agent_id: str,
        command: str,
        *,
        background: bool = False,
        timeout_seconds: float | None = None,
        secrets: dict[str, str] | None = None,
        agent_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_id": agent_id, "command": command, "background": background}
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds
        if secrets:
            body["secrets"] = secrets
        if agent_token:
            body["agent_token"] = agent_token
        # The supervisor bounds the command itself; the transport waits a little longer.
        wait = (timeout_seconds or 600) + 30 if not background else 60
        result = cut_output(await self._call("POST", "/v1/run", body, wait))
        for stream in ("stdout", "stderr"):
            if isinstance(result.get(stream), str):
                result[stream] = trailing(scan, result[stream])
        return scan.data(result)

    async def processes(self, scan: SecretScan) -> dict[str, Any]:
        return scan.data(await self._call("GET", "/v1/processes", None, 30))

    async def stop(self, scan: SecretScan, pid: int, agent_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"pid": pid}
        if agent_id:
            body["agent_id"] = agent_id
        return scan.data(await self._call("POST", "/v1/processes/stop", body, 30))

    async def stop_all(self, scan: SecretScan, agent_id: str | None = None) -> dict[str, Any]:
        body = {"agent_id": agent_id} if agent_id else {}
        return scan.data(await self._call("POST", "/v1/processes/stop-all", body, 30))

    async def read_text(
        self, scan: SecretScan, agent_id: str, path: str, offset: int, limit: int
    ) -> dict[str, Any]:
        """A slice of a file as text, with every secret form replaced. The slice is read
        with a margin on both sides, so a secret crossing its edges is still found."""
        before = min(offset, MARGIN)
        value = await self._call(
            "POST",
            "/v1/files/read",
            {
                "agent_id": agent_id,
                "path": path,
                "offset": offset - before,
                "limit": min(limit + before + MARGIN, 2 * 1024 * 1024),
            },
            90,
        )
        if not value.get("ok"):
            return scan.data({"ok": False, "error": value.get("error", "")})
        data = base64.b64decode(value["content_base64"])
        # One decoding; the slice edges are found by decoding prefixes the same way,
        # holding back an incomplete character so it counts with the slice.
        text = data.decode("utf-8", "replace")
        start = chars(data[:before])
        end = chars(data[: before + limit])
        at_end = value["offset"] + len(data) >= value["size"] and before + limit >= len(data)
        if at_end:
            text = trailing(scan, text)
            end = len(text)
        return {
            "ok": True,
            "path": scan.text(path),
            "size": value["size"],
            "offset": offset,
            "truncated": offset + limit < value["size"],
            "binary": b"\0" in data[before : before + limit],
            "content": window(scan, text, start, max(start, end)),
        }

    async def read_bytes(self, scan: SecretScan, agent_id: str, path: str) -> bytes:
        """A whole file's bytes (an export). Refused when they carry a secret."""
        value = await self._call("POST", "/v1/files/read", {"agent_id": agent_id, "path": path}, 90)
        if not value.get("ok"):
            raise LonoraError("workspace_file_unreadable", 404)
        if value["truncated"]:
            raise LonoraError("workspace_file_too_large", 413)
        data = base64.b64decode(value["content_base64"])
        if scan.found(data) or scan.text(data.decode("utf-8", "replace")) != data.decode(
            "utf-8", "replace"
        ):
            raise LonoraError("workspace_file_holds_secret", 409)
        return data

    async def write(
        self, scan: SecretScan, agent_id: str, path: str, data: bytes, *, append: bool = False
    ) -> dict[str, Any]:
        body = {
            "agent_id": agent_id,
            "path": path,
            "content_base64": base64.b64encode(data).decode(),
            "append": append,
        }
        return scan.data(await self._call("POST", "/v1/files/write", body, 90))
