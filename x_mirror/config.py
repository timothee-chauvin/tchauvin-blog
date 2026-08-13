from pathlib import Path

# The CLI edits the Jekyll site it is invoked from, not this package's checkout:
# code (this repo) and site data live in separate repositories. main() refuses to
# run unless the cwd looks like a site root.
REPO_ROOT = Path.cwd()
DATA_DIR = REPO_ROOT / "_data" / "x"
MEDIA_DIR = REPO_ROOT / "assets" / "x" / "media"
AVATAR_DIR = REPO_ROOT / "assets" / "x" / "avatars"

HANDLE = "timotheechauvin"
# Posts before this year are dropped at backfill; the account owner considers them archived-only.
START_YEAR = 2024

API_BASE = "https://api.x.com/2"
TWEET_LOOKUP_BATCH = 100
TIMELINE_PAGE_SIZE = 100
HTTP_TIMEOUT_SECONDS = 30
