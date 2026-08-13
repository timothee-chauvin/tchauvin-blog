# tchauvin-blog

The code behind [tchauvin.com](https://tchauvin.com): a Jekyll site (minima-based) with
a self-hosted mirror of the site owner's X/Twitter posts at
[/x/](https://tchauvin.com/x/) and an LLM-friendly plain-Markdown view of the whole
site under [/llm/](https://tchauvin.com/llm/x.md).

Content (posts, images, the X post data) lives in a separate private repository; this
repo is only the engine. The private repo's deploy workflow checks this repo out and
overlays it onto the content tree before running `jekyll build`, so the split is
invisible to the site itself.

## Layout

- `_plugins/`, `_includes/`, `_layouts/`, `_sass/` — Jekyll customizations.
  `_plugins/x_generator.rb` renders the X mirror from `_data/x/*.json`;
  `_plugins/llm_generator.rb` emits the `/llm/` Markdown views.
- `x_mirror/` — Python CLI (`x-mirror`) that maintains `_data/x/` and `assets/x/`:
  `backfill` from an official X archive export, hourly `sync` from the X API v2,
  `curate`/`forget` for editorial control. Media and avatars are mirrored locally so
  visitors never contact an X-operated host.
- `scripts/` — repo checks (also run in the site's deploy workflow): escaping
  self-test, privacy check (no X-operated hosts referenced), `/llm/` well-formedness,
  post heading style.
- `tests/` — pytest suite against a synthetic archive fixture
  (`tests/fixtures/make_fixture.py`).

## Running

```sh
uv run pytest                 # Python tests
bundle install                # ruby side (see .tool-versions)
scripts/check-x-escaping      # escaping self-test
```

The `x-mirror` CLI must be run from a Jekyll site root (a directory with
`_config.yml`); it reads and writes `_data/x/` and `assets/x/` relative to the cwd:

```sh
uv run --project /path/to/tchauvin-blog x-mirror sync
```

`sync` needs `X_BEARER_TOKEN` set (X API v2, read access to the account's timeline).

## Deploys

A push to `main` here runs the tests, then dispatches the private site repo's deploy
workflow (secret `SITE_DISPATCH_TOKEN`, a fine-grained PAT with Actions read/write on
the site repo). A push to the private repo deploys directly. Either way, GitHub Pages
serves the result.
