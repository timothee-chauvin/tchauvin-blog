from datetime import datetime, timezone

import pytest

from x_mirror.models import Post, State
from x_mirror.store import Store


def make_post(post_id, when, in_reply_to_id, thread_id):
    return Post(
        id=post_id,
        created_at=when,
        text=f"post {post_id}",
        media=[],
        in_reply_to_id=in_reply_to_id,
        quoted_id=None,
        thread_id=thread_id,
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_upsert_routes_posts_into_year_files(store, tmp_path):
    store.upsert_posts([
        make_post("1", datetime(2025, 3, 1, tzinfo=timezone.utc), None, "1"),
        make_post("2", datetime(2026, 3, 1, tzinfo=timezone.utc), None, "2"),
    ])
    assert (tmp_path / "2025.json").is_file()
    assert (tmp_path / "2026.json").is_file()
    assert store.years() == [2026, 2025]


def test_year_file_is_reverse_chronological(store):
    store.upsert_posts([
        make_post("1", datetime(2026, 1, 1, tzinfo=timezone.utc), None, "1"),
        make_post("3", datetime(2026, 3, 1, tzinfo=timezone.utc), None, "3"),
        make_post("2", datetime(2026, 2, 1, tzinfo=timezone.utc), None, "2"),
    ])
    assert [p.id for p in store.load_year(2026)] == ["3", "2", "1"]


def test_upsert_is_idempotent(store):
    post = make_post("1", datetime(2026, 1, 1, tzinfo=timezone.utc), None, "1")
    assert store.upsert_posts([post]) == 1
    assert store.upsert_posts([post]) == 0
    assert len(store.load_year(2026)) == 1


def test_remove_posts_returns_what_it_removed(store):
    store.upsert_posts([
        make_post("1", datetime(2026, 1, 1, tzinfo=timezone.utc), None, "1"),
        make_post("2", datetime(2026, 2, 1, tzinfo=timezone.utc), None, "2"),
    ])
    removed = store.remove_posts({"1"})
    assert [p.id for p in removed] == ["1"]
    assert [p.id for p in store.load_year(2026)] == ["2"]


def test_descendants_walks_the_self_reply_chain(store):
    store.upsert_posts([
        make_post("1", datetime(2026, 1, 1, tzinfo=timezone.utc), None, "1"),
        make_post("2", datetime(2026, 1, 2, tzinfo=timezone.utc), "1", "1"),
        make_post("3", datetime(2026, 1, 3, tzinfo=timezone.utc), "2", "1"),
        make_post("9", datetime(2026, 1, 4, tzinfo=timezone.utc), None, "9"),
    ])
    assert [p.id for p in store.descendants("1")] == ["2", "3"]
    assert [p.id for p in store.descendants("2")] == ["3"]
    assert store.descendants("3") == []


def test_state_round_trips_on_disk(store):
    state = State(user_id="7", last_synced_id=None, avatar_path=None, pending_ref_ids=[])
    store.save_state(state)
    assert store.load_state() == state


def test_load_state_raises_when_missing(store):
    with pytest.raises(FileNotFoundError):
        store.load_state()


def test_descendants_terminates_on_a_cycle(store):
    store.upsert_posts([
        make_post("1", datetime(2026, 1, 1, tzinfo=timezone.utc), "2", "1"),
        make_post("2", datetime(2026, 1, 2, tzinfo=timezone.utc), "1", "1"),
    ])
    result = store.descendants("1")
    assert [p.id for p in result] == ["2"]
    assert len(result) == 1


def test_descendants_terminates_on_a_self_reply(store):
    store.upsert_posts([
        make_post("1", datetime(2026, 1, 1, tzinfo=timezone.utc), "1", "1"),
    ])
    result = store.descendants("1")
    assert result == []
