from datetime import datetime, timezone

import pytest

from x_mirror import config
from x_mirror.cli import _extract_post_id, forget, resolve_forget_targets
from x_mirror.models import Media, Post
from x_mirror.store import Store


def make_post(post_id, day, in_reply_to_id, thread_id):
    return Post(
        id=post_id,
        created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        text=f"post {post_id}",
        media=[],
        in_reply_to_id=in_reply_to_id,
        quoted_id=None,
        thread_id=thread_id,
    )


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path)
    store.upsert_posts([
        make_post("1", 1, None, "1"),
        make_post("2", 2, "1", "1"),
        make_post("3", 3, "2", "1"),
        make_post("9", 4, None, "9"),
    ])
    return store


def test_standalone_post_needs_no_prompt(store):
    assert resolve_forget_targets(store, "9", scope=None) == {"9"}


def test_scope_post_removes_only_the_target(store):
    assert resolve_forget_targets(store, "1", scope="post") == {"1"}


def test_scope_thread_removes_the_target_and_everything_below(store):
    assert resolve_forget_targets(store, "1", scope="thread") == {"1", "2", "3"}


def test_scope_thread_from_the_middle_leaves_ancestors_alone(store):
    assert resolve_forget_targets(store, "2", scope="thread") == {"2", "3"}


def test_unknown_scope_raises(store):
    with pytest.raises(ValueError):
        resolve_forget_targets(store, "1", scope="everything")


def test_unknown_post_raises(store):
    with pytest.raises(KeyError):
        resolve_forget_targets(store, "404", scope=None)


def test_forget_deletes_media_before_touching_the_store(tmp_path, monkeypatch):
    # delete_media raises on the missing file below; if the store were updated first
    # (the ordering bug this guards against), the post would vanish from the JSON while
    # its file stayed undeleted, and a re-run could never clean it up.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)

    store = Store(config.DATA_DIR)
    post = Post(
        id="1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        text="post 1",
        media=[Media(kind="photo", local_path="/assets/x/media/1-0.jpg",
                     source_url="https://x.com/a/status/1", alt=None)],
        in_reply_to_id=None,
        quoted_id=None,
        thread_id="1",
    )
    store.upsert_posts([post])

    with pytest.raises(FileNotFoundError):
        forget("1", scope=None)

    assert store.all_posts() == [post]


def test_forget_preflight_checks_every_file_before_deleting_any(tmp_path, monkeypatch):
    # Post "1"'s file exists; post "2"'s does not. The pre-flight check must reject the
    # whole batch before unlinking anything, including "1"'s file, so a re-run after
    # fixing "2" doesn't also have to recover from "1" having already been deleted.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)

    media_dir = tmp_path / "assets" / "x" / "media"
    media_dir.mkdir(parents=True)
    (media_dir / "1-0.jpg").write_bytes(b"present")

    store = Store(config.DATA_DIR)
    post_a = Post(
        id="1", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), text="post 1",
        media=[Media(kind="photo", local_path="/assets/x/media/1-0.jpg",
                     source_url="https://x.com/a/status/1", alt=None)],
        in_reply_to_id=None, quoted_id=None, thread_id="1",
    )
    post_b = Post(
        id="2", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), text="post 2",
        media=[Media(kind="photo", local_path="/assets/x/media/2-0.jpg",
                     source_url="https://x.com/a/status/2", alt=None)],
        in_reply_to_id="1", quoted_id=None, thread_id="1",
    )
    store.upsert_posts([post_a, post_b])

    with pytest.raises(FileNotFoundError):
        forget("1", scope="thread")

    assert (media_dir / "1-0.jpg").exists()
    assert {p.id for p in store.all_posts()} == {"1", "2"}


def test_forget_refuses_to_orphan_a_surviving_quote(tmp_path, monkeypatch):
    # A quote that resolves to nothing raises in _plugins/x_generator.rb, taking down
    # every page of the site, and hydrate can't repair it. So forget must refuse rather
    # than manufacture that state — and must not have deleted anything on the way out.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)

    media_dir = tmp_path / "assets" / "x" / "media"
    media_dir.mkdir(parents=True)
    (media_dir / "100-0.jpg").write_bytes(b"present")

    store = Store(config.DATA_DIR)
    quoted = Post(
        id="100", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), text="quoted post",
        media=[Media(kind="photo", local_path="/assets/x/media/100-0.jpg",
                     source_url="https://x.com/a/status/100", alt=None)],
        in_reply_to_id=None, quoted_id=None, thread_id="100",
    )
    quoting = Post(
        id="109", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), text="quoting myself",
        media=[], in_reply_to_id=None, quoted_id="100", thread_id="109",
    )
    store.upsert_posts([quoted, quoting])

    with pytest.raises(ValueError, match="109"):
        forget("https://x.com/me/status/100", scope="post")

    assert {p.id for p in store.all_posts()} == {"100", "109"}
    assert (media_dir / "100-0.jpg").exists()


def test_forget_allows_removing_a_quote_and_its_quoter_together(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)

    store = Store(config.DATA_DIR)
    quoted = make_post("100", 1, None, "100")
    quoting = Post(
        id="101", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), text="quoting myself",
        media=[], in_reply_to_id="100", quoted_id="100", thread_id="100",
    )
    store.upsert_posts([quoted, quoting])

    forget("100", scope="thread")

    assert store.all_posts() == []


@pytest.mark.parametrize("target", [
    "https://x.com/user/status/1933?s=20",
    "https://x.com/user/status/1933?t=abc&s=46",
    "https://x.com/user/status/1933/",
    "https://x.com/user/status/1933/photo/1",
    "1933",
    # fire hands a bare-digit argument over as an int, not a str
    1933,
])
def test_extract_post_id_handles_real_world_url_shapes(target):
    assert _extract_post_id(target) == "1933"


def test_curate_round_trip(tmp_path, monkeypatch):
    from x_mirror import cli, config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    store = Store(tmp_path)
    store.upsert_posts([make_post("1", 1, None, "1")])
    cli.curate("https://x.com/u/status/1")
    assert store.load_curated() == ["1"]
    cli.curate("1")  # idempotent
    assert store.load_curated() == ["1"]
    cli.curate("1", remove=True)
    assert store.load_curated() == []


def test_curate_unmirrored_post_raises(tmp_path, monkeypatch):
    from x_mirror import cli, config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    Store(tmp_path).upsert_posts([make_post("1", 1, None, "1")])
    with pytest.raises(KeyError):
        cli.curate("404")
