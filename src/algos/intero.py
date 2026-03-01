import datetime
from src.database import InteroPost


def handler(cursor, limit):
    posts = (
        InteroPost.select()
        .order_by(InteroPost.indexed_at.desc())
        .limit(limit)
    )

    if cursor:
        try:
            parts = cursor.split("::")
            if len(parts) == 2:
                ts_str, cid = parts
                ts = datetime.datetime.utcfromtimestamp(int(ts_str) / 1000)
                posts = posts.where(
                    (InteroPost.indexed_at < ts)
                    | ((InteroPost.indexed_at == ts) & (InteroPost.cid < cid))
                )
        except (ValueError, TypeError):
            pass

    feed = []
    new_cursor = None
    for post in posts:
        feed.append({"post": post.uri})
        ts_ms = int(post.indexed_at.timestamp() * 1000)
        new_cursor = f"{ts_ms}::{post.cid}"

    # Only return cursor if we filled the page — signals more results available
    if len(feed) < limit:
        new_cursor = None

    return {"cursor": new_cursor, "feed": feed}
