from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Author(BaseModel):
    handle: str
    display_name: str
    avatar_path: str | None


class Media(BaseModel):
    kind: Literal["photo", "video", "gif"]
    local_path: str | None
    source_url: str
    alt: str | None


class Ref(BaseModel):
    """A post by anyone, captured once at hydration and never re-checked."""

    id: str
    author: Author
    created_at: datetime
    text: str
    media: list[Media]
    unavailable: bool


class Post(BaseModel):
    id: str
    created_at: datetime
    text: str
    media: list[Media]
    in_reply_to_id: str | None
    quoted_id: str | None
    thread_id: str


class State(BaseModel):
    user_id: str
    last_synced_id: str | None
    # The account owner's own mirrored avatar. Everyone else's lives on their Ref;
    # the owner has no Ref, and the Jekyll templates read this.
    avatar_path: str | None
    pending_ref_ids: list[str]
