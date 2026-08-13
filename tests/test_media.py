import pytest

from x_mirror.media import delete_media, mirror_avatar_bytes, mirror_photo_bytes
from x_mirror.models import Media


def test_mirror_photo_writes_file_and_returns_site_path(tmp_path):
    path = mirror_photo_bytes("1933", 0, ".jpg", b"binary", tmp_path)
    assert path == "/assets/x/media/1933-0.jpg"
    assert (tmp_path / "1933-0.jpg").read_bytes() == b"binary"


def test_mirror_photo_is_deterministic_across_calls(tmp_path):
    first = mirror_photo_bytes("1933", 1, ".png", b"a", tmp_path)
    second = mirror_photo_bytes("1933", 1, ".png", b"a", tmp_path)
    assert first == second


def test_mirror_avatar_uses_the_handle(tmp_path):
    path = mirror_avatar_bytes("someone", ".jpg", b"img", tmp_path)
    assert path == "/assets/x/avatars/someone.jpg"
    assert (tmp_path / "someone.jpg").read_bytes() == b"img"


def test_delete_media_removes_only_local_files(tmp_path):
    (tmp_path / "assets" / "x" / "media").mkdir(parents=True)
    (tmp_path / "assets" / "x" / "media" / "1933-0.jpg").write_bytes(b"x")
    media = [
        Media(kind="photo", local_path="/assets/x/media/1933-0.jpg",
              source_url="https://x.com/a/status/1933", alt=None),
        Media(kind="video", local_path=None,
              source_url="https://x.com/a/status/1933", alt=None),
    ]
    removed = delete_media(media, tmp_path)
    assert removed == ["/assets/x/media/1933-0.jpg"]
    assert not (tmp_path / "assets" / "x" / "media" / "1933-0.jpg").exists()


def test_delete_media_raises_when_a_local_file_is_already_gone(tmp_path):
    media = [Media(kind="photo", local_path="/assets/x/media/nope.jpg",
                   source_url="https://x.com/a/status/1", alt=None)]
    with pytest.raises(FileNotFoundError):
        delete_media(media, tmp_path)


def test_delete_media_raises_when_local_path_escapes_media_directory(tmp_path):
    media = [Media(kind="photo", local_path="/assets/x/media/../../../../etc/passwd",
                   source_url="https://x.com/a/status/1", alt=None)]
    with pytest.raises(ValueError, match="escapes media directory"):
        delete_media(media, tmp_path)
