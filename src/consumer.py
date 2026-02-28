import asyncio
import json
import logging
import signal

import websockets

from src.database import db, Post, SubscriptionState, init_db
from src.prefilter import passes_prefilter, check_hashtags
from src.classifier import classify_post

logger = logging.getLogger(__name__)

JETSTREAM_URL = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)
SERVICE_NAME = "jetstream"
CURSOR_UPDATE_INTERVAL = 50  # Update cursor every N messages
QUALITY_THRESHOLD = 3  # Minimum score to include in feed


def _get_cursor() -> int | None:
    """Load the saved cursor from the database."""
    try:
        state = SubscriptionState.get(SubscriptionState.service == SERVICE_NAME)
        return state.cursor
    except SubscriptionState.DoesNotExist:
        return None


def _save_cursor(cursor: int) -> None:
    """Persist the cursor to the database."""
    SubscriptionState.insert(
        service=SERVICE_NAME, cursor=cursor
    ).on_conflict(
        conflict_target=[SubscriptionState.service],
        update={SubscriptionState.cursor: cursor},
    ).execute()


def _handle_delete(uri: str) -> None:
    """Remove a deleted post from the database."""
    deleted = Post.delete().where(Post.uri == uri).execute()
    if deleted:
        logger.info("Deleted post: %s", uri)


def _extract_hashtags(record: dict) -> list[str]:
    """Extract hashtag strings from Bluesky post facets."""
    tags = []
    for facet in record.get("facets") or []:
        for feature in facet.get("features") or []:
            if feature.get("$type") == "app.bsky.richtext.facet#tag":
                tag = feature.get("tag", "")
                if tag:
                    tags.append(tag)
    return tags


def _handle_create(did: str, rkey: str, cid: str, record: dict) -> None:
    """Process a new post through the filter pipeline."""
    # English only
    langs = record.get("langs") or []
    if "en" not in langs:
        return

    text = record.get("text", "")
    if len(text) < 30:
        return

    # Skip bot-like posts: just a title/header with no real content
    # e.g. 'Feed: "Neuroscience News"\nPublished on Friday, ...'
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) <= 2 and len(text) < 80:
        return

    # Check quoted post text against exclusion filter — catches political
    # quote-posts that use science as metaphor (e.g., Pavlov quote-tweeting Trump)
    embed = record.get("embed") or {}
    quoted_text = ((embed.get("record") or {}).get("record") or {}).get("text", "")
    if quoted_text:
        from src.prefilter import _EXCLUSION_RE, _normalize_unicode
        if _EXCLUSION_RE.search(_normalize_unicode(quoted_text)):
            return

    # Extract hashtags from structured facets
    hashtags = _extract_hashtags(record)

    # Science hashtag bypasses keyword prefilter, but classifier still gates
    has_science_hashtag = check_hashtags(hashtags)
    if not has_science_hashtag and not passes_prefilter(text):
        return

    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    if has_science_hashtag:
        logger.info("Hashtag bypass: %s — tags: %s — %.80s", uri, hashtags, text)
    else:
        logger.info("Candidate: %s — %.80s", uri, text)

    # LLM classification — returns quality score 1-5
    score = classify_post(text, uri=uri)

    if score < QUALITY_THRESHOLD:
        logger.debug("Rejected (score=%d): %s", score, uri)
        return

    # Store approved post with quality score; initial feed_score = quality_score
    Post.insert(
        uri=uri, cid=cid, quality_score=score, feed_score=float(score)
    ).on_conflict_ignore().execute()
    logger.info("Approved (score=%d): %s", score, uri)


async def _consume() -> None:
    """Connect to Jetstream and process messages."""
    init_db()

    cursor = _get_cursor()
    url = JETSTREAM_URL
    if cursor:
        url += f"&cursor={cursor}"
        logger.info("Resuming from cursor: %d", cursor)

    msg_count = 0

    async with websockets.connect(url) as ws:
        logger.info("Connected to Jetstream")
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Track cursor
            time_us = msg.get("time_us")
            if time_us:
                msg_count += 1
                if msg_count % CURSOR_UPDATE_INTERVAL == 0:
                    _save_cursor(time_us)

            if msg.get("kind") != "commit":
                continue

            commit = msg.get("commit", {})
            operation = commit.get("operation")
            did = msg.get("did", "")
            rkey = commit.get("rkey", "")

            if operation == "delete":
                uri = f"at://{did}/app.bsky.feed.post/{rkey}"
                _handle_delete(uri)
            elif operation == "create":
                cid = commit.get("cid", "")
                record = commit.get("record", {})
                _handle_create(did, rkey, cid, record)


async def run() -> None:
    """Run the consumer with exponential backoff reconnect."""
    backoff = 1
    max_backoff = 60

    while True:
        try:
            await _consume()
        except (
            websockets.ConnectionClosed,
            websockets.InvalidURI,
            ConnectionError,
            OSError,
        ) as e:
            logger.warning("Connection lost: %s — reconnecting in %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception:
            logger.exception("Unexpected error — reconnecting in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        else:
            backoff = 1  # Reset on clean disconnect


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    loop = asyncio.new_event_loop()

    # Graceful shutdown on SIGINT/SIGTERM
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, loop.stop)

    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
