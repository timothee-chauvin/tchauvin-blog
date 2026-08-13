"""Regenerate tests/fixtures/archive.zip. Run manually; the zip is committed."""

import json
import zipfile
from pathlib import Path

TWEETS = [
    {"tweet": {
        "id_str": "100",
        "created_at": "Sun Jun 14 12:03:41 +0000 2026",
        "full_text": "thread root with a link https://t.co/aaa",
        "entities": {"urls": [{"url": "https://t.co/aaa",
                               "expanded_url": "https://example.com/article"}]},
    }},
    {"tweet": {
        "id_str": "101",
        "created_at": "Sun Jun 14 12:05:00 +0000 2026",
        "full_text": "second post in the thread",
        "in_reply_to_status_id_str": "100",
        "in_reply_to_screen_name": "timotheechauvin",
        "entities": {"urls": []},
    }},
    {"tweet": {
        "id_str": "102",
        "created_at": "Mon Jun 15 09:00:00 +0000 2026",
        "full_text": "replying to a stranger with a photo",
        "in_reply_to_status_id_str": "900",
        "in_reply_to_screen_name": "stranger",
        "entities": {"urls": []},
        "extended_entities": {"media": [{
            "type": "photo",
            "media_url_https": "https://pbs.twimg.com/media/abc.jpg",
            "ext_alt_text": "a photo",
        }]},
    }},
    {"tweet": {
        "id_str": "103",
        "created_at": "Tue Jun 16 09:00:00 +0000 2026",
        "full_text": "look at this https://t.co/bbb",
        "entities": {"urls": [{"url": "https://t.co/bbb",
                               "expanded_url": "https://x.com/stranger/status/901"}]},
    }},
    {"tweet": {
        "id_str": "104",
        "created_at": "Wed Jun 17 09:00:00 +0000 2026",
        "full_text": "RT @someone: not mine",
        "entities": {"urls": []},
        "retweeted_status": {"id_str": "999"},
    }},
    {"tweet": {
        "id_str": "105",
        "created_at": "Thu Jun 18 09:00:00 +0000 2026",
        "full_text": "three photos out of order",
        "entities": {"urls": []},
        # Attachment order (zzz, aaa, mmm) deliberately does not match the
        # lexicographic order of the archive filenames' hash basenames.
        "extended_entities": {"media": [
            {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/zzz.jpg",
             "ext_alt_text": "zzz alt"},
            {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/aaa.jpg",
             "ext_alt_text": "aaa alt"},
            {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/mmm.jpg",
             "ext_alt_text": "mmm alt"},
        ]},
    }},
    {"tweet": {
        "id_str": "106",
        "created_at": "Fri Jun 19 09:00:00 +0000 2026",
        "full_text": "compare https://t.co/ccc vs https://t.co/ddd for details",
        "entities": {"urls": [
            {"url": "https://t.co/ccc", "expanded_url": "https://x.com/stranger/status/902"},
            {"url": "https://t.co/ddd", "expanded_url": "https://x.com/stranger/status/903"},
        ]},
    }},
    {"tweet": {
        "id_str": "107",
        "created_at": "Sat Jun 20 09:00:00 +0000 2026",
        "full_text": "a photo post that ends in its own media link https://t.co/eee",
        # A media attachment's t.co lives in entities.media, never in entities.urls,
        # and expands to a permalink back to this very post.
        "entities": {"urls": [], "media": [{
            "url": "https://t.co/eee",
            "expanded_url": "https://twitter.com/timotheechauvin/status/107/photo/1",
        }]},
        "extended_entities": {"media": [{
            "type": "photo",
            "media_url_https": "https://pbs.twimg.com/media/eee.jpg",
            "ext_alt_text": "self-link photo",
        }]},
    }},
    {"tweet": {
        "id_str": "108",
        "created_at": "Sun Jun 21 09:00:00 +0000 2026",
        # The archive HTML-escapes &, < and > in full_text.
        "full_text": "R&amp;D moves fast &gt; slow, x &lt; y",
        "entities": {"urls": []},
    }},
    {"tweet": {
        # Real archives carry no retweeted_status field; RTs are marked only by prefix.
        "id_str": "109",
        "created_at": "Mon Jun 22 09:00:00 +0000 2026",
        "full_text": "RT @someone: not my writing either",
        "entities": {"urls": []},
    }},
    {"tweet": {
        "id_str": "50",
        "created_at": "Mon Jun 22 09:00:00 +0000 2018",
        "full_text": "ancient history, dropped by start_year",
        "entities": {"urls": []},
    }},
    {"tweet": {
        # A Premium long post: tweets.js truncates with an ellipsis; the full text
        # lives in note-tweet.js, joined by creation instant + text prefix.
        "id_str": "110",
        "created_at": "Tue Jun 23 09:00:00 +0000 2026",
        "full_text": "This is a long post that got cut right about…",
        "entities": {"urls": []},
    }},
    {"tweet": {
        # Reply-style long post: full_text carries the leading mention and a t.co id
        # that differs from the note's for the same link.
        "id_str": "111",
        "created_at": "Wed Jun 24 09:00:00 +0000 2026",
        "full_text": "@stranger I wrote about this https://t.co/OLD1 and then some…",
        "in_reply_to_status_id_str": "900",
        "in_reply_to_screen_name": "stranger",
        "entities": {"urls": [{"url": "https://t.co/OLD1",
                               "expanded_url": "https://example.com/essay"}]},
    }},
]

NOTES = [
    {"noteTweet": {
        "noteTweetId": "999110",
        "createdAt": "2026-06-23T09:00:00.000Z",
        "core": {
            "text": "This is a long post that got cut right about here, but the note carries "
                    "the full text, including a link https://t.co/fff at the end",
            "urls": [{"shortUrl": "https://t.co/fff",
                      "expandedUrl": "https://example.com/long-read"}],
        },
    }},
    {"noteTweet": {
        "noteTweetId": "999112",
        "createdAt": "2026-06-24T09:00:00.000Z",
        "core": {
            "text": "I wrote about this https://t.co/NEW2 and then some more thoughts that got cut",
            "urls": [{"shortUrl": "https://t.co/NEW2",
                      "expandedUrl": "https://example.com/essay"}],
        },
    }},
    {"noteTweet": {
        # Same instant, different text: forces the prefix check to disambiguate.
        "noteTweetId": "999111",
        "createdAt": "2026-06-23T09:00:00.000Z",
        "core": {"text": "A colliding note that must NOT be matched", "urls": []},
    }},
]

out = Path(__file__).parent / "archive.zip"
with zipfile.ZipFile(out, "w") as zf:
    zf.writestr("data/tweets.js",
                "window.YTD.tweets.part0 = " + json.dumps(TWEETS, indent=2))
    zf.writestr("data/note-tweet.js",
                "window.YTD.note_tweet.part0 = " + json.dumps(NOTES, indent=2))
    zf.writestr("data/tweets_media/102-abc.jpg", b"fake-jpeg-bytes")
    zf.writestr("data/tweets_media/105-zzz.jpg", b"zzz-bytes")
    zf.writestr("data/tweets_media/105-aaa.jpg", b"aaa-bytes")
    zf.writestr("data/tweets_media/105-mmm.jpg", b"mmm-bytes")
    zf.writestr("data/tweets_media/107-eee.jpg", b"eee-bytes")
print(f"wrote {out}")
