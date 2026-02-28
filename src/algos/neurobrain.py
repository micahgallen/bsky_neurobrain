import datetime
from src.database import Post


def handler(cursor, limit):
    posts = (
        Post.select()
        .order_by(Post.indexed_at.desc())
        .limit(limit)
    )

    if cursor:
        try:
            ts_str, cid = cursor.split("::")
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
        new_cursor = f"{ts_ms}::{post.cid}"

    return {"cursor": new_cursor, "feed": feed}
