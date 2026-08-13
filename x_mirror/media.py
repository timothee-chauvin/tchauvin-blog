from pathlib import Path

import httpx

from x_mirror.models import Media


def _write(directory: Path, name: str, data: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)


def mirror_photo_bytes(post_id: str, index: int, suffix: str, data: bytes, media_dir: Path) -> str:
    name = f"{post_id}-{index}{suffix}"
    _write(media_dir, name, data)
    return f"/assets/x/media/{name}"


def mirror_avatar_bytes(handle: str, suffix: str, data: bytes, avatar_dir: Path) -> str:
    # X handles are alphanumeric plus underscore; no path injection possible from the API.
    name = f"{handle}{suffix}"
    _write(avatar_dir, name, data)
    return f"/assets/x/avatars/{name}"


def download(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    return response.content


def delete_media(media: list[Media], repo_root: Path) -> list[str]:
    removed = []
    media_tree = repo_root / "assets" / "x"
    for item in media:
        if item.local_path is None:
            continue
        path = (repo_root / item.local_path.lstrip("/")).resolve()
        try:
            path.relative_to(media_tree)
        except ValueError:
            raise ValueError(f"local_path {item.local_path} escapes media directory")
        path.unlink()
        removed.append(item.local_path)
    return removed
