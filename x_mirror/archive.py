import re
import zipfile
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import orjson

from x_mirror.media import mirror_photo_bytes
from x_mirror.models import Media, Post

KNOWN_MEDIA_TYPES = {"photo": "photo", "animated_gif": "gif", "video": "video"}
# Trailing, not "contains": X's client appends the quoted permalink to the end of the
# text, so only a status URL at the very end of the (already-expanded) text is a quote.
# A status URL earlier in the text is just an ordinary link the author typed or shared.
STATUS_URL = re.compile(r"https?://(?:x|twitter)\.com/[^/\s]+/status/(\d+)$")
ARCHIVE_TIME_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def _load_tweets(zf: zipfile.ZipFile) -> list[dict]:
    raw = zf.read("data/tweets.js").decode("utf-8")
    return orjson.loads(raw[raw.index("["):])


def _media_index(zf: zipfile.ZipFile) -> dict[str, str]:
    # Keyed by archive basename (e.g. "<tweet_id>-<hash>.<ext>"), not by tweet id: the
    # hash has no relationship to attachment order, so lookups must be by exact filename.
    return {
        Path(name).name: name
        for name in zf.namelist()
        if name.startswith("data/tweets_media/")
    }


def _parse_media(tweet: dict, media_index: dict[str, str], zf: zipfile.ZipFile,
                 media_dir: Path) -> list[Media]:
    entries = tweet.get("extended_entities", {}).get("media", [])
    permalink = f"https://x.com/i/status/{tweet['id_str']}"
    media: list[Media] = []
    for index, entry in enumerate(entries):
        kind = KNOWN_MEDIA_TYPES.get(entry["type"])
        if kind is None:
            raise ValueError(f"tweet {tweet['id_str']}: unrecognized media type {entry['type']!r}")

        local_path = None
        if kind != "video":
            expected_name = f"{tweet['id_str']}-{Path(entry['media_url_https']).name}"
            name = media_index.get(expected_name)
            if name is None:
                raise ValueError(f"tweet {tweet['id_str']}: no archive file for {expected_name}")
            local_path = mirror_photo_bytes(
                tweet["id_str"], index, Path(name).suffix, zf.read(name), media_dir
            )
        media.append(Media(
            kind=kind,
            local_path=local_path,
            source_url=permalink,
            alt=entry.get("ext_alt_text"),
        ))
    return media


def strip_status_url(text: str, status_id: str, count: int) -> str:
    """Remove links to a given status, wherever they sit in the text. `\\S*` because the
    id can carry a suffix (`/photo/1`) or query params, and the `(?!\\d)` keeps a longer
    id starting with the same digits from matching."""
    pattern = re.compile(
        rf"\s*https?://(?:x|twitter)\.com/[^/\s]+/status/{re.escape(status_id)}(?!\d)\S*"
    )
    return pattern.sub("", text, count=count).strip()


def _expand_links(text: str, urls: list[dict], post_id: str) -> tuple[str, str | None]:
    """Expand every t.co link. A status URL only becomes quoted_id if it's the trailing
    URL in the resulting text (a quote-tweet permalink); elsewhere it stays as a link."""
    # Both the archive's full_text and the API's text HTML-escape &, < and > ("R&D"
    # arrives as "R&amp;D"). Unescape before expansion so an expanded_url that happens
    # to contain a literal "&amp;" is not corrupted by a later unescape.
    text = unescape(text)
    for url in urls:
        text = text.replace(url["url"], url["expanded_url"])
    # A post's media (and a Premium long post's truncated preview) carries a link back to
    # the post itself. Rendered, that's a self-referential link that routes the reader
    # through X — the redirect that expanding t.co exists to avoid.
    text = strip_status_url(text, post_id, 0)
    quoted_id = None
    match = STATUS_URL.search(text)
    if match:
        quoted_id = match.group(1)
        text = text[:match.start()].strip()
    return text, quoted_id


def _is_retweet(tweet: dict) -> bool:
    # Real archives carry no retweeted_status field (unlike the API); the only marker
    # is the "RT @" text prefix.
    return "retweeted_status" in tweet or tweet["full_text"].startswith("RT @")


def _parse_created_at(tweet: dict) -> datetime:
    return datetime.strptime(tweet["created_at"], ARCHIVE_TIME_FORMAT).astimezone(timezone.utc)


def _load_notes(zf: zipfile.ZipFile) -> dict[str, list[dict]]:
    """Full text of Premium long posts, keyed by ISO creation instant. tweets.js
    truncates them at ~280 chars with a trailing ellipsis."""
    try:
        raw = zf.read("data/note-tweet.js").decode("utf-8")
    except KeyError:
        return {}
    notes: dict[str, list[dict]] = {}
    for entry in orjson.loads(raw[raw.index("["):]):
        note = entry["noteTweet"]
        notes.setdefault(note["createdAt"], []).append(note)
    return notes


def _apply_note(tweet: dict, notes: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    """Return (text, urls) for the tweet, substituting the note-tweet's full text when
    one matches. Notes carry no tweet id, so the join is by creation instant, verified
    by text prefix (instants can collide)."""
    full_text = tweet["full_text"]
    entities = tweet.get("entities", {})
    archive_urls = entities.get("urls", []) + entities.get("media", [])
    if "…" not in full_text:
        return full_text, archive_urls

    instant = _parse_created_at(tweet).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    # The note text omits the reply's leading @mentions, and the same link is shortened
    # to a different t.co id in full_text than in the note — so strip mentions and cut
    # the prefix at the first t.co before comparing.
    prefix = unescape(full_text.split("…")[0])
    prefix = re.sub(r"\A(?:@\w+\s+)+", "", prefix)
    prefix = prefix.split("https://t.co/")[0].strip()
    candidates = notes.get(instant, [])
    if not prefix and len(candidates) == 1:
        return _note_payload(candidates[0], entities)
    for note in candidates:
        if note["core"]["text"].startswith(prefix):
            return _note_payload(note, entities)
    return full_text, archive_urls


def _note_payload(note: dict, entities: dict) -> tuple[str, list[dict]]:
    note_urls = [{"url": u["shortUrl"], "expanded_url": u["expandedUrl"]}
                 for u in note["core"].get("urls", [])]
    # entities.media still applies: the media t.co is not part of the note text,
    # but the truncated preview's own links are superseded by the note's.
    return note["core"]["text"], note_urls + entities.get("media", [])


def parse_archive(zip_path: Path, media_dir: Path, start_year: int) -> tuple[list[Post], set[str]]:
    with zipfile.ZipFile(zip_path) as zf:
        raw_tweets = [
            entry["tweet"] for entry in _load_tweets(zf)
            if _parse_created_at(entry["tweet"]).year >= start_year
        ]
        media_index = _media_index(zf)
        notes = _load_notes(zf)

        owned_ids = {t["id_str"] for t in raw_tweets if not _is_retweet(t)}
        posts: list[Post] = []
        pending: set[str] = set()

        for tweet in raw_tweets:
            if _is_retweet(tweet):
                continue
            # entities.media carries the media attachment's own t.co, which never appears
            # in entities.urls — unexpanded it renders as a live t.co link on the page.
            raw_text, urls = _apply_note(tweet, notes)
            text, quoted_id = _expand_links(raw_text, urls, tweet["id_str"])
            parent_id = tweet.get("in_reply_to_status_id_str")
            if parent_id is not None and parent_id not in owned_ids:
                pending.add(parent_id)
            if quoted_id is not None and quoted_id not in owned_ids:
                pending.add(quoted_id)

            posts.append(Post(
                id=tweet["id_str"],
                created_at=_parse_created_at(tweet),
                text=text,
                media=_parse_media(tweet, media_index, zf, media_dir),
                in_reply_to_id=parent_id,
                quoted_id=quoted_id,
                thread_id="",
            ))

    _assign_thread_ids(posts, owned_ids)
    return posts, pending


def _assign_thread_ids(posts: list[Post], owned_ids: set[str]) -> None:
    by_id = {p.id: p for p in posts}
    for post in posts:
        root = post
        seen = {root.id}
        # The seen set guards against a cycle in the reply graph, which would otherwise hang the build.
        while root.in_reply_to_id in owned_ids and root.in_reply_to_id not in seen:
            seen.add(root.in_reply_to_id)
            root = by_id[root.in_reply_to_id]
        post.thread_id = root.id
