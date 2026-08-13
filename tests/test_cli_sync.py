from datetime import datetime, timezone

from x_mirror import config
from x_mirror.cli import _posts_from_timeline, hydrate, sync
from x_mirror.models import Author, Post, Ref, State
from x_mirror.store import Store


def make_tweet(id_, text, urls=None, referenced_tweets=None, media=None, note_tweet=None):
    tweet = {
        "id": id_,
        "text": text,
        "author_id": "1",
        "created_at": "2026-06-14T11:40:00.000Z",
        "entities": {"urls": urls or []},
    }
    if referenced_tweets is not None:
        tweet["referenced_tweets"] = referenced_tweets
    if media is not None:
        tweet["_media"] = media
    if note_tweet is not None:
        tweet["note_tweet"] = note_tweet
    return tweet


def test_plain_post_has_no_parent_or_quote(tmp_path):
    store = Store(tmp_path)
    posts, pending = _posts_from_timeline([make_tweet("200", "just a post")], store)
    assert posts[0].in_reply_to_id is None
    assert posts[0].quoted_id is None
    assert posts[0].thread_id == "200"
    assert pending == set()


def test_self_reply_inherits_thread_id_from_store(tmp_path):
    store = Store(tmp_path)
    store.upsert_posts([Post(
        id="100", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        text="root", media=[], in_reply_to_id=None, quoted_id=None, thread_id="100",
    )])
    tweet = make_tweet("201", "more thoughts",
                        referenced_tweets=[{"type": "replied_to", "id": "100"}])

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].in_reply_to_id == "100"
    assert posts[0].thread_id == "100"
    assert pending == set()


def test_reply_to_a_stranger_starts_its_own_thread(tmp_path):
    store = Store(tmp_path)
    tweet = make_tweet("202", "interesting point",
                        referenced_tweets=[{"type": "replied_to", "id": "900"}])

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].in_reply_to_id == "900"
    assert posts[0].thread_id == "202"
    assert pending == {"900"}


def test_quote_strips_trailing_permalink_from_text(tmp_path):
    store = Store(tmp_path)
    tweet = make_tweet(
        "203", "look at this https://t.co/abc",
        urls=[{"url": "https://t.co/abc", "expanded_url": "https://x.com/stranger/status/901"}],
        referenced_tweets=[{"type": "quoted", "id": "901"}],
    )

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].quoted_id == "901"
    assert "status/901" not in posts[0].text
    assert posts[0].text.strip() == "look at this"
    assert pending == {"901"}


def test_mid_text_status_link_is_not_a_quote(tmp_path):
    store = Store(tmp_path)
    tweet = make_tweet(
        "206", "see https://t.co/abc for details",
        urls=[{"url": "https://t.co/abc", "expanded_url": "https://x.com/stranger/status/902"}],
    )

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].quoted_id is None
    assert "https://x.com/stranger/status/902" in posts[0].text
    assert pending == set()


def test_photo_is_downloaded_and_mirrored(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    httpx_mock.add_response(url="https://pbs.twimg.com/media/abc.jpg", content=b"fake-jpeg-bytes")

    store = Store(tmp_path / "data")
    tweet = make_tweet(
        "204", "a photo",
        media=[{"media_key": "3_1", "type": "photo",
               "url": "https://pbs.twimg.com/media/abc.jpg", "alt_text": "a photo"}],
    )

    posts, _ = _posts_from_timeline([tweet], store)

    assert posts[0].media[0].local_path == "/assets/x/media/204-0.jpg"
    assert posts[0].media[0].alt == "a photo"
    assert (tmp_path / "media" / "204-0.jpg").read_bytes() == b"fake-jpeg-bytes"


def test_video_is_not_downloaded(tmp_path):
    store = Store(tmp_path)
    tweet = make_tweet(
        "205", "a video",
        media=[{"media_key": "7_1", "type": "video", "alt_text": None}],
    )

    posts, _ = _posts_from_timeline([tweet], store)

    assert posts[0].media[0].local_path is None
    assert posts[0].media[0].kind == "video"


# --- C1: a thread (or self-quote) arriving in one timeline response ---

def test_thread_posted_in_one_sync_window_shares_a_thread_id(tmp_path):
    store = Store(tmp_path)
    # Deliberately out of order (newest first), matching how the API actually returns them.
    tweets = [
        make_tweet("302", "third", referenced_tweets=[{"type": "replied_to", "id": "301"}]),
        make_tweet("300", "root"),
        make_tweet("301", "second", referenced_tweets=[{"type": "replied_to", "id": "300"}]),
    ]

    posts, pending = _posts_from_timeline(tweets, store)

    by_id = {p.id: p for p in posts}
    assert by_id["300"].thread_id == "300"
    assert by_id["301"].thread_id == "300"
    assert by_id["302"].thread_id == "300"
    assert pending == set()


def test_self_quote_in_one_sync_window_is_not_pending(tmp_path):
    store = Store(tmp_path)
    tweets = [
        make_tweet(
            "401", "look at this https://t.co/abc",
            urls=[{"url": "https://t.co/abc", "expanded_url": "https://x.com/me/status/400"}],
            referenced_tweets=[{"type": "quoted", "id": "400"}],
        ),
        make_tweet("400", "root"),
    ]

    posts, pending = _posts_from_timeline(tweets, store)

    by_id = {p.id: p for p in posts}
    assert by_id["401"].quoted_id == "400"
    assert pending == set()


def test_self_reply_whose_parent_is_already_in_the_store_still_works(tmp_path):
    # Regression guard: the batch-seeding fix for C1 must not break the pre-existing
    # store-lookup path for a parent from an earlier sync.
    store = Store(tmp_path)
    store.upsert_posts([Post(
        id="100", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        text="root", media=[], in_reply_to_id=None, quoted_id=None, thread_id="100",
    )])
    tweet = make_tweet("201", "more thoughts",
                        referenced_tweets=[{"type": "replied_to", "id": "100"}])

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].thread_id == "100"
    assert pending == set()


# --- C3: animated gifs use preview_image_url, not url ---

def test_gif_uses_preview_image_url_and_completes(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    httpx_mock.add_response(url="https://pbs.twimg.com/tweet_video_thumb/abc.jpg",
                            content=b"gif-preview-bytes")

    store = Store(tmp_path / "data")
    tweet = make_tweet(
        "207", "a gif",
        media=[{"media_key": "7_2", "type": "animated_gif",
               "preview_image_url": "https://pbs.twimg.com/tweet_video_thumb/abc.jpg",
               "alt_text": None}],
    )

    posts, _ = _posts_from_timeline([tweet], store)

    assert posts[0].media[0].kind == "gif"
    assert posts[0].media[0].local_path == "/assets/x/media/207-0.jpg"
    assert (tmp_path / "media" / "207-0.jpg").read_bytes() == b"gif-preview-bytes"


# --- I4: a quote tweet with an attached photo ---

def test_quote_with_photo_still_reports_quoted_id(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    httpx_mock.add_response(url="https://pbs.twimg.com/media/xyz.jpg", content=b"photo-bytes")

    store = Store(tmp_path / "data")
    # v2 tacks the media t.co on after the quote permalink, so the quote link is no
    # longer trailing; only referenced_tweets still identifies it as a quote.
    tweet = make_tweet(
        "211", "look at this https://t.co/quote https://t.co/media",
        urls=[
            {"url": "https://t.co/quote", "expanded_url": "https://x.com/stranger/status/901"},
            {"url": "https://t.co/media", "expanded_url": "https://x.com/me/status/211/photo/1"},
        ],
        referenced_tweets=[{"type": "quoted", "id": "901"}],
        media=[{"media_key": "3_1", "type": "photo",
               "url": "https://pbs.twimg.com/media/xyz.jpg", "alt_text": None}],
    )

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].quoted_id == "901"
    assert "status/901" not in posts[0].text
    assert posts[0].text.strip() == "look at this"
    assert pending == {"901"}
    assert posts[0].media[0].local_path == "/assets/x/media/211-0.jpg"


def test_media_permalink_is_stripped_from_the_text(tmp_path, httpx_mock, monkeypatch):
    # v2 puts the media attachment's t.co in entities.urls, expanding to a permalink
    # back to this very post with a /photo/1 suffix. Stored, it renders as a live
    # self-referential link that routes the reader through x.com.
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    httpx_mock.add_response(url="https://pbs.twimg.com/media/xyz.jpg", content=b"photo-bytes")

    store = Store(tmp_path / "data")
    tweet = make_tweet(
        "220", "just a photo https://t.co/media",
        urls=[{"url": "https://t.co/media",
               "expanded_url": "https://x.com/me/status/220/photo/1"}],
        media=[{"media_key": "3_1", "type": "photo",
               "url": "https://pbs.twimg.com/media/xyz.jpg", "alt_text": None}],
    )

    posts, _ = _posts_from_timeline([tweet], store)

    assert posts[0].text == "just a photo"
    assert posts[0].quoted_id is None


def test_quote_without_photo_still_works(tmp_path):
    # Same as test_quote_strips_trailing_permalink_from_text, restated to make explicit
    # that this is the "no photo" half of I4's required pair.
    store = Store(tmp_path)
    tweet = make_tweet(
        "212", "worth reading https://t.co/abc",
        urls=[{"url": "https://t.co/abc", "expanded_url": "https://x.com/stranger/status/903"}],
        referenced_tweets=[{"type": "quoted", "id": "903"}],
    )

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].quoted_id == "903"
    assert posts[0].text.strip() == "worth reading"
    assert pending == {"903"}


# --- I8: a long (note_tweet) post ---

def test_long_post_uses_note_tweet_text_and_does_not_self_quote(tmp_path):
    store = Store(tmp_path)
    tweet = make_tweet(
        "210", "truncated preview... https://t.co/self",
        urls=[{"url": "https://t.co/self", "expanded_url": "https://x.com/me/status/210"}],
        note_tweet={"text": "a very long post that goes on and on without any links at all"},
    )

    posts, pending = _posts_from_timeline([tweet], store)

    assert posts[0].text == "a very long post that goes on and on without any links at all"
    assert posts[0].quoted_id is None
    assert pending == set()


# --- C2: sync() must not drop a leftover pending list ---

def test_sync_folds_leftover_pending_into_the_new_batch(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "token")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(config, "AVATAR_DIR", tmp_path / "avatars")

    store = Store(config.DATA_DIR)
    store.save_state(State(user_id="7", last_synced_id="100", avatar_path=None, pending_ref_ids=["888"]))

    httpx_mock.add_response(json={
        "data": [{"id": "101", "text": "new post", "author_id": "7",
                  "created_at": "2026-06-14T11:40:00.000Z", "entities": {"urls": []}}],
        "meta": {"result_count": 1},
    })
    httpx_mock.add_response(json={
        "data": [{"id": "888", "text": "stranger's tweet", "author_id": "5",
                  "created_at": "2026-06-14T11:00:00.000Z"}],
        "includes": {"users": [{"id": "5", "username": "stranger", "name": "A Stranger",
                                "profile_image_url": "https://pbs.twimg.com/a_normal.jpg"}]},
    })
    httpx_mock.add_response(content=b"avatar-bytes")

    sync()

    refs = store.load_refs()
    assert "888" in refs
    assert refs["888"].text == "stranger's tweet"


def test_sync_retries_pending_refs_even_when_timeline_is_empty(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "token")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "AVATAR_DIR", tmp_path / "avatars")

    store = Store(config.DATA_DIR)
    store.save_state(State(user_id="7", last_synced_id="100", avatar_path=None, pending_ref_ids=["888"]))

    httpx_mock.add_response(json={"meta": {"result_count": 0}})
    httpx_mock.add_response(json={
        "data": [{"id": "888", "text": "stranger's tweet", "author_id": "5",
                  "created_at": "2026-06-14T11:00:00.000Z"}],
        "includes": {"users": [{"id": "5", "username": "stranger", "name": "A Stranger",
                                "profile_image_url": "https://pbs.twimg.com/a_normal.jpg"}]},
    })
    httpx_mock.add_response(content=b"avatar-bytes")

    sync()

    refs = store.load_refs()
    assert "888" in refs


# --- I7: hydrate must not re-fetch a ref already captured ---

def test_hydrate_skips_refs_already_hydrated(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "token")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "AVATAR_DIR", tmp_path / "avatars")

    store = Store(config.DATA_DIR)
    store.save_state(State(user_id="7", last_synced_id="100", avatar_path=None, pending_ref_ids=["888", "889"]))
    store.save_refs({"888": Ref(
        id="888", author=Author(handle="a", display_name="A", avatar_path=None),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), text="already hydrated",
        media=[], unavailable=False,
    )})

    httpx_mock.add_response(json={
        "data": [{"id": "889", "text": "new ref", "author_id": "5",
                  "created_at": "2026-06-14T11:00:00.000Z"}],
        "includes": {"users": [{"id": "5", "username": "stranger", "name": "A Stranger",
                                "profile_image_url": "https://pbs.twimg.com/a_normal.jpg"}]},
    })
    httpx_mock.add_response(content=b"avatar-bytes")

    hydrate()

    request = httpx_mock.get_requests()[0]
    assert request.url.params["ids"] == "889"


def test_hydrate_mirrors_a_refs_photo_locally(tmp_path, httpx_mock, monkeypatch):
    # lookup_tweets pays for attachments.media_keys + media.fields; a ref's photo must
    # end up on Ref.media, mirrored locally like a post's own — a pbs.twimg.com URL on
    # a rendered parent/quote card would break the privacy invariant.
    monkeypatch.setenv("X_BEARER_TOKEN", "token")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(config, "AVATAR_DIR", tmp_path / "avatars")

    store = Store(config.DATA_DIR)
    store.save_state(State(user_id="7", last_synced_id="100", avatar_path=None,
                           pending_ref_ids=["888"]))

    httpx_mock.add_response(json={
        "data": [{"id": "888", "text": "a stranger's photo", "author_id": "5",
                  "created_at": "2026-06-14T11:00:00.000Z",
                  "attachments": {"media_keys": ["3_9"]}}],
        "includes": {
            "users": [{"id": "5", "username": "stranger", "name": "A Stranger",
                       "profile_image_url": "https://pbs.twimg.com/a_normal.jpg"}],
            "media": [{"media_key": "3_9", "type": "photo",
                       "url": "https://pbs.twimg.com/media/ref.jpg", "alt_text": "a ref photo"}],
        },
    })
    httpx_mock.add_response(url="https://pbs.twimg.com/a.jpg", content=b"avatar-bytes")
    httpx_mock.add_response(url="https://pbs.twimg.com/media/ref.jpg", content=b"ref-photo-bytes")

    hydrate()

    ref = store.load_refs()["888"]
    assert ref.media[0].local_path == "/assets/x/media/888-0.jpg"
    assert ref.media[0].alt == "a ref photo"
    assert (tmp_path / "media" / "888-0.jpg").read_bytes() == b"ref-photo-bytes"


def test_html_entities_in_api_text_are_unescaped(tmp_path):
    store = Store(tmp_path)
    posts, _ = _posts_from_timeline([make_tweet("210", "R&amp;D &gt; hype")], store)
    assert posts[0].text == "R&D > hype"
