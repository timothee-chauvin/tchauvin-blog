from datetime import datetime, timezone

import pytest

from x_mirror import cli, config
from x_mirror.models import Author, Media, Post, Ref, State


def test_main_refuses_to_run_outside_a_site_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    with pytest.raises(SystemExit):
        cli._require_site_root()


def test_main_accepts_a_site_root(tmp_path, monkeypatch):
    (tmp_path / "_config.yml").write_text("title: t\n")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    cli._require_site_root()


def test_post_round_trips_through_json():
    post = Post(
        id="1933",
        created_at=datetime(2026, 6, 14, 12, 3, tzinfo=timezone.utc),
        text="hello https://example.com",
        media=[],
        in_reply_to_id=None,
        quoted_id=None,
        thread_id="1933",
    )
    assert Post.model_validate_json(post.model_dump_json()) == post


def test_media_video_has_no_local_path():
    media = Media(
        kind="video",
        local_path=None,
        source_url="https://x.com/timotheechauvin/status/1933",
        alt=None,
    )
    assert media.local_path is None


def test_ref_defaults_to_available():
    ref = Ref(
        id="42",
        author=Author(handle="someone", display_name="Some One", avatar_path=None),
        created_at=datetime(2026, 6, 14, 11, 40, tzinfo=timezone.utc),
        text="parent text",
        media=[],
        unavailable=False,
    )
    assert ref.unavailable is False


def test_state_round_trips():
    state = State(user_id="7", last_synced_id="1933", avatar_path="/assets/x/avatars/me.jpg",
                  pending_ref_ids=["42", "43"])
    assert State.model_validate_json(state.model_dump_json()) == state
