"""Background job to fetch engagement metrics and compute feed scores."""

import datetime
import logging
import math
import time

from atproto import Client

from src.config import HANDLE, PASSWORD
from src.database import db, Post, init_db
from src.postmeta import extract_link

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
    # Freshness boost is gated on engagement — posts must earn their way to the
    # top with some social validation. Full boost at weighted>=3 (e.g. 3 likes,
    # or 1 repost). Zero-engagement posts rank at their raw quality score.
    freshness = 0.3 * math.exp(-age_hours / 12) * min(1.0, weighted / 3)
    return quality_score + engagement_bonus + freshness - time_penalty


RISING_MIN_QUALITY = 4       # Rising is for good posts only
RISING_MIN_ENGAGEMENT = 3    # weighted; e.g. 3 likes or 1 repost — must be *rising*
RISING_MAX_AGE_HOURS = 48    # must match MAX_FEED_AGE_HOURS in src/algos/neurobrain_v2.py
RISING_HALF_LIFE_HOURS = 8
LINK_CAP = 3                 # max posts per shared link kept visible in a feed window


def _compute_feed_score_v2(
    quality_score: int,
    like_count: int,
    repost_count: int,
    reply_count: int,
    quote_count: int,
    age_hours: float,
    is_reply: bool = False,
) -> float:
    """Compute feed score for NeuroBrain Rising (v2).

    Rising = good, new, gaining traction, and not already in Top (the last
    part is enforced in the handler). Eligibility gates return 0.0, which the
    handler filters out:
      - quality >= 4 (quality-3 posts with a burst of likes were dominating)
      - weighted engagement >= 3 (zero-engagement posts are not "rising")
      - not a reply (mid-thread commentary was half the feed)
      - under 48h old

    Score is log engagement with an 8h half-life plus a small q5 bonus that
    fades over the window. No ungated freshness boost.
    """
    weighted = _weighted_engagement(like_count, repost_count, reply_count, quote_count)
    if (
        is_reply
        or quality_score < RISING_MIN_QUALITY
        or weighted < RISING_MIN_ENGAGEMENT
        or age_hours > RISING_MAX_AGE_HOURS
    ):
        return 0.0
    decay = math.exp(-math.log(2) * age_hours / RISING_HALF_LIFE_HOURS)
    engagement = math.log1p(weighted) * decay
    quality_bonus = 0.5 * (quality_score - RISING_MIN_QUALITY) * max(0.0, 1 - age_hours / RISING_MAX_AGE_HOURS)
    return engagement + quality_bonus


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

            # Backfill reply flag / link from the fetched record for posts
            # ingested before these columns existed.
            record = getattr(pv, "record", None)
            meta_kwargs = {}
            if record is not None:
                reply = bool(getattr(record, "reply", None))
                meta_kwargs["is_reply"] = int(reply)
                if post.link is None:
                    link = extract_link_from_record_view(record)
                    if link:
                        meta_kwargs["link"] = link
            else:
                reply = bool(post.is_reply)

            feed_score = _compute_feed_score(**score_kwargs)
            feed_score_v2 = _compute_feed_score_v2(is_reply=reply, **score_kwargs)

            Post.update(
                engagement_updated_at=now,
                feed_score=feed_score,
                feed_score_v2=feed_score_v2,
                **engagement_kwargs,
                **meta_kwargs,
            ).where(Post.id == post.id).execute()

            updated += 1

    return updated


def _recompute_scores(posts: list[Post], now: datetime.datetime) -> int:
    """Recompute v1 + v2 feed scores from stored engagement values + current time decay.

    Does NOT touch engagement_updated_at — that field tracks last API-confirmed
    engagement, not last score recompute. Posts here are older than 48h, so
    their v2 (Rising) score is always 0.
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
            feed_score_v2=_compute_feed_score_v2(is_reply=bool(post.is_reply), **score_kwargs),
        ).where(Post.id == post.id).execute()
        updated += 1
    return updated


def extract_link_from_record_view(record) -> str | None:
    """Adapter: atproto record model -> plain dict -> postmeta.extract_link."""
    try:
        data = record.model_dump(by_alias=True) if hasattr(record, "model_dump") else dict(record)
    except Exception:
        return None
    return extract_link(data)


def _recompute_link_ranks(now: datetime.datetime) -> int:
    """Rank posts sharing the same link by feed_score within the 7-day window.

    Handlers only serve link_rank <= LINK_CAP, so at most LINK_CAP posts about
    the same URL show up per feed. Posts without a link always rank 1.
    """
    cutoff = now - datetime.timedelta(days=SCORE_REFRESH_DAYS)
    rows = list(
        Post.select(Post.id, Post.link, Post.link_rank, Post.feed_score)
        .where((Post.indexed_at >= cutoff) & (Post.link.is_null(False)))
        .order_by(Post.link, Post.feed_score.desc(), Post.indexed_at.desc())
    )
    changed = 0
    rank = 0
    current = None
    with db.atomic():
        for row in rows:
            if row.link != current:
                current, rank = row.link, 0
            rank += 1
            if row.link_rank != rank:
                Post.update(link_rank=rank).where(Post.id == row.id).execute()
                changed += 1
    return changed


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

    rank_updated = _recompute_link_ranks(now)

    logger.info(
        "Engagement: %d API-refreshed, %d decay-only, %d link-rank changes",
        api_updated, decay_updated, rank_updated,
    )
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
