import datetime
from src.database import Post


def handler(cursor, limit):
    posts = (
        Post.select()
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
