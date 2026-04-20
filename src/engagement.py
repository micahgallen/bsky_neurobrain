"""Background job to fetch engagement metrics and compute feed scores."""

import datetime
import logging
import math
import time

from atproto import Client

from src.config import HANDLE, PASSWORD
from src.database import db, Post, init_db

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 48        # API refresh window — fetch fresh engagement counts
SCORE_REFRESH_DAYS = 7     # Score recompute window (matches v1 MAX_FEED_AGE_DAYS)
UPDATE_INTERVAL = 300      # seconds (5 minutes)
BATCH_SIZE = 25            # Bluesky API limit for getPosts


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
    """Compute feed score for NeuroBrain v1 — quality digest, 7-day window.

    Quality tiers are preserved: engagement bonus is capped below 1.0 so a
    score-4 post never outranks a score-5. Time penalty is superlinear (weak
    early, strong late) so posts drop toward the bottom of their tier as
    they approach the 7-day cutoff. A small freshness boost gives brand-new
    posts a short head start (~24h) before engagement takes over.
    """
    weighted = _weighted_engagement(like_count, repost_count, reply_count, quote_count)
    engagement_bonus = min(math.log1p(weighted) * 0.15, 0.7)
    # Superlinear penalty: ~0 early, ~0.9 at 7d (grows as (age/7d)^1.5)
    time_penalty = (min(age_hours, 168) / 168) ** 1.5 * 0.9
    # Freshness boost: 0.3 at 0h, 0.11 at 12h, 0.04 at 24h, ~0 by 36h
    freshness = 0.3 * math.exp(-age_hours / 12)
    return quality_score + engagement_bonus + freshness - time_penalty


def _compute_feed_score_v2(
    quality_score: int,
    like_count: int,
    repost_count: int,
    reply_count: int,
    quote_count: int,
    age_hours: float,
) -> float:
    """Compute feed score for NeuroBrain Rising (v2) — fast decay, 72h window.

    Engagement-driven with a 6-hour half-life: bursty early engagement wins,
    late accumulation fades. Quality acts as a modest additive bonus that
    also fades over 72h, so stale high-quality posts can't sit on the feed
    without fresh traction. Small freshness boost keeps brand-new posts
    visible for their first couple hours before engagement decides.
    """
    weighted = _weighted_engagement(like_count, repost_count, reply_count, quote_count)
    # 6-hour half-life on engagement — content needs to be both fresh AND engaging
    decay = math.exp(-math.log(2) * age_hours / 6)
    engagement_bonus = math.log1p(weighted) * 0.5 * decay
    # Quality bonus fades linearly to 0 at 72h so old q5s can't linger
    quality_bonus = (max(0, quality_score - 3) * 0.4) * max(0, 1 - age_hours / 72)
    # Freshness boost: 0.3 at 0h, fades with 3h half-life
    freshness = 0.3 * math.exp(-age_hours / 3)
    return engagement_bonus + quality_bonus + freshness


def _refresh_engagement_via_api(posts: list[Post], now: datetime.datetime) -> int:
    """Fetch fresh engagement counts from Bluesky API and recompute v1 + v2 scores."""
    if not posts:
        return 0

    client = _get_client()
    updated = 0

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

    return updated


def _recompute_scores(posts: list[Post], now: datetime.datetime) -> int:
    """Recompute v1 + v2 feed scores from stored engagement values + current time decay.

    Does NOT touch engagement_updated_at — that field tracks last API-confirmed
    engagement, not last score recompute. v2 score is age-dependent too (8h
    half-life on engagement, 48h fade on quality residual), so it benefits
    from the recompute even though the v2 handler has no age window.
    """
    if not posts:
        return 0
    updated = 0
    for post in posts:
        age_hours = max((now - post.indexed_at).total_seconds() / 3600, 0.01)
        score_kwargs = dict(
            quality_score=post.quality_score,
            like_count=post.like_count,
            repost_count=post.repost_count,
            reply_count=post.reply_count,
            quote_count=post.quote_count,
            age_hours=age_hours,
        )
        Post.update(
            feed_score=_compute_feed_score(**score_kwargs),
            feed_score_v2=_compute_feed_score_v2(**score_kwargs),
        ).where(Post.id == post.id).execute()
        updated += 1
    return updated


def update_engagement() -> int:
    """Refresh feed scores for posts in the active window.

    Two phases:
      B (cheap, local): posts 48h–14d → recompute v1+v2 scores from stored engagement.
      A (expensive, network): posts <48h → fetch fresh engagement from Bluesky API.

    Phase B runs first so an API outage in Phase A still produces fresh decay updates.
    """
    db.connect(reuse_if_open=True)
    now = datetime.datetime.utcnow()

    api_cutoff = now - datetime.timedelta(hours=LOOKBACK_HOURS)
    score_cutoff = now - datetime.timedelta(days=SCORE_REFRESH_DAYS)

    older = list(
        Post.select()
        .where((Post.indexed_at >= score_cutoff) & (Post.indexed_at < api_cutoff))
    )
    decay_updated = _recompute_scores(older, now)

    fresh = list(
        Post.select()
        .where(Post.indexed_at >= api_cutoff)
        .order_by(Post.indexed_at.desc())
    )
    api_updated = _refresh_engagement_via_api(fresh, now)

    logger.info("Engagement: %d API-refreshed, %d decay-only", api_updated, decay_updated)
    return api_updated + decay_updated


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
