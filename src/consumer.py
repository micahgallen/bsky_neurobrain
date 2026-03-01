import asyncio
import json
import logging
import re
import signal
import time

import websockets

from src.config import HANDLE, PASSWORD, SIGNAL_FEED_URI, INTERO_FEED_URI
from src.database import db, Post, SignalPost, InteroPost, PoliticsLog, SubscriptionState, init_db
from src.prefilter import passes_prefilter, check_hashtags
from src.classifier import classify_post, classify_politics, classify_intero
from src.intero_prefilter import passes_intero_prefilter

logger = logging.getLogger(__name__)

JETSTREAM_URL = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)
SERVICE_NAME = "jetstream"
CURSOR_UPDATE_INTERVAL = 50  # Update cursor every N messages
QUALITY_THRESHOLD = 3  # Minimum score to include in feed
FOLLOW_REFRESH_INTERVAL = 1800  # Refresh follow list every 30 minutes

# Follow set and last refresh time (module-level for access in _handle_create)
_follow_set: set[str] = set()
_follow_set_updated: float = 0


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
    deleted_signal = SignalPost.delete().where(SignalPost.uri == uri).execute()
    if deleted_signal:
        logger.info("Deleted signal post: %s", uri)
    deleted_intero = InteroPost.delete().where(InteroPost.uri == uri).execute()
    if deleted_intero:
        logger.info("Deleted intero post: %s", uri)


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


def _handle_signal(did: str, rkey: str, cid: str, text: str) -> None:
    """Process a post for the Signal feed (followed accounts, no politics)."""
    if not _follow_set or did not in _follow_set:
        return

    if classify_politics(text):
        uri = f"at://{did}/app.bsky.feed.post/{rkey}"
        logger.debug("Signal rejected (political): %s", uri)
        PoliticsLog.create(did=did)
        return

    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    SignalPost.insert(uri=uri, cid=cid).on_conflict_ignore().execute()
    logger.info("Signal approved: %s — %.80s", uri, text)


def _handle_intero(did: str, rkey: str, cid: str, text: str) -> None:
    """Process a post for the Interoception feed (prefilter → binary classifier)."""
    if not passes_intero_prefilter(text):
        return

    uri = f"at://{did}/app.bsky.feed.post/{rkey}"

    if not classify_intero(text):
        logger.debug("Intero rejected (classifier): %s", uri)
        return

    InteroPost.insert(uri=uri, cid=cid).on_conflict_ignore().execute()
    logger.info("Intero approved: %s — %.80s", uri, text)


def _handle_create(did: str, rkey: str, cid: str, record: dict) -> None:
    """Process a new post through the filter pipeline."""
    # English only
    langs = record.get("langs") or []
    if "en" not in langs:
        return

    text = record.get("text", "")
    if len(text) < 30:
        return

    # Signal feed: check followed accounts (runs before NeuroBrain filters)
    if SIGNAL_FEED_URI:
        _handle_signal(did, rkey, cid, text)

    # Interoception feed: prefilter only, no classifier
    if INTERO_FEED_URI:
        _handle_intero(did, rkey, cid, text)

    # Skip bot-like posts: just a title/header with no real content
    # e.g. 'Feed: "Neuroscience News"\nPublished on Friday, ...'
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) <= 2 and len(text) < 80:
        return

    # Skip emoji-heavy posts — bots and promotional accounts use heavy emoji;
    # real scientists almost never do. Threshold: 4+ emoji in a single post.
    emoji_count = len(re.findall(
        r"[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF"
        r"\U0000200D\U00002B50\U00002B55\U000023CF\U000023E9-\U000023F3"
        r"\U000023F8-\U000023FA\U0000231A\U0000231B]",
        text,
    ))
    if emoji_count >= 4:
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


def _refresh_follows() -> None:
    """Load or refresh the follow set if needed."""
    global _follow_set, _follow_set_updated
    if not SIGNAL_FEED_URI or not HANDLE or not PASSWORD:
        return
    now = time.monotonic()
    if now - _follow_set_updated < FOLLOW_REFRESH_INTERVAL and _follow_set:
        return
    try:
        from src.follows import load_follows
        _follow_set = load_follows(HANDLE, PASSWORD)
        _follow_set_updated = now
    except Exception:
        logger.exception("Failed to refresh follow set")


async def _consume() -> None:
    """Connect to Jetstream and process messages."""
    init_db()
    _refresh_follows()

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
                    _refresh_follows()

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
