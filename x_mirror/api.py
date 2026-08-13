import httpx

from x_mirror import config

TWEET_FIELDS = "created_at,author_id,entities,attachments,referenced_tweets,note_tweet"
EXPANSIONS = "author_id,attachments.media_keys"
MEDIA_FIELDS = "type,url,alt_text,preview_image_url"
USER_FIELDS = "username,name,profile_image_url"


def _attach_media(payload: dict) -> None:
    # Expansions put media on includes.media, keyed by media_key; attach each tweet's own
    # media inline (like the author is attached below) so callers don't have to carry
    # includes around separately.
    media_by_key = {m["media_key"]: m for m in payload.get("includes", {}).get("media", [])}
    for tweet in payload.get("data", []):
        tweet["_media"] = [
            media_by_key[key] for key in tweet.get("attachments", {}).get("media_keys", [])
        ]


class XClient:
    def __init__(self, bearer_token: str):
        if not bearer_token:
            raise ValueError("X_BEARER_TOKEN is unset")
        self._client = httpx.Client(
            base_url=config.API_BASE,
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )

    def _get(self, path: str, params: dict) -> dict:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def fetch_user(self, handle: str) -> dict:
        return self._get(f"/users/by/username/{handle}",
                         {"user.fields": USER_FIELDS})["data"]

    def timeline(self, user_id: str, since_id: str | None) -> list[dict]:
        params = {
            "max_results": config.TIMELINE_PAGE_SIZE,
            "tweet.fields": TWEET_FIELDS,
            "expansions": EXPANSIONS,
            "media.fields": MEDIA_FIELDS,
            "user.fields": USER_FIELDS,
            "exclude": "retweets",
        }
        if since_id is not None:
            params["since_id"] = since_id

        collected: list[dict] = []
        while True:
            payload = self._get(f"/users/{user_id}/tweets", params)
            _attach_media(payload)
            collected.extend(payload.get("data", []))
            next_token = payload.get("meta", {}).get("next_token")
            if next_token is None:
                return collected
            params["pagination_token"] = next_token

    def lookup_tweets(self, ids: list[str]) -> tuple[list[dict], set[str]]:
        found: list[dict] = []
        missing: set[str] = set()
        for start in range(0, len(ids), config.TWEET_LOOKUP_BATCH):
            batch = ids[start:start + config.TWEET_LOOKUP_BATCH]
            payload = self._get("/tweets", {
                "ids": ",".join(batch),
                "tweet.fields": TWEET_FIELDS,
                "expansions": EXPANSIONS,
                "media.fields": MEDIA_FIELDS,
                "user.fields": USER_FIELDS,
            })
            _attach_media(payload)
            data = payload.get("data", [])
            users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
            for tweet in data:
                tweet["_author"] = users[tweet["author_id"]]
            found.extend(data)
            returned = {t["id"] for t in data}
            missing.update(i for i in batch if i not in returned)
        return found, missing
