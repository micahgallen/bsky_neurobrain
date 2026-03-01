"""Backfill the Signal feed with recent posts from followed accounts."""

import datetime
import logging
import sys
import time

from atproto import Client

from src.config import HANDLE, PASSWORD
from src.classifier import classify_politics
from src.database import init_db, SignalPost
from src.follows import load_follows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def backfill(hours=1):
    init_db()

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    logger.info("Backfilling posts from the last %d hour(s) (since %s)", hours, cutoff)

    follows = load_follows(HANDLE, PASSWORD)
    logger.info("Fetching recent posts from %d followed accounts...", len(follows))

    client = Client()
    client.login(HANDLE, PASSWORD)

    total = 0
    political = 0
    approved = 0
    errors = 0

    # Rate limit: ~2000 req/5min to stay well under Bluesky's 3000/5min limit
    # That's ~0.15s between requests
    REQUEST_INTERVAL = 0.15

    for i, did in enumerate(follows, 1):
        try:
            resp = client.get_author_feed(did, filter="posts_no_replies", limit=30)
            time.sleep(REQUEST_INTERVAL)
        except Exception:
            logger.debug("Failed to fetch feed for %s", did)
            errors += 1
            time.sleep(1)  # Back off on errors
            continue

        for item in resp.feed:
            post = item.post
            record = post.record

            # Skip reposts/quotes from other authors — only the followed account's own posts
            if post.author.did != did:
                continue

            # Skip non-English
            langs = getattr(record, "langs", None) or []
            if "en" not in langs:
                continue

            text = getattr(record, "text", "") or ""
            if len(text) < 30:
                continue

            # Skip posts older than cutoff
            created = getattr(record, "created_at", None)
            if created:
                # Parse ISO timestamp — atproto returns string
                if isinstance(created, str):
                    # Handle both Z and +00:00 suffixes
                    ts = created.replace("Z", "+00:00")
                    try:
                        dt = datetime.datetime.fromisoformat(ts).replace(tzinfo=None)
                    except ValueError:
                        continue
                else:
                    dt = created
                if dt < cutoff:
                    continue

            total += 1

            if classify_politics(text):
                political += 1
                logger.info(
                    "[%d/%d] POLITICAL: %.60s", i, len(follows), text
                )
                continue

            # Insert into SignalPost
            SignalPost.insert(
                uri=post.uri, cid=post.cid
            ).on_conflict_ignore().execute()
            approved += 1
            logger.info(
                "[%d/%d] APPROVED:  %.60s", i, len(follows), text
            )

        # Progress every 50 accounts
        if i % 50 == 0:
            logger.info(
                "Progress: %d/%d accounts, %d posts (%d approved, %d political)",
                i, len(follows), total, approved, political,
            )

    logger.info(
        "Done! %d posts checked, %d approved, %d political, %d fetch errors",
        total, approved, political, errors,
    )


if __name__ == "__main__":
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 1
    backfill(hours)
