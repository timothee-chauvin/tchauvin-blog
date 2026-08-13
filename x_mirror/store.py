from collections.abc import Iterable
from pathlib import Path

import orjson

from x_mirror.models import Post, Ref, State


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _year_path(self, year: int) -> Path:
        return self.data_dir / f"{year}.json"

    def years(self) -> list[int]:
        return sorted(
            (int(p.stem) for p in self.data_dir.glob("*.json") if p.stem.isdigit()),
            reverse=True,
        )

    def load_year(self, year: int) -> list[Post]:
        path = self._year_path(year)
        if not path.is_file():
            return []
        return [Post.model_validate(item) for item in orjson.loads(path.read_bytes())]

    def _write_year(self, year: int, posts: list[Post]) -> None:
        posts.sort(key=lambda p: p.created_at, reverse=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = [p.model_dump(mode="json") for p in posts]
        # OPT_INDENT_2: these files are committed, so readable formatting prevents unreadable diffs on every sync
        self._year_path(year).write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

    def all_posts(self) -> list[Post]:
        posts = [p for year in self.years() for p in self.load_year(year)]
        posts.sort(key=lambda p: p.created_at, reverse=True)
        return posts

    def upsert_posts(self, posts: Iterable[Post]) -> int:
        by_year: dict[int, list[Post]] = {}
        for post in posts:
            by_year.setdefault(post.created_at.year, []).append(post)

        added = 0
        for year, incoming in by_year.items():
            existing = self.load_year(year)
            known = {p.id for p in existing}
            fresh = [p for p in incoming if p.id not in known]
            added += len(fresh)
            if fresh:
                self._write_year(year, existing + fresh)
        return added

    def remove_posts(self, ids: set[str]) -> list[Post]:
        removed: list[Post] = []
        for year in self.years():
            posts = self.load_year(year)
            keep = [p for p in posts if p.id not in ids]
            if len(keep) != len(posts):
                removed.extend(p for p in posts if p.id in ids)
                self._write_year(year, keep)
        return removed

    def descendants(self, post_id: str) -> list[Post]:
        posts = self.all_posts()
        children: dict[str, list[Post]] = {}
        for post in posts:
            if post.in_reply_to_id is not None:
                children.setdefault(post.in_reply_to_id, []).append(post)

        found: list[Post] = []
        visited: set[str] = {post_id}
        # Guard against a cycle in the reply graph, which would otherwise hang the build
        queue = [post_id]
        while queue:
            for child in children.get(queue.pop(), []):
                if child.id not in visited:
                    visited.add(child.id)
                    found.append(child)
                    queue.append(child.id)
        found.sort(key=lambda p: p.created_at)
        return found

    def load_curated(self) -> list[str]:
        path = self.data_dir / "curated.json"
        if not path.is_file():
            return []
        return orjson.loads(path.read_bytes())

    def save_curated(self, ids: list[str]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "curated.json").write_bytes(
            orjson.dumps(ids, option=orjson.OPT_INDENT_2)
        )

    def load_refs(self) -> dict[str, Ref]:
        path = self.data_dir / "refs.json"
        if not path.is_file():
            return {}
        return {k: Ref.model_validate(v) for k, v in orjson.loads(path.read_bytes()).items()}

    def save_refs(self, refs: dict[str, Ref]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {k: v.model_dump(mode="json") for k, v in sorted(refs.items())}
        (self.data_dir / "refs.json").write_bytes(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2)
        )

    def load_state(self) -> State:
        path = self.data_dir / "state.json"
        if not path.is_file():
            # Missing state means backfill never ran; fail loudly rather than silently using a default
            raise FileNotFoundError(f"{path} missing — run backfill first")
        return State.model_validate(orjson.loads(path.read_bytes()))

    def save_state(self, state: State) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "state.json").write_bytes(
            orjson.dumps(state.model_dump(mode="json"), option=orjson.OPT_INDENT_2)
        )
