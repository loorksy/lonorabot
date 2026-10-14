"""Public, read-only Expo Updates protocol v1; publication stays an offline operation."""

import base64
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response
from lonora_core.user_error import LonoraError
from lonora_security.ota_storage import read_ota_file
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/mobile/updates", tags=["mobile_updates"])
HEADERS = {"expo-protocol-version": "1", "expo-sfv-version": "0", "Cache-Control": "no-store"}
RUNTIME = re.compile(r"[a-fA-F0-9]{40,64}")
ASSET = re.compile(r"([a-f0-9]{64})\.([a-zA-Z0-9]{1,12})")


def uuid_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("UUID required")
    parsed = str(UUID(value))
    if parsed != value.lower():
        raise ValueError("canonical UUID required")
    return parsed


def signature_header(raw: bytes) -> str:
    value = raw.decode("ascii").strip()
    decoded = base64.b64decode(value, validate=True)
    if not 128 <= len(decoded) <= 1024:
        raise ValueError("invalid RSA signature")
    return f'sig="{value}", keyid="main"'


def cohort_selected(header: str | None, percentage: int) -> bool:
    if percentage == 100:
        return True
    if not header or len(header) > 2048:
        return False
    match = re.fullmatch(r'\s*lonora-client="([0-9a-fA-F-]+)"\s*', header)
    if not match:
        return False
    try:
        client = uuid_value(match[1])
    except ValueError:
        return False
    return int.from_bytes(hashlib.sha256(client.encode()).digest()[:8], "big") % 100 < percentage


@router.get("")
async def update(request: Request) -> Response:
    platform = request.headers.get("expo-platform")
    runtime = request.headers.get("expo-runtime-version", "")
    channel = request.headers.get("expo-channel-name")
    if (
        request.headers.get("expo-protocol-version") != "1"
        or platform not in {"android", "ios"}
        or channel not in {"preview", "production"}
        or RUNTIME.fullmatch(runtime) is None
    ):
        raise LonoraError("mobile_update_request_invalid", 400)
    root = request.app.state.runtime.settings.ota_root
    path = ("releases", channel, platform, runtime)
    try:
        pointer = json.loads(
            await run_in_threadpool(read_ota_file, root, (*path, "active.json"), 8192)
        )
        percentage = pointer.get("rollout_percentage", 100)
        if type(percentage) is not int or not 0 <= percentage <= 100:
            raise ValueError("invalid rollout")
        selected = cohort_selected(request.headers.get("expo-extra-params"), percentage)
        release = pointer.get("release_id") if selected else pointer.get("previous_release_id")
        if not release:
            return Response(status_code=204, headers=HEADERS)
        release = uuid_value(release)
        if request.headers.get("expo-current-update-id", "").lower() == release:
            return Response(status_code=204, headers=HEADERS)
        if pointer.get("rollback_to_embedded") is True:
            payload = await run_in_threadpool(
                read_ota_file, root, (*path, release, "directive.json"), 8192
            )
            directive = json.loads(payload)
            if directive.get("type") != "rollBackToEmbedded":
                raise ValueError("invalid rollback directive")
            signature = signature_header(
                await run_in_threadpool(
                    read_ota_file, root, (*path, release, "directive.sig"), 4096
                )
            )
            boundary = "lonora-ota-directive"
            body = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="directive"\r\n'
                f"Content-Type: application/json\r\nexpo-signature: {signature}\r\n\r\n"
            ).encode()
            body += payload + f"\r\n--{boundary}--\r\n".encode()
            return Response(
                body, headers={**HEADERS, "Content-Type": f"multipart/mixed; boundary={boundary}"}
            )
        payload = await run_in_threadpool(
            read_ota_file, root, (*path, release, "manifest.json"), 2_000_000
        )
        manifest = json.loads(payload)
        if manifest.get("id") != release or manifest.get("runtimeVersion") != runtime:
            raise ValueError("manifest target mismatch")
        signature = signature_header(
            await run_in_threadpool(read_ota_file, root, (*path, release, "manifest.sig"), 4096)
        )
        return Response(
            payload,
            media_type="application/expo+json",
            headers={**HEADERS, "expo-signature": signature},
        )
    except LonoraError as error:
        if error.code == "mobile_update_not_found":
            return Response(status_code=204, headers=HEADERS)
        raise
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise LonoraError("mobile_update_invalid", 503) from None


@router.get("/assets/{filename}")
async def asset(request: Request, filename: str) -> Response:
    match = ASSET.fullmatch(filename)
    if match is None:
        raise LonoraError("mobile_update_asset_not_found", 404)
    payload = await run_in_threadpool(
        read_ota_file,
        request.app.state.runtime.settings.ota_root,
        ("assets", filename),
        100_000_000,
    )
    if hashlib.sha256(payload).hexdigest() != match[1]:
        raise LonoraError("mobile_update_invalid", 503)
    return Response(
        payload,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "ETag": f'"{match[1]}"',
        },
    )
