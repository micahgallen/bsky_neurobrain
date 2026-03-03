"""Background job to fetch engagement metrics and compute feed scores."""

import datetime
import logging
import math
import time

from atproto import Client

from src.config import HANDLE, PASSWORD
from src.database import db, Post, init_db

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 48
UPDATE_INTERVAL = 300  # seconds (5 minutes)
BATCH_SIZE = 25  # Bluesky API limit for getPosts


def _get_client() -> Client:
    """Create and authenticate an atproto client."""
    client = Client()
    client.login(HANDLE, PASSWORD)
    return client


def _weighted_engagement(
    like_count: int,
    repost_count: int,
    reply_count: int,
    quote_count: int,
) -> int:
    """Compute weighted engagement total."""
    return like_count + (repost_count * 3) + (reply_count * 2) + (quote_count * 4)


def _compute_feed_score(
    quality_score: int,
    like_count: int,
    repost_count: int,
    reply_count: int,
    quote_count: int,
    age_hours: float,
) -> float:
    """Compute a combined feed score from quality and engagement.

    Quality is king: engagement can boost a post within its quality tier
    but never promote it above higher-quality content. A viral score-3
    pop-psych post should never outrank a score-5 paper discussion.

    Score bands: quality_score forms the integer part, engagement fills
    the fractional part (0.0 to ~0.9), time decay subtracts a small amount.
    """
    weighted = _weighted_engagement(like_count, repost_count, reply_count, quote_count)
    # Engagement bonus capped at ~0.9 so it never crosses quality tiers
    # log1p(100) ≈ 4.6, * 0.2 = 0.92 — even 100 weighted engagement stays < 1.0
    engagement_bonus = min(math.log1p(weighted) * 0.2, 0.95)
    time_penalty = min(age_hours / 120, 0.5)
    return quality_score + engagement_bonus - time_penalty


def _compute_feed_score_v2(
    quality_score: int,
    like_count: int,
    repost_count: int,
    reply_count: int,
    quote_count: int,
    age_hours: float,
) -> float:
    """Compute feed score with exponential engagement decay + quality floor.

    Engagement decays with an 8-hour half-life so fresh content can break
    through without needing to accumulate engagement first. Exceptional
    content (score 4-5) gets a small residual bonus that fades over 48h.
    Quality tiers are still fully preserved.
    """
    weighted = _weighted_engagement(like_count, repost_count, reply_count, quote_count)
    half_life = 8  # hours
    decay = math.exp(-math.log(2) * age_hours / half_life)
    engagement_bonus = min(math.log1p(weighted) * 0.2, 0.95) * decay
    # Quality floor: score-5 gets +0.2, score-4 gets +0.1, fading over 48h
    quality_residual = 0.1 * max(0, quality_score - 3) * max(0, 1 - age_hours / 48)
    return quality_score + engagement_bonus + quality_residual


def update_engagement() -> int:
    """Fetch engagement metrics for recent posts and update feed scores.

    Returns the number of posts updated.
    """
    db.connect(reuse_if_open=True)

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=LOOKBACK_HOURS)
    posts = list(
        Post.select()
        .where(Post.indexed_at >= cutoff)
        .order_by(Post.indexed_at.desc())
    )

    if not posts:
        logger.info("No recent posts to update")
        return 0

    logger.info("Updating engagement for %d posts", len(posts))

    client = _get_client()
    updated = 0
    now = datetime.datetime.utcnow()

    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        uris = [p.uri for p in batch]

        try:
            response = client.get_posts(uris)
        except Exception:
            logger.exception("Failed to fetch posts batch %d", i // BATCH_SIZE)
            continue

        api_posts = {pv.uri: pv for pv in response.posts}

        for post in batch:
            pv = api_posts.get(post.uri)
            if pv is None:
                continue

            age_hours = max((now - post.indexed_at).total_seconds() / 3600, 0.01)

            engagement_kwargs = dict(
                like_count=pv.like_count or 0,
                repost_count=pv.repost_count or 0,
                reply_count=pv.reply_count or 0,
                quote_count=pv.quote_count or 0,
            )
            score_kwargs = dict(
                quality_score=post.quality_score,
                age_hours=age_hours,
                **engagement_kwargs,
            )

            feed_score = _compute_feed_score(**score_kwargs)
            feed_score_v2 = _compute_feed_score_v2(**score_kwargs)

            Post.update(
                engagement_updated_at=now,
                feed_score=feed_score,
                feed_score_v2=feed_score_v2,
                **engagement_kwargs,
            ).where(Post.id == post.id).execute()

            updated += 1

    logger.info("Updated engagement for %d/%d posts", updated, len(posts))
    return updated


def run_loop() -> None:
    """Run engagement updates in a loop."""
    init_db()
    logger.info("Engagement updater started (interval=%ds)", UPDATE_INTERVAL)

    while True:
        try:
            update_engagement()
        except Exception:
            logger.exception("Engagement update failed")

        time.sleep(UPDATE_INTERVAL)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_loop()


if __name__ == "__main__":
    main()
