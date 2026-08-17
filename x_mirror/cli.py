import os
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import fire
import httpx

from x_mirror import config
from x_mirror.api import XClient
from x_mirror.archive import KNOWN_MEDIA_TYPES, _expand_links, parse_archive, strip_status_url
from x_mirror.media import delete_media, download, mirror_avatar_bytes, mirror_photo_bytes
from x_mirror.models import Author, Media, Post, Ref, State
from x_mirror.store import Store

STATUS_ID = re.compile(r"/status/(\d+)")


def _extract_post_id(target: str | int) -> str:
    # str(): fire parses a bare-digit argument as an int, so `forget 1933` arrives
    # as an int while the URL form arrives as a str.
    # Mobile "Copy link" and desktop URLs both carry query params (?s=20, ?t=..&s=..)
    # and path suffixes (/photo/1) after the id, so anchor on /status/ instead of the
    # end of the string. A bare id (no URL at all) is accepted as its own case.
    text = str(target)
    match = STATUS_ID.search(text)
    if match is not None:
        return match.group(1)
    stripped = text.strip()
    if stripped.isdigit():
        return stripped
    raise ValueError(f"could not find a status id in {target!r}")


def _store() -> Store:
    return Store(config.DATA_DIR)


def _client() -> XClient:
    return XClient(os.environ.get("X_BEARER_TOKEN", ""))


def resolve_forget_targets(store: Store, post_id: str, scope: str | None) -> set[str]:
    if not any(p.id == post_id for p in store.all_posts()):
        raise KeyError(f"post {post_id} is not mirrored")
    below = {p.id for p in store.descendants(post_id)}
    if not below:
        return {post_id}
    if scope is None:
        raise ValueError("scope is required when the post has descendants")
    if scope == "post":
        return {post_id}
    if scope == "thread":
        return {post_id} | below
    raise ValueError(f"unknown scope {scope!r}; use 'post' or 'thread'")


def _prompt_for_scope(post_id: str, below_count: int) -> str:
    print(f"Post {post_id} is part of a thread and has {below_count} posts below it.")
    print("  [p] this post only")
    print(f"  [t] this post and the {below_count} below it")
    print("  [c] cancel")
    answer = input("> ").strip().lower()
    if answer == "p":
        return "post"
    if answer == "t":
        return "thread"
    sys.exit("cancelled")


def _check_media_exists(media: list[Media], repo_root: Path) -> None:
    # Mirrors delete_media's own containment check but never unlinks anything, so every
    # targeted post can be validated before the first file is touched.
    media_tree = repo_root / "assets" / "x"
    for item in media:
        if item.local_path is None:
            continue
        path = (repo_root / item.local_path.lstrip("/")).resolve()
        try:
            path.relative_to(media_tree)
        except ValueError:
            raise ValueError(f"local_path {item.local_path} escapes media directory")
        if not path.is_file():
            raise FileNotFoundError(f"{path} does not exist")


def _check_no_surviving_quotes(all_posts: list[Post], ids: set[str]) -> None:
    # A quoted post that resolves to nothing is fatal to the whole site build, not just
    # /x/ (_plugins/x_generator.rb raises), and hydrate can't repair it: the id is long
    # gone from pending_ref_ids. So removing a self-quoted post is refused outright.
    quoting = [p.id for p in all_posts if p.id not in ids and p.quoted_id in ids]
    if quoting:
        raise ValueError(
            f"post(s) {', '.join(sorted(quoting))} quote {', '.join(sorted(ids))} and would "
            "survive this removal, leaving a quote that resolves to nothing — which fails "
            "every jekyll build, not just /x/. Forget the quoting post(s) first."
        )


def forget(target: str, scope: str | None = None) -> None:
    """Remove a post (and optionally its thread descendants) from the mirror."""
    post_id = _extract_post_id(target)

    store = _store()
    below = store.descendants(post_id)
    if below and scope is None:
        scope = _prompt_for_scope(post_id, len(below))

    ids = resolve_forget_targets(store, post_id, scope)
    all_posts = store.all_posts()
    targets = [p for p in all_posts if p.id in ids]
    _check_no_surviving_quotes(all_posts, ids)
    # Pre-flight every file across every targeted post before deleting any of them, then
    # delete before touching the store: a mid-way divergence is caught with nothing
    # half-done, and the JSON still describes what's on disk if something does fail.
    for post in targets:
        _check_media_exists(post.media, config.REPO_ROOT)
    for post in targets:
        for path in delete_media(post.media, config.REPO_ROOT):
            print(f"removed {path}")
    for post in store.remove_posts(ids):
        print(f"removed post {post.id}")


def curate(target: str, remove: bool = False) -> None:
    """Add (or with --remove, drop) a mirrored post from the curated view. The curate
    button on /x/ pages edits the same _data/x/curated.json by dispatching curate.yml,
    which runs this command."""
    post_id = _extract_post_id(target)
    store = _store()
    if not any(p.id == post_id for p in store.all_posts()):
        raise KeyError(f"post {post_id} is not mirrored")
    curated = store.load_curated()
    if remove:
        if post_id not in curated:
            raise KeyError(f"post {post_id} is not curated")
        curated.remove(post_id)
    elif post_id not in curated:
        curated.append(post_id)
    store.save_curated(curated)
    print(f"{'removed' if remove else 'curated'} {post_id} ({len(curated)} curated)")


def _mirror_avatar(user: dict, http: httpx.Client) -> str:
    # profile_image_url points at the 48px "_normal" crop; dropping the suffix
    # gives the original upload.
    url = user["profile_image_url"].replace("_normal", "")
    return mirror_avatar_bytes(user["username"], Path(url).suffix,
                               download(http, url), config.AVATAR_DIR)


def backfill(archive: str) -> None:
    store = _store()
    posts, pending = parse_archive(Path(archive), config.MEDIA_DIR, config.START_YEAR)
    added = store.upsert_posts(posts)
    user = _client().fetch_user(config.HANDLE)
    with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS) as http:
        avatar_path = _mirror_avatar(user, http)
    newest = max((p.id for p in posts), key=int)
    store.save_state(State(user_id=user["id"], last_synced_id=newest,
                           avatar_path=avatar_path, pending_ref_ids=sorted(pending)))
    print(f"backfilled {added} posts, {len(pending)} refs pending hydration")
    hydrate()


def hydrate() -> None:
    store = _store()
    state = store.load_state()
    if not state.pending_ref_ids:
        print("nothing to hydrate")
        return

    refs = store.load_refs()
    # A Ref is captured once and never re-checked, so anything already in refs.json
    # doesn't need a billed re-read even if it lingers in pending_ref_ids.
    to_fetch = [ref_id for ref_id in state.pending_ref_ids if ref_id not in refs]
    found, missing = _client().lookup_tweets(to_fetch) if to_fetch else ([], set())

    with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS) as http:
        for tweet in found:
            author_payload = tweet["_author"]
            avatar_path = _mirror_avatar(author_payload, http)
            refs[tweet["id"]] = Ref(
                id=tweet["id"],
                author=Author(handle=author_payload["username"],
                              display_name=author_payload["name"],
                              avatar_path=avatar_path),
                created_at=datetime.fromisoformat(
                    tweet["created_at"].replace("Z", "+00:00")),
                text=unescape(tweet["text"]),
                # Mirrored locally like a post's own media: a pbs.twimg.com URL reaching
                # a rendered parent/quote card would break the privacy invariant.
                media=_media_from_tweet(tweet, http),
                unavailable=False,
            )

    for ref_id in missing:
        refs[ref_id] = Ref(
            id=ref_id,
            author=Author(handle="unknown", display_name="Unavailable",
                          avatar_path=None),
            created_at=datetime.now(timezone.utc),
            text="",
            media=[],
            unavailable=True,
        )

    store.save_refs(refs)
    # model_copy rather than a fresh State: a rebuilt State silently drops any field
    # this function doesn't happen to name.
    store.save_state(state.model_copy(update={"pending_ref_ids": []}))
    print(f"hydrated {len(found)} refs, {len(missing)} unavailable")


def _media_from_tweet(tweet: dict, http: httpx.Client) -> list[Media]:
    permalink = f"https://x.com/i/status/{tweet['id']}"
    media: list[Media] = []
    for index, entry in enumerate(tweet.get("_media", [])):
        kind = KNOWN_MEDIA_TYPES.get(entry["type"])
        if kind is None:
            raise ValueError(f"tweet {tweet['id']}: unrecognized media type {entry['type']!r}")
        # v2 only returns `url` for photos; animated_gif carries preview_image_url instead
        # (video's asset is never fetched, matching the archive path's privacy invariant).
        url = None
        if kind == "photo":
            url = entry["url"]
        elif kind == "gif":
            url = entry["preview_image_url"]
        local_path = None
        if url is not None:
            local_path = mirror_photo_bytes(
                tweet["id"], index, Path(url).suffix, download(http, url), config.MEDIA_DIR,
            )
        media.append(Media(kind=kind, local_path=local_path, source_url=permalink,
                           alt=entry.get("alt_text")))
    return media


def _referenced_id(tweet: dict, ref_type: str) -> str | None:
    for ref in tweet.get("referenced_tweets", []):
        if ref["type"] == ref_type:
            return ref["id"]
    return None


def _post_text_and_urls(tweet: dict) -> tuple[str, list[dict]]:
    # A Premium long post is truncated in `text` with a trailing self-referential t.co;
    # note_tweet.text carries the real content, with its own entities. Defensive: not
    # verified against a live Premium account, since one wasn't available for testing.
    note_tweet = tweet.get("note_tweet")
    if note_tweet is not None:
        return note_tweet["text"], note_tweet.get(
            "entities", {}).get("urls", tweet.get("entities", {}).get("urls", []))
    return tweet["text"], tweet.get("entities", {}).get("urls", [])


def _strip_quote_permalink(text: str, quoted_id: str) -> str:
    # Unlike the trailing-only archive rule, a v2 quote-with-photo tacks the media t.co
    # on after the quote permalink, so the permalink can land anywhere in the text.
    return strip_status_url(text, quoted_id, 1)


def _posts_from_timeline(tweets: list[dict], store: Store) -> tuple[list[Post], set[str]]:
    # Seed with the batch itself (not just the store) and process oldest-first, so a
    # thread or self-quote posted within one sync window resolves parents before
    # children instead of treating every member as referencing a stranger.
    owned = {p.id: p for p in store.all_posts()}
    pending: set[str] = set()
    posts: list[Post] = []

    with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS) as http:
        for tweet in sorted(tweets, key=lambda t: int(t["id"])):
            raw_text, urls = _post_text_and_urls(tweet)
            text, trailing_quoted_id = _expand_links(raw_text, urls, tweet["id"])

            # referenced_tweets is authoritative on the API path (unlike the archive,
            # which has no such field); it wins over the trailing-URL guess when present.
            referenced_quoted_id = _referenced_id(tweet, "quoted")
            quoted_id = referenced_quoted_id if referenced_quoted_id is not None else trailing_quoted_id
            if referenced_quoted_id is not None:
                text = _strip_quote_permalink(text, referenced_quoted_id)
            if quoted_id is not None and quoted_id not in owned:
                pending.add(quoted_id)

            parent_id = _referenced_id(tweet, "replied_to")
            if parent_id is None:
                thread_id = tweet["id"]
            elif parent_id in owned:
                thread_id = owned[parent_id].thread_id
            else:
                thread_id = tweet["id"]
                pending.add(parent_id)

            post = Post(
                id=tweet["id"],
                created_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")),
                text=text,
                media=_media_from_tweet(tweet, http),
                in_reply_to_id=parent_id,
                quoted_id=quoted_id,
                thread_id=thread_id,
            )
            posts.append(post)
            owned[post.id] = post
    return posts, pending


def sync() -> None:
    store = _store()
    state = store.load_state()
    tweets = _client().timeline(state.user_id, state.last_synced_id)
    if not tweets:
        print("no new posts")
        # A leftover pending list (e.g. from a transient hydrate failure) still needs
        # retrying even on a quiet sync where nothing new showed up.
        if state.pending_ref_ids:
            hydrate()
        return
    posts, pending = _posts_from_timeline(tweets, store)
    added = store.upsert_posts(posts)
    newest = max((p.id for p in posts), key=int)
    all_pending = sorted(set(state.pending_ref_ids) | pending)
    store.save_state(state.model_copy(update={"last_synced_id": newest,
                                              "pending_ref_ids": all_pending}))
    print(f"synced {added} new posts")
    hydrate()


def _require_site_root() -> None:
    if not (config.REPO_ROOT / "_config.yml").is_file():
        sys.exit(f"{config.REPO_ROOT} is not a Jekyll site root (no _config.yml); "
                 "run x-mirror from the site repository")


def main() -> None:
    _require_site_root()
    fire.Fire({"backfill": backfill, "hydrate": hydrate, "sync": sync, "forget": forget, "curate": curate})
