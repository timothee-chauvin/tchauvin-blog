import pytest

from x_mirror.api import XClient


def test_lookup_reports_missing_ids_separately(httpx_mock):
    httpx_mock.add_response(json={
        "data": [{"id": "900", "text": "alive", "author_id": "5",
                  "created_at": "2026-06-14T11:40:00.000Z"}],
        "includes": {"users": [{"id": "5", "username": "stranger",
                                "name": "A Stranger",
                                "profile_image_url": "https://pbs.twimg.com/a.jpg"}]},
        "errors": [{"resource_id": "901", "title": "Not Found Error"}],
    })
    found, missing = XClient("token").lookup_tweets(["900", "901"])
    assert [t["id"] for t in found] == ["900"]
    assert missing == {"901"}


def test_timeline_returns_empty_list_when_nothing_is_new(httpx_mock):
    httpx_mock.add_response(json={"meta": {"result_count": 0}})
    assert XClient("token").timeline("7", since_id="1933") == []


def test_http_errors_are_not_swallowed(httpx_mock):
    httpx_mock.add_response(status_code=429)
    with pytest.raises(Exception):
        XClient("token").timeline("7", since_id=None)


def test_missing_bearer_token_raises():
    with pytest.raises(ValueError):
        XClient("")
