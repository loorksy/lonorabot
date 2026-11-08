"""Provider failure taxonomy shared by the model adapters and the model router.

Every provider failure becomes one ``ModelProviderError``. Its ``reason``
selects the router's recovery (retry the same provider, fall back, compact and
retry, or stop); its ``code`` stays one of Lonora's stable, owner-visible error
codes, so Run and Task recovery keep reading the codes they always read.

The reason taxonomy and the ordered classification (provider-typed codes, then
HTTP status refined by message, then message patterns) adapt Hermes Agent
``agent/error_classifier.py`` (``FailoverReason``, ``classify_api_error``), and
the ``Retry-After`` parsing adapts ``agent/retry_utils.py``
(``parse_retry_after_seconds``), source https://github.com/NousResearch/hermes-agent
at revision a9ff9799e273f525b82718cdc69fdec71b1dca5a. Lonora keeps a reduced
reason set with its own pattern tables, adds an output-limit reason carrying
the provider's stated maximum, and never stores provider message text (it can
echo request content) on the error.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, cast

from lonora_core.user_error import LonoraError


class FailureReason(StrEnum):
    """Why one provider request failed; the router maps it to a recovery."""

    # The credential itself is rejected (every model it could reach).
    AUTH = "auth"
    # The credential is valid but may not use this model.
    PERMISSION = "permission"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    CONTEXT_OVERFLOW = "context_overflow"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    MODEL_NOT_FOUND = "model_not_found"
    CONTENT_POLICY = "content_policy"
    FORMAT_ERROR = "format_error"
    # The requested output budget exceeds what the model accepts.
    OUTPUT_LIMIT = "output_limit"
    # Generation stopped at the output budget; incomplete calls are never used.
    TRUNCATED = "truncated"
    INVALID_RESPONSE = "invalid_response"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"


# Stable owner-visible code and API status for each reason.
CODES: dict[FailureReason, tuple[str, int]] = {
    FailureReason.AUTH: ("model_credentials_rejected", 502),
    FailureReason.PERMISSION: ("model_access_denied", 502),
    FailureReason.BILLING: ("model_billing_exhausted", 502),
    FailureReason.RATE_LIMIT: ("model_rate_limited", 429),
    FailureReason.OVERLOADED: ("model_provider_unavailable", 502),
    FailureReason.SERVER_ERROR: ("model_provider_unavailable", 502),
    FailureReason.TIMEOUT: ("model_provider_unavailable", 502),
    FailureReason.CONNECTION: ("model_provider_unavailable", 502),
    FailureReason.CONTEXT_OVERFLOW: ("context_limit_exceeded", 413),
    FailureReason.PAYLOAD_TOO_LARGE: ("context_limit_exceeded", 413),
    FailureReason.MODEL_NOT_FOUND: ("model_endpoint_unavailable", 502),
    FailureReason.CONTENT_POLICY: ("model_content_blocked", 502),
    FailureReason.FORMAT_ERROR: ("model_request_rejected", 502),
    FailureReason.OUTPUT_LIMIT: ("model_request_rejected", 502),
    FailureReason.TRUNCATED: ("model_output_truncated", 502),
    FailureReason.INVALID_RESPONSE: ("model_response_invalid", 502),
    FailureReason.NOT_CONFIGURED: ("model_not_configured", 409),
    FailureReason.UNKNOWN: ("model_provider_unavailable", 502),
}


class ModelProviderError(LonoraError):
    """A classified provider failure; ``code`` is the stable Lonora code.

    ``inferred`` marks a reason read only from message wording on an otherwise
    generic response (a plain 400/422 or an untyped stream error event). It
    still selects the recovery, but it is not evidence strong enough to take a
    model or credential offline for every Agent.
    """

    def __init__(
        self,
        reason: FailureReason,
        *,
        http_status: int | None = None,
        retry_after: float | None = None,
        output_limit: int | None = None,
        provider_type: str | None = None,
        inferred: bool = False,
    ):
        code, status = CODES[reason]
        super().__init__(code, status, diagnostic_type=provider_type)
        self.reason = reason
        self.http_status = http_status
        self.retry_after = retry_after
        self.output_limit = output_limit
        self.inferred = inferred


def reason_of(error: LonoraError) -> FailureReason | None:
    """The classified reason, or ``None`` for an unclassified Lonora error."""
    return error.reason if isinstance(error, ModelProviderError) else None


# Lowercased substrings. Order of use is fixed in ``classify_failure``.
_BILLING = (
    "insufficient_quota",
    "insufficient quota",
    "insufficient credits",
    "insufficient_credits",
    "insufficient balance",
    "credit balance",
    "credits exhausted",
    "billing hard limit",
    "billing_hard_limit",
    "billing_not_active",
    "check your plan and billing",
    "payment required",
    "exceeded your current quota",
    "budget limit exceeded",
    "spend limit",
    "balance_depleted",
    "out of credits",
)
_RATE_LIMIT = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "throttl",
    "requests per minute",
    "tokens per minute",
    "requests per day",
    "resource_exhausted",
    "resource exhausted",
)
_OVERLOADED = (
    "overloaded",
    "at capacity",
    "over capacity",
    "temporarily unavailable",
    "server is busy",
    "service unavailable",
)
_PAYLOAD = (
    "request_too_large",
    "request too large",
    "payload too large",
    "request entity too large",
    "request exceeds the maximum size",
)
_CONTEXT = (
    "context length",
    "context_length",
    "context size",
    "context window",
    "context limit",
    "maximum context",
    "prompt is too long",
    "prompt too long",
    "prompt exceeds max length",
    "too many tokens",
    "token limit",
    "reduce the length",
    "input is too long",
    "input too long",
    "maximum allowed input length",
    "maximum number of input tokens",
    "max_model_len",
)
_OUTPUT_FIELDS = (
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
    "maximum output",
    "completion tokens",
    "output tokens",
)
_UNSUPPORTED = ("unsupported parameter", "not supported", "unknown parameter", "unrecognized")
_CONTENT = (
    "content_filter",
    "content filter",
    "content policy",
    "content_policy",
    "usage policies",
    "flagged",
    "safety system",
    "responsibleaipolicyviolation",
    "data_inspection_failed",
    "inappropriate content",
)
_MODEL_NOT_FOUND = (
    "model_not_found",
    "model not found",
    "invalid model",
    "unknown model",
    "no such model",
    "is not a valid model",
    "unsupported model",
    "no endpoints found",
)
# Wording that says the key itself is rejected; decisive on a 403.
_INVALID_KEY = (
    "invalid api key",
    "invalid_api_key",
    "invalid x-api-key",
    "incorrect api key",
    "api key not valid",
    "api_key_invalid",
    "invalid authentication",
    "authentication failed",
    "authentication_error",
)
_AUTH = (*_INVALID_KEY, "unauthorized")
# "The model `x` does not exist": the word "model" must lead the phrase, so a
# missing tool_call_id or file id is not read as a missing model.
_MODEL_MISSING = re.compile(r"\bmodel\b[^.;\n]{0,120}?\bdoes not exist")
# Structured provider error types and codes that are decisive on their own.
_TYPED: dict[str, FailureReason] = {
    "authentication_error": FailureReason.AUTH,
    # Anthropic: this key may not use this model; other models may answer.
    "permission_error": FailureReason.PERMISSION,
    "invalid_api_key": FailureReason.AUTH,
    "billing_error": FailureReason.BILLING,
    "insufficient_quota": FailureReason.BILLING,
    "rate_limit_error": FailureReason.RATE_LIMIT,
    "rate_limit_exceeded": FailureReason.RATE_LIMIT,
    "overloaded_error": FailureReason.OVERLOADED,
    "api_error": FailureReason.SERVER_ERROR,
    "server_error": FailureReason.SERVER_ERROR,
    "timeout_error": FailureReason.TIMEOUT,
    "request_too_large": FailureReason.PAYLOAD_TOO_LARGE,
    "not_found_error": FailureReason.MODEL_NOT_FOUND,
    "model_not_found": FailureReason.MODEL_NOT_FOUND,
    "context_length_exceeded": FailureReason.CONTEXT_OVERFLOW,
    "content_filter": FailureReason.CONTENT_POLICY,
    "content_policy_violation": FailureReason.CONTENT_POLICY,
}
_OUTPUT_LIMIT_PATTERNS = (
    re.compile(r"at most (\d+) (?:completion|output) tokens"),
    re.compile(r">\s*(\d+),? which is the maximum"),
    re.compile(r"range of max_\w+ is \[\s*\d+\s*,\s*(\d+)\s*\]"),
    re.compile(r"less than or equal to (\d+)"),
    re.compile(r"maximum (?:allowed )?(?:number of )?(?:output|completion) tokens (?:is|of) (\d+)"),
)
_RETRY_IN_MESSAGE = re.compile(
    r"(?:retry after|try again in)\s*(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds)?\b"
)
# A provider-declared wait longer than this is not trusted as stated.
MAXIMUM_RETRY_AFTER_SECONDS = 3600.0
_MESSAGE_LIMIT = 4000


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Seconds from a ``Retry-After`` value: delta-seconds or an HTTP date.

    Missing, unparseable, zero or expired values give ``None``: no usable wait.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    if seconds != seconds or seconds <= 0:  # NaN or no wait
        return None
    return min(seconds, MAXIMUM_RETRY_AFTER_SECONDS)


def retry_after_from_headers(headers: Mapping[str, str] | None) -> float | None:
    if not headers:
        return None
    lowered = {key.lower(): value for key, value in headers.items()}
    milliseconds = lowered.get("retry-after-ms")
    if milliseconds is not None:
        try:
            value = float(milliseconds) / 1000
        except ValueError:
            value = 0.0
        if value > 0:
            return min(value, MAXIMUM_RETRY_AFTER_SECONDS)
    return parse_retry_after(lowered.get("retry-after"))


def _retry_after_from_message(text: str) -> float | None:
    match = _RETRY_IN_MESSAGE.search(text)
    if not match:
        return None
    seconds = float(match.group(1))
    if (match.group(2) or "").startswith("m"):
        seconds /= 1000
    return min(seconds, MAXIMUM_RETRY_AFTER_SECONDS) if seconds > 0 else None


def decode_payload(body: str | bytes | None) -> Any:
    if body is None:
        return None
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    text = text[:65536]
    try:
        return json.loads(text)
    except ValueError:
        return text


def error_details(payload: Any) -> tuple[str, str, str, int | None]:
    """``(type, code, message, numeric code)`` from Anthropic/OpenAI/OpenRouter shapes."""
    if isinstance(payload, str):
        return "", "", payload, None
    if not isinstance(payload, dict):
        return "", "", "", None
    body = cast(dict[str, Any], payload)
    nested = body.get("error")
    error: dict[str, Any] = cast(dict[str, Any], nested) if isinstance(nested, dict) else body
    if isinstance(nested, str):
        error = {"message": nested}
    kind = error.get("type")
    code = error.get("code")
    message = error.get("message")
    numeric = code if isinstance(code, int) and not isinstance(code, bool) else None
    parts = [message if isinstance(message, str) else ""]
    metadata = error.get("metadata")
    if isinstance(metadata, dict):
        raw = cast(dict[str, Any], metadata).get("raw")
        if isinstance(raw, str):
            # OpenRouter relays the upstream provider's own error text here.
            parts.append(raw)
    return (
        kind if isinstance(kind, str) else "",
        code if isinstance(code, str) else "",
        " ".join(part for part in parts if part),
        numeric,
    )


def _has(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _output_limit(text: str) -> int | None:
    for pattern in _OUTPUT_LIMIT_PATTERNS:
        match = pattern.search(text)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def _by_message(text: str) -> tuple[FailureReason, int | None] | None:
    if _has(text, _PAYLOAD):
        return FailureReason.PAYLOAD_TOO_LARGE, None
    if _has(text, _OUTPUT_FIELDS) and not _has(text, _CONTEXT) and not _has(text, _UNSUPPORTED):
        return FailureReason.OUTPUT_LIMIT, _output_limit(text)
    if _has(text, _CONTEXT):
        return FailureReason.CONTEXT_OVERFLOW, None
    if _has(text, _BILLING) and not _has(text, _RATE_LIMIT):
        return FailureReason.BILLING, None
    if _has(text, _CONTENT):
        return FailureReason.CONTENT_POLICY, None
    if _has(text, _MODEL_NOT_FOUND) or _MODEL_MISSING.search(text):
        return FailureReason.MODEL_NOT_FOUND, None
    if _has(text, _RATE_LIMIT):
        return FailureReason.RATE_LIMIT, None
    if _has(text, _OVERLOADED):
        return FailureReason.OVERLOADED, None
    if _has(text, _AUTH):
        return FailureReason.AUTH, None
    return None


def _by_status(status: int, text: str) -> tuple[FailureReason, int | None, bool]:
    """``(reason, output limit, inferred)`` for a failed HTTP response."""
    if status == 401:
        return FailureReason.AUTH, None, False
    if status == 402:
        return FailureReason.BILLING, None, False
    if status == 403:
        if _has(text, _BILLING):
            return FailureReason.BILLING, None, False
        if _has(text, _CONTENT):
            return FailureReason.CONTENT_POLICY, None, False
        if _has(text, _INVALID_KEY):
            return FailureReason.AUTH, None, False
        # A 403 without invalid-key wording is a refusal for this model (or
        # resource), not proof that the key is bad for every model.
        return FailureReason.PERMISSION, None, False
    if status == 404:
        return FailureReason.MODEL_NOT_FOUND, None, False
    if status == 408:
        return FailureReason.TIMEOUT, None, False
    if status == 409:
        return FailureReason.SERVER_ERROR, None, False
    if status == 413:
        return FailureReason.PAYLOAD_TOO_LARGE, None, False
    if status == 429:
        if _has(text, _OVERLOADED):
            return FailureReason.OVERLOADED, None, False
        if _has(text, _BILLING) and not _has(text, _RATE_LIMIT):
            return FailureReason.BILLING, None, False
        return FailureReason.RATE_LIMIT, None, False
    if status in {503, 529} or (status >= 500 and _has(text, _OVERLOADED)):
        return FailureReason.OVERLOADED, None, False
    if status == 504:
        return FailureReason.TIMEOUT, None, False
    if status >= 500:
        return FailureReason.SERVER_ERROR, None, False
    if status >= 400:
        found = _by_message(text)
        if found is not None:
            return found[0], found[1], True
        return FailureReason.FORMAT_ERROR, None, False
    return FailureReason.UNKNOWN, None, False


def classify_failure(
    status: int | None, payload: Any, headers: Mapping[str, str] | None = None
) -> ModelProviderError:
    """Classify one failed response or in-stream error event.

    ``status`` is ``None`` for an error event inside a successful stream; a
    numeric ``code`` in the event (as OpenRouter sends) stands in for it.
    """
    kind, code, message, numeric = error_details(payload)
    text = " ".join(part for part in (kind, code, message) if part).lower()[:_MESSAGE_LIMIT]
    effective = status if status is not None else numeric
    typed = _TYPED.get(code) or _TYPED.get(kind)
    output_limit: int | None = None
    inferred = False
    if typed is not None and (effective is None or effective >= 400):
        reason = typed
    elif effective is not None and effective >= 300:
        reason, output_limit, inferred = _by_status(effective, text)
    else:
        # An error event mid-stream without a type: read the message, and
        # otherwise treat it as a provider-side interruption.
        found = _by_message(text)
        reason, output_limit = found or (FailureReason.SERVER_ERROR, None)
        inferred = found is not None
    if reason is FailureReason.FORMAT_ERROR or (
        reason in {FailureReason.SERVER_ERROR, FailureReason.UNKNOWN}
        and effective is not None
        and 400 <= effective < 500
    ):
        refined = _by_message(text)
        if refined is not None:
            reason, output_limit = refined
            inferred = True
    retry_after: float | None = None
    if reason in {
        FailureReason.RATE_LIMIT,
        FailureReason.OVERLOADED,
        FailureReason.SERVER_ERROR,
        FailureReason.TIMEOUT,
    }:
        retry_after = retry_after_from_headers(headers) or _retry_after_from_message(text)
    return ModelProviderError(
        reason,
        http_status=effective,
        retry_after=retry_after,
        output_limit=output_limit,
        provider_type=kind or code or None,
        inferred=inferred,
    )


def response_failure(
    status: int, body: str | bytes | None, headers: Mapping[str, str] | None
) -> ModelProviderError:
    return classify_failure(status, decode_payload(body), headers)


# Stop reasons that mean generation was cut off at the output budget or window.
TRUNCATION_STOPS = frozenset({"max_tokens", "length", "model_context_window_exceeded"})
# Stop reasons that mean a provider safety system withheld the answer.
REFUSAL_STOPS = frozenset({"refusal", "content_filter"})
