from pathlib import Path

import pytest

from x_mirror import config
from x_mirror.cli import backfill
from x_mirror.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "archive.zip"

OWNER = {"data": {
    "id": "7",
    "username": "timotheechauvin",
    "name": "Timothée Chauvin",
    "profile_image_url": "https://pbs.twimg.com/profile_images/1_normal.jpg",
}}


@pytest.fixture
def paths(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "token")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(config, "AVATAR_DIR", tmp_path / "avatars")

    httpx_mock.add_response(json=OWNER)
    httpx_mock.add_response(content=b"owner-avatar-bytes")
    # The fixture leaves refs 900 and 901 pending; an empty lookup marks both
    # unavailable, which keeps this test on backfill rather than on hydration.
    httpx_mock.add_response(json={})
    return tmp_path


def test_backfill_mirrors_the_owner_avatar(paths):
    backfill(str(FIXTURE))
    assert (paths / "avatars" / "timotheechauvin.jpg").read_bytes() == b"owner-avatar-bytes"


def test_backfill_records_the_avatar_path_in_state(paths):
    backfill(str(FIXTURE))
    state = Store(config.DATA_DIR).load_state()
    assert state.avatar_path == "/assets/x/avatars/timotheechauvin.jpg"
    assert state.user_id == "7"


def test_backfill_fetches_the_full_size_avatar(paths, httpx_mock):
    backfill(str(FIXTURE))
    requested = [str(r.url) for r in httpx_mock.get_requests()]
    # "_normal" is X's 48px crop; the mirror wants the original upload
    assert "https://pbs.twimg.com/profile_images/1.jpg" in requested


def test_backfill_writes_posts_and_pending_refs(paths):
    backfill(str(FIXTURE))
    store = Store(config.DATA_DIR)
    assert {p.id for p in store.all_posts()} == {"100", "101", "102", "103", "105", "106", "107", "108", "110", "111"}
    assert set(store.load_refs()) == {"900", "901"}
