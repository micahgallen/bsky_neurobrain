import datetime
from src.database import Post
from src.algos.neurobrain import MAX_FEED_AGE_DAYS as TOP_WINDOW_DAYS, LINK_CAP
from src.engagement import RISING_MIN_QUALITY, RISING_MIN_ENGAGEMENT

MAX_FEED_AGE_HOURS = 48  # must match RISING_MAX_AGE_HOURS in src/engagement.py
TOP_EXCLUDE_N = 30       # posts already on Top's first page are not "rising"


def handler(cursor, limit):
    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(hours=MAX_FEED_AGE_HOURS)
    top_cutoff = now - datetime.timedelta(days=TOP_WINDOW_DAYS)
    already_top = (
        Post.select(Post.id)
        .where((Post.indexed_at >= top_cutoff) & (Post.link_rank <= LINK_CAP))
        .order_by(Post.feed_score.desc(), Post.indexed_at.desc())
        .limit(TOP_EXCLUDE_N)
    )
    weighted = (
        Post.like_count + Post.repost_count * 3 + Post.reply_count * 2 + Post.quote_count * 4
    )
    # Eligibility gates are duplicated here from _compute_feed_score_v2 so the
    # feed is correct even if a stored score is stale.
    posts = (
        Post.select()
        .where(
            (Post.indexed_at >= cutoff)
            & (Post.feed_score_v2 > 0)      # 0 = failed an eligibility gate
            & (Post.quality_score >= RISING_MIN_QUALITY)
            & (weighted >= RISING_MIN_ENGAGEMENT)
            & (Post.is_reply == 0)
            & (Post.link_rank <= LINK_CAP)
            & (Post.id.not_in(already_top))
        )
        .order_by(Post.feed_score_v2.desc(), Post.indexed_at.desc())
        .limit(limit)
    )

    if cursor:
        try:
            parts = cursor.split("::")
            if len(parts) == 3:
                score_x100, ts_str, cid = parts
                score = int(score_x100) / 100.0
                ts = datetime.datetime.utcfromtimestamp(int(ts_str) / 1000)
                posts = posts.where(
                    (Post.feed_score_v2 < score)
                    | ((Post.feed_score_v2 == score) & (Post.indexed_at < ts))
                    | (
                        (Post.feed_score_v2 == score)
                        & (Post.indexed_at == ts)
                        & (Post.cid < cid)
                    )
                )
            elif len(parts) == 2:
                ts_str, cid = parts
                ts = datetime.datetime.utcfromtimestamp(int(ts_str) / 1000)
                posts = posts.where(
                    (Post.indexed_at < ts)
                    | ((Post.indexed_at == ts) & (Post.cid < cid))
                )
        except (ValueError, TypeError):
            pass

    feed = []
    new_cursor = None
    for post in posts:
        feed.append({"post": post.uri})
        ts_ms = int(post.indexed_at.timestamp() * 1000)
        score_x100 = int(post.feed_score_v2 * 100)
        new_cursor = f"{score_x100}::{ts_ms}::{post.cid}"

    # Only return cursor if we filled the page — signals more results available
    if len(feed) < limit:
        new_cursor = None

    return {"cursor": new_cursor, "feed": feed}
