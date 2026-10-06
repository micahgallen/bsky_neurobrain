"""One-off backfill after the 2026-10-06 feed changes.

For every post in the 7-day Top window:
  1. Remove posts that match the topic blacklist (text from ClassificationLog).
  2. Fetch the record from the public Bluesky API and set is_reply + link.
  3. Recompute v1/v2 feed scores and link ranks.

Safe to re-run. Run with: PYTHONPATH=. venv/bin/python scripts/backfill_post_meta.py
"""

import datetime
import sys
import time

import requests

from src.database import db, Post, ClassificationLog, init_db
from src.engagement import (
    SCORE_REFRESH_DAYS,
    _compute_feed_score,
    _compute_feed_score_v2,
    _recompute_link_ranks,
)
from src.postmeta import BLACKLIST_RE, extract_link

PUBLIC_API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
BATCH = 25


def main() -> None:
    init_db()
    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=SCORE_REFRESH_DAYS)
    dry = "--dry-run" in sys.argv

    # 1. Blacklist sweep. ClassificationLog has no uri index, so do one pass
    #    over the recent rows instead of per-post lookups.
    texts = {}
    log_cutoff = cutoff - datetime.timedelta(days=1)
    for row in (
        ClassificationLog.select(ClassificationLog.uri, ClassificationLog.text)
        .where((ClassificationLog.classified_at >= log_cutoff) & (ClassificationLog.quality_score >= 3))
        .tuples()
    ):
        texts[row[0]] = row[1]

    posts = list(Post.select().where(Post.indexed_at >= cutoff))
    doomed = [p for p in posts if BLACKLIST_RE.search(texts.get(p.uri, ""))]
    print(f"{len(posts)} posts in window; {len(doomed)} match the blacklist")
    for p in doomed[:15]:
        print("   -", texts[p.uri][:90].replace("\n", " "))
    if not dry and doomed:
        Post.delete().where(Post.id.in_([p.id for p in doomed])).execute()
    posts = [p for p in posts if p.id not in {d.id for d in doomed}]

    # 2. Reply flag + link from the API.
    updated = missing = 0
    for i in range(0, len(posts), BATCH):
        batch = posts[i : i + BATCH]
        try:
            r = requests.get(PUBLIC_API, params=[("uris", p.uri) for p in batch], timeout=30)
            r.raise_for_status()
            views = {v["uri"]: v for v in r.json().get("posts", [])}
        except Exception as e:
            print(f"   batch {i // BATCH} failed: {e}")
            time.sleep(2)
            continue
        for p in batch:
            v = views.get(p.uri)
            if v is None:
                missing += 1
                continue
            rec = v.get("record", {})
            fields = dict(
                is_reply=int(bool(rec.get("reply"))),
                link=extract_link(rec),
                like_count=v.get("likeCount", 0) or 0,
                repost_count=v.get("repostCount", 0) or 0,
                reply_count=v.get("replyCount", 0) or 0,
                quote_count=v.get("quoteCount", 0) or 0,
            )
            age_hours = max((now - p.indexed_at).total_seconds() / 3600, 0.01)
            score_kwargs = dict(
                quality_score=p.quality_score, age_hours=age_hours,
                like_count=fields["like_count"], repost_count=fields["repost_count"],
                reply_count=fields["reply_count"], quote_count=fields["quote_count"],
            )
            fields["feed_score"] = _compute_feed_score(**score_kwargs)
            fields["feed_score_v2"] = _compute_feed_score_v2(is_reply=bool(fields["is_reply"]), **score_kwargs)
            if not dry:
                Post.update(**fields).where(Post.id == p.id).execute()
            updated += 1
        if (i // BATCH) % 40 == 0:
            print(f"   {i + len(batch)}/{len(posts)} processed")
    print(f"updated {updated}, {missing} no longer available on the API")

    # 3. Link ranks.
    if not dry:
        changed = _recompute_link_ranks(now)
        print(f"link ranks changed on {changed} posts")
        n_reply = Post.select().where((Post.indexed_at >= cutoff) & (Post.is_reply == 1)).count()
        n_link = Post.select().where((Post.indexed_at >= cutoff) & (Post.link.is_null(False))).count()
        n_capped = Post.select().where((Post.indexed_at >= cutoff) & (Post.link_rank > 3)).count()
        print(f"window now: {n_reply} replies flagged, {n_link} with links, {n_capped} hidden by link cap")


if __name__ == "__main__":
    main()
