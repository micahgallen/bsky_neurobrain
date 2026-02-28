import datetime
from src.database import SignalPost


def handler(cursor, limit):
    posts = (
        SignalPost.select()
        .order_by(SignalPost.indexed_at.desc())
        .limit(limit)
    )

    if cursor:
        try:
            parts = cursor.split("::")
            if len(parts) == 2:
                ts_str, cid = parts
                ts = datetime.datetime.utcfromtimestamp(int(ts_str) / 1000)
                posts = posts.where(
                    (SignalPost.indexed_at < ts)
                    | ((SignalPost.indexed_at == ts) & (SignalPost.cid < cid))
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
