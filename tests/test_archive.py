import json
import zipfile
from pathlib import Path

import pytest

from x_mirror.archive import parse_archive

FIXTURE = Path(__file__).parent / "fixtures" / "archive.zip"


def parse(tmp_path):
    return parse_archive(FIXTURE, tmp_path, 2023)


def test_retweets_are_excluded(tmp_path):
    posts, _ = parse(tmp_path)
    assert "104" not in {p.id for p in posts}


def test_all_other_posts_are_kept(tmp_path):
    posts, _ = parse(tmp_path)
    assert {p.id for p in posts} == {"100", "101", "102", "103", "105", "106", "107", "108", "110", "111"}


def test_tco_links_are_expanded(tmp_path):
    posts, _ = parse(tmp_path)
    root = next(p for p in posts if p.id == "100")
    assert "https://example.com/article" in root.text
    assert "t.co" not in root.text


def test_self_replies_share_a_thread_id(tmp_path):
    posts, _ = parse(tmp_path)
    by_id = {p.id: p for p in posts}
    assert by_id["100"].thread_id == "100"
    assert by_id["101"].thread_id == "100"


def test_reply_to_a_stranger_starts_its_own_thread(tmp_path):
    posts, _ = parse(tmp_path)
    by_id = {p.id: p for p in posts}
    assert by_id["102"].thread_id == "102"
    assert by_id["102"].in_reply_to_id == "900"


def test_stranger_parents_and_quotes_are_reported_for_hydration(tmp_path):
    _, pending = parse(tmp_path)
    assert pending == {"900", "901"}


def test_quoted_status_url_is_stripped_from_text(tmp_path):
    posts, _ = parse(tmp_path)
    quoting = next(p for p in posts if p.id == "103")
    assert quoting.quoted_id == "901"
    assert "status/901" not in quoting.text
    assert quoting.text.strip() == "look at this"


def test_photos_are_mirrored_locally(tmp_path):
    posts, _ = parse(tmp_path)
    with_photo = next(p for p in posts if p.id == "102")
    assert with_photo.media[0].local_path == "/assets/x/media/102-0.jpg"
    assert with_photo.media[0].alt == "a photo"
    assert (tmp_path / "102-0.jpg").read_bytes() == b"fake-jpeg-bytes"


def test_multi_photo_posts_pair_bytes_by_hash_not_position(tmp_path):
    # Attachment order is zzz, aaa, mmm; archive filenames sort aaa, mmm, zzz.
    # Each photo must get its own bytes and alt text regardless of that mismatch.
    posts, _ = parse(tmp_path)
    post = next(p for p in posts if p.id == "105")
    zzz, aaa, mmm = post.media

    assert zzz.alt == "zzz alt"
    assert zzz.local_path == "/assets/x/media/105-0.jpg"
    assert (tmp_path / "105-0.jpg").read_bytes() == b"zzz-bytes"

    assert aaa.alt == "aaa alt"
    assert aaa.local_path == "/assets/x/media/105-1.jpg"
    assert (tmp_path / "105-1.jpg").read_bytes() == b"aaa-bytes"

    assert mmm.alt == "mmm alt"
    assert mmm.local_path == "/assets/x/media/105-2.jpg"
    assert (tmp_path / "105-2.jpg").read_bytes() == b"mmm-bytes"


def test_missing_archive_file_for_photo_raises(tmp_path):
    zip_path = tmp_path / "broken.zip"
    tweets = [{"tweet": {
        "id_str": "200",
        "created_at": "Sun Jun 14 12:03:41 +0000 2026",
        "full_text": "a photo that never got archived",
        "entities": {"urls": []},
        "extended_entities": {"media": [{
            "type": "photo",
            "media_url_https": "https://pbs.twimg.com/media/missing.jpg",
            "ext_alt_text": "gone",
        }]},
    }}]
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data/tweets.js",
                     "window.YTD.tweets.part0 = " + json.dumps(tweets))

    with pytest.raises(ValueError, match="200"):
        parse_archive(zip_path, tmp_path, 2023)


def test_unrecognized_media_type_raises(tmp_path):
    zip_path = tmp_path / "broken.zip"
    tweets = [{"tweet": {
        "id_str": "201",
        "created_at": "Sun Jun 14 12:03:41 +0000 2026",
        "full_text": "a poll, of all things",
        "entities": {"urls": []},
        "extended_entities": {"media": [{
            "type": "poll",
            "media_url_https": "https://pbs.twimg.com/media/poll.jpg",
            "ext_alt_text": None,
        }]},
    }}]
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data/tweets.js",
                     "window.YTD.tweets.part0 = " + json.dumps(tweets))

    with pytest.raises(ValueError, match="poll"):
        parse_archive(zip_path, tmp_path, 2023)


def test_trailing_status_url_is_still_treated_as_a_quote(tmp_path):
    posts, _ = parse(tmp_path)
    quoting = next(p for p in posts if p.id == "103")
    assert quoting.quoted_id == "901"


def test_media_tco_is_expanded_and_the_self_permalink_dropped(tmp_path):
    # The media t.co lives in entities.media, not entities.urls. Left unexpanded it
    # renders as a live t.co link — a redirect through X for anyone who clicks it —
    # and expanded it is just a link back to the post the reader is already reading.
    posts, _ = parse(tmp_path)
    post = next(p for p in posts if p.id == "107")
    assert post.text == "a photo post that ends in its own media link"
    assert "t.co" not in post.text
    assert "status/107" not in post.text
    assert post.quoted_id is None
    assert post.media[0].local_path == "/assets/x/media/107-0.jpg"


def test_mid_text_status_links_are_not_quotes(tmp_path):
    posts, _ = parse(tmp_path)
    post = next(p for p in posts if p.id == "106")
    assert post.quoted_id is None
    assert "https://x.com/stranger/status/902" in post.text
    assert "https://x.com/stranger/status/903" in post.text


def test_html_entities_in_full_text_are_unescaped(tmp_path):
    posts, _ = parse(tmp_path)
    post = next(p for p in posts if p.id == "108")
    assert post.text == "R&D moves fast > slow, x < y"


def test_rt_prefixed_posts_are_excluded(tmp_path):
    posts, _ = parse(tmp_path)
    assert "109" not in {p.id for p in posts}


def test_posts_before_start_year_are_dropped(tmp_path):
    posts, _ = parse(tmp_path)
    assert "50" not in {p.id for p in posts}


def test_note_tweet_replaces_truncated_text(tmp_path):
    posts, _ = parse(tmp_path)
    post = next(p for p in posts if p.id == "110")
    assert "cut right about here" in post.text
    assert "…" not in post.text
    assert "https://example.com/long-read" in post.text
    assert "colliding" not in post.text


def test_note_join_survives_mentions_and_differing_tco_ids(tmp_path):
    posts, _ = parse(tmp_path)
    post = next(p for p in posts if p.id == "111")
    assert "more thoughts that got cut" in post.text
    assert "https://example.com/essay" in post.text
    assert "t.co" not in post.text
