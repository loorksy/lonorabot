"""RSS and Atom news feeds through the SSRF-safe public client.

Every request, including each redirect target, goes through ``public_get``: HTTPS only,
the host resolved once and every address checked public, the connection pinned to that
address. A document type declaration or entity is refused before parsing, so no entity
expansion or external fetch can happen. Item text is bounded and stripped of markup;
it is untrusted evidence, never instructions. Errors carry stable codes, never the
feed URL (it may contain a token).
"""

import html
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.public_http import public_get

MAXIMUM_FEED_BYTES = 2 * 1024 * 1024
MAXIMUM_REDIRECTS = 3
MAXIMUM_ITEMS = 50
TAG = re.compile(r"<[^>]{0,2000}>")


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str | None
    published: str | None
    summary: str


def plain(text: str | None, limit: int) -> str:
    value = html.unescape(TAG.sub(" ", text or ""))
    return " ".join(value.split())[:limit]


def safe_link(value: str | None, base: str) -> str | None:
    if not value:
        return None
    link = urljoin(base, value.strip())
    parsed = urlsplit(link)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or len(link) > 2048:
        return None
    return parsed._replace(fragment="").geturl()


def iso_time(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        # Atom dates are RFC 3339 already; anything else stays unparsed (None).
        return text[:40] if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.+\-Z]{5,30}", text) else None
    return moment.isoformat() if moment.tzinfo is not None else None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(element: ElementTree.Element | None, name: str) -> ElementTree.Element | None:
    if element is None:
        return None
    return next((item for item in element if local(item.tag) == name), None)


def text_of(element: ElementTree.Element | None, *names: str) -> str | None:
    for name in names:
        found = child(element, name)
        if found is not None:
            return "".join(found.itertext())
    return None


def atom_link(entry: ElementTree.Element) -> str | None:
    return next(
        (
            item.get("href")
            for item in entry
            if local(item.tag) == "link" and item.get("rel", "alternate") == "alternate"
        ),
        None,
    )


def parse_feed(body: bytes, base: str) -> tuple[str, list[FeedItem]]:
    """The feed's title and items (RSS 2.0, RSS 1.0 or Atom); ``news_feed_invalid``
    for anything else."""
    if b"<!doctype" in body[:4096].lower() or b"<!entity" in body.lower():
        raise LonoraError("news_feed_invalid", 502)
    try:
        root = ElementTree.fromstring(body)
    except (ElementTree.ParseError, ValueError, RecursionError):
        raise LonoraError("news_feed_invalid", 502) from None
    kind = local(root.tag)
    if kind in {"rss", "RDF"}:
        title = text_of(child(root, "channel"), "title")
        entries = [item for item in root.iter() if local(item.tag) == "item"]
    elif kind == "feed":
        title = text_of(root, "title")
        entries = [item for item in root if local(item.tag) == "entry"]
    else:
        raise LonoraError("news_feed_invalid", 502)
    items = [
        FeedItem(
            title=plain(text_of(entry, "title"), 300),
            link=safe_link(atom_link(entry) if kind == "feed" else text_of(entry, "link"), base),
            published=iso_time(text_of(entry, "pubDate", "published", "updated", "date")),
            summary=plain(text_of(entry, "description", "summary", "content"), 600),
        )
        for entry in entries[:MAXIMUM_ITEMS]
    ]
    return plain(title, 200), items


async def read_feed(url: str) -> tuple[str, list[FeedItem]]:
    """Fetch and parse one public feed, following at most three checked redirects."""
    target = url
    for _ in range(MAXIMUM_REDIRECTS + 1):
        try:
            response = await public_get(target, maximum_bytes=MAXIMUM_FEED_BYTES)
        except LonoraError as error:
            if error.code == "research_source_too_large":
                raise LonoraError("news_feed_too_large", 413) from None
            raise
        except httpx.TimeoutException:
            raise LonoraError("news_feed_timeout", 504) from None
        except (httpx.HTTPError, OSError):
            # Transport messages can echo the feed URL, which may carry a token.
            raise LonoraError("news_feed_unavailable", 502) from None
        if response.status in {301, 302, 303, 307, 308}:
            location = next(
                (value for name, value in response.headers.items() if name.lower() == "location"),
                None,
            )
            if not location:
                raise LonoraError("news_feed_unavailable", 502)
            target = urljoin(target, location)
            continue
        if response.status != 200:
            raise LonoraError("news_feed_unavailable", 502)
        return parse_feed(response.body, target)
    raise LonoraError("news_feed_redirect_limit", 502)
