# How to Build Your Own AI-Curated Bluesky Feed

This guide walks you through creating a custom Bluesky feed that uses a locally-hosted LLM to filter and rank posts on any topic. By the end, you'll have a live feed that processes the full Bluesky firehose in real time.

NeuroBrain processes ~500 posts/sec and filters them down to a few quality science posts per hour. You can adapt this same architecture for any domain — music criticism, legal analysis, startup discussion, sports analytics, whatever you want to curate.

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** installed with a model pulled (e.g., `ollama pull qwen2.5:3b`)
- **A Bluesky account** with an [app password](https://bsky.app/settings/app-passwords)
- **A domain name** pointed at your server (Bluesky needs to reach your feed over HTTPS)
- **A server** that can run 24/7 (a cheap VPS works fine — the LLM is the bottleneck, and a 3B model runs on CPU if needed)

## Overview

A Bluesky custom feed has four parts:

```
1. Consumer     — connects to the firehose and filters posts
2. Database     — stores approved post URIs
3. Server       — serves the feed skeleton to Bluesky via HTTP
4. Registration — tells Bluesky your feed exists and where to find it
```

Bluesky's feed protocol is simple: your server returns a list of post URIs (the "skeleton"), and Bluesky hydrates them into full posts with author info, embeds, etc. You never need to store post content — just the `at://` URIs of posts you want to include.

## Step 1: Set Up the Project

```bash
mkdir my-feed && cd my-feed
python3 -m venv venv
source venv/bin/activate
pip install flask peewee websockets requests python-dotenv atproto
```

Create a `.env` file:

```bash
HOSTNAME=feed.yourdomain.com
HANDLE=your-handle.bsky.social
PASSWORD=your-app-password
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
# FEED_URI will be set after registration
FEED_URI=
```

## Step 2: Configuration

Create `src/config.py`:

```python
import os
from dotenv import load_dotenv

load_dotenv()

HOSTNAME = os.environ.get("HOSTNAME", "")
FEED_URI = os.environ.get("FEED_URI", "")
HANDLE = os.environ.get("HANDLE", "")
PASSWORD = os.environ.get("PASSWORD", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
SERVICE_DID = os.environ.get("SERVICE_DID", "")

if not SERVICE_DID and HOSTNAME:
    SERVICE_DID = f"did:web:{HOSTNAME}"
```

Create empty `src/__init__.py`:

```bash
touch src/__init__.py
```

## Step 3: Database

Create `src/database.py`. You only need two tables: one for approved posts and one for tracking your position in the firehose.

```python
import datetime
from peewee import (
    SqliteDatabase, Model, CharField, BigIntegerField,
    DateTimeField, IntegerField, FloatField,
)

db = SqliteDatabase("feed.db", pragmas={"journal_mode": "wal"})

class BaseModel(Model):
    class Meta:
        database = db

class Post(BaseModel):
    uri = CharField(unique=True, index=True)
    cid = CharField()
    indexed_at = DateTimeField(default=datetime.datetime.utcnow, index=True)
    score = FloatField(default=1.0, index=True)

class SubscriptionState(BaseModel):
    service = CharField(unique=True)
    cursor = BigIntegerField()

def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Post, SubscriptionState])
```

**Why SQLite?** It handles concurrent reads/writes via WAL mode, needs zero configuration, and is more than fast enough for this workload. You're writing a few posts per minute and reading a page of 50 on each feed request.

## Step 4: The Classifier

Create `src/classifier.py`. This is where you define **what your feed is about**. The system prompt is the most important part of your entire feed — spend time on it.

```python
import requests
from src.config import OLLAMA_URL, OLLAMA_MODEL

SYSTEM_PROMPT = """\
You are a classifier for a [YOUR TOPIC] feed. Rate the following social
media post on a scale of 1-5 for relevance.

5 - [What a perfect post looks like]
4 - [What a great post looks like]
3 - [Minimum acceptable quality]
2 - [Close but not good enough]
1 - [Not relevant at all]

ALWAYS score 1 for:
- [Things you explicitly want to exclude]
- [More things to exclude]

Respond with ONLY a single digit: 1, 2, 3, 4, or 5."""


def classify_post(text: str) -> int:
    """Classify a post using Ollama. Returns score 1-5 (0 on error)."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f'Post: "{text}"\nScore:'},
                ],
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 5},
            },
            timeout=10,
        )
        resp.raise_for_status()
        answer = resp.json()["message"]["content"].strip()
        for ch in answer:
            if ch.isdigit() and 1 <= int(ch) <= 5:
                return int(ch)
        return 1
    except Exception:
        return 0
```

### Tips for writing a good classifier prompt

- **Be specific about what you want**, not just the topic. "Expert discussion of machine learning papers" is better than "AI posts."
- **List explicit exclusions.** The LLM will let borderline content through unless you tell it not to. If you don't want memes, say so.
- **Use the full 1-5 scale** with clear distinctions between levels. This gives you a quality signal you can use for ranking.
- **Test extensively** before deploying. Run your prompt against 50+ real Bluesky posts and check the scores.
- **A 3B model is enough** for binary/scored classification. You don't need a 70B model — the prompt does the heavy lifting.

## Step 5: The Prefilter (Optional but Recommended)

If your topic has distinctive vocabulary, a keyword prefilter can reject 90-95% of posts before they reach the LLM. This is essentially free (regex matching) and dramatically reduces your LLM load.

Create `src/prefilter.py`:

```python
import re

# Words that strongly signal your topic
KEYWORDS = [
    r"your", r"topic", r"specific", r"terms",
    r"go", r"here",
]

# Words that signal off-topic content (reject even if keywords match)
EXCLUSIONS = [
    r"spam", r"off-topic", r"terms",
]

def _build_pattern(terms):
    joined = "|".join(terms)
    return re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)

_KEYWORD_RE = _build_pattern(KEYWORDS)
_EXCLUSION_RE = _build_pattern(EXCLUSIONS)

def passes_prefilter(text: str) -> bool:
    if _EXCLUSION_RE.search(text):
        return False
    return bool(_KEYWORD_RE.search(text))
```

Without a prefilter, every English post (~50/sec) hits your LLM. With one, you might only send 1-5 posts/sec. A 3B model on a decent GPU handles ~6 classifications/sec, so the prefilter is the difference between keeping up and falling behind.

**If your topic is broad** (e.g., "interesting posts") and you can't define keywords, skip the prefilter and use a bigger model or faster GPU.

## Step 6: The Consumer

Create `src/consumer.py`. This connects to Bluesky's Jetstream firehose and runs your pipeline on every post.

```python
import asyncio
import json
import logging
import websockets
from src.database import db, Post, SubscriptionState, init_db
from src.classifier import classify_post

logger = logging.getLogger(__name__)

JETSTREAM_URL = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)
QUALITY_THRESHOLD = 3  # Minimum score to include

def _get_cursor():
    try:
        state = SubscriptionState.get(SubscriptionState.service == "jetstream")
        return state.cursor
    except SubscriptionState.DoesNotExist:
        return None

def _save_cursor(cursor):
    SubscriptionState.insert(
        service="jetstream", cursor=cursor
    ).on_conflict(
        conflict_target=[SubscriptionState.service],
        update={SubscriptionState.cursor: cursor},
    ).execute()

def _handle_create(did, rkey, cid, record):
    # Filter: English only, minimum length
    if "en" not in (record.get("langs") or []):
        return
    text = record.get("text", "")
    if len(text) < 30:
        return

    # Optional: keyword prefilter
    # from src.prefilter import passes_prefilter
    # if not passes_prefilter(text):
    #     return

    # LLM classification
    score = classify_post(text)
    if score < QUALITY_THRESHOLD:
        return

    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    Post.insert(
        uri=uri, cid=cid, score=float(score)
    ).on_conflict_ignore().execute()
    logger.info("Approved (score=%d): %.80s", score, text)

async def consume():
    init_db()
    cursor = _get_cursor()
    url = JETSTREAM_URL
    if cursor:
        url += f"&cursor={cursor}"

    msg_count = 0
    async with websockets.connect(url) as ws:
        logger.info("Connected to Jetstream")
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            time_us = msg.get("time_us")
            if time_us:
                msg_count += 1
                if msg_count % 50 == 0:
                    _save_cursor(time_us)

            if msg.get("kind") != "commit":
                continue

            commit = msg.get("commit", {})
            if commit.get("operation") == "create":
                _handle_create(
                    msg.get("did", ""),
                    commit.get("rkey", ""),
                    commit.get("cid", ""),
                    commit.get("record", {}),
                )

async def run():
    while True:
        try:
            await consume()
        except Exception as e:
            logger.warning("Connection lost: %s — reconnecting in 5s", e)
            await asyncio.sleep(5)

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    asyncio.run(run())
```

Create `src/__main__.py` so you can run it as a module:

```python
from src.consumer import main
main()
```

### Key design decisions

- **Cursor persistence** — The consumer saves its position every 50 messages. On restart, it resumes from exactly where it left off. No posts are re-processed and no posts are missed.
- **`on_conflict_ignore()`** — If a post somehow gets processed twice, the duplicate is silently ignored.
- **English filter** — Jetstream provides the `langs` field from the post record. Filter here to avoid wasting LLM calls on languages your classifier wasn't designed for.

## Step 7: The Server

Create `src/server.py`. Bluesky calls three endpoints on your server:

```python
from flask import Flask, jsonify, request
from src.config import HOSTNAME, SERVICE_DID, FEED_URI
from src.database import Post, init_db
import datetime

app = Flask(__name__)
init_db()

@app.route("/.well-known/did.json")
def did_json():
    """Identity document — tells Bluesky who you are."""
    return jsonify({
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": SERVICE_DID,
        "service": [{
            "id": "#bsky_fg",
            "type": "BskyFeedGenerator",
            "serviceEndpoint": f"https://{HOSTNAME}",
        }],
    })

@app.route("/xrpc/app.bsky.feed.describeFeedGenerator")
def describe():
    """Tells Bluesky what feeds you serve."""
    return jsonify({
        "did": SERVICE_DID,
        "feeds": [{"uri": FEED_URI}],
    })

@app.route("/xrpc/app.bsky.feed.getFeedSkeleton")
def feed_skeleton():
    """Returns the feed — just a list of post URIs."""
    feed_param = request.args.get("feed")
    if feed_param != FEED_URI:
        return jsonify({"error": "Unsupported feed"}), 400

    cursor = request.args.get("cursor")
    limit = min(max(request.args.get("limit", 50, type=int), 1), 100)

    # Query posts, newest first (or by score — your choice)
    posts = Post.select().order_by(
        Post.score.desc(), Post.indexed_at.desc()
    ).limit(limit)

    # Cursor-based pagination
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

    if len(feed) < limit:
        new_cursor = None

    result = {"feed": feed}
    if new_cursor:
        result["cursor"] = new_cursor
    return jsonify(result)
```

### Understanding the feed protocol

Bluesky's feed system is elegant in its simplicity:

1. **Your server only returns post URIs** ("the skeleton"). Bluesky handles hydrating them into full posts with author info, images, embeds, like counts, etc.
2. **Cursor-based pagination** — When a user scrolls, Bluesky sends back the cursor from your last response. You use it to return the next page. The cursor format is yours to define — it just needs to be an opaque string that you can decode.
3. **The `did.json` endpoint** — This is how Bluesky verifies your server owns the domain. It must be served at `https://your-domain/.well-known/did.json`.

## Step 8: Register the Feed

Create `scripts/publish_feed.py`:

```python
from atproto import Client, models
from src.config import HANDLE, PASSWORD, SERVICE_DID

def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    record = models.AppBskyFeedGenerator.Record(
        did=SERVICE_DID,
        display_name="My Feed Name",       # Shows in Bluesky UI
        description="What this feed is about.",
        created_at=client.get_current_time_iso(),
    )

    # The rkey becomes part of your feed URI
    rkey = "my-feed"
    client.app.bsky.feed.generator.create(client.me.did, record, rkey=rkey)
    uri = f"at://{client.me.did}/app.bsky.feed.generator/{rkey}"
    print(f"Feed published! Set FEED_URI={uri} in your .env")

if __name__ == "__main__":
    main()
```

Run it:

```bash
PYTHONPATH=. python scripts/publish_feed.py
```

Copy the printed URI into your `.env` as `FEED_URI`, then restart your server.

## Step 9: Expose Your Server

Bluesky needs to reach your server over HTTPS. Options:

**Cloudflare Tunnel (recommended)** — Free, no port forwarding needed:
```bash
cloudflared tunnel create my-feed
cloudflared tunnel route dns my-feed feed.yourdomain.com
cloudflared tunnel run my-feed
```

**Caddy** — Automatic HTTPS with Let's Encrypt:
```
feed.yourdomain.com {
    reverse_proxy localhost:5000
}
```

**nginx + certbot** — The classic approach.

## Step 10: Run It

Start all three processes:

```bash
# Terminal 1: Consumer
python -m src.consumer

# Terminal 2: Server
python -c "from src.server import app; app.run(host='0.0.0.0', port=5000)"
```

For production, use systemd services (see `deploy/` in this repo for examples) so everything restarts automatically.

## Going Further

### Add engagement ranking

NeuroBrain's engagement updater (`src/engagement.py`) is a background process that fetches like/repost/reply counts from the Bluesky API every 5 minutes and recomputes feed scores. This lets popular posts within the same quality tier bubble up.

Key insight: **use engagement to rank within quality tiers, never across them.** Cap the engagement bonus below 1.0 so a viral score-3 post can never outrank a quiet score-5 post.

### Add time decay

Without time decay, a post that accumulates engagement will sit at the top of your feed forever. NeuroBrain v2 uses exponential decay with an 8-hour half-life — engagement matters most when it's fresh and fades over time, letting new content break through naturally.

### Add a prefilter for performance

If your LLM can't keep up with the firehose volume, a keyword prefilter can reject 90-95% of posts before they reach the model. This is the single biggest performance lever you have.

### Handle post deletions

When a user deletes a post on Bluesky, the firehose sends a delete event. You should handle this by removing the post from your database:

```python
if commit.get("operation") == "delete":
    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    Post.delete().where(Post.uri == uri).execute()
```

### Use a bigger model

A 3B model is fast and good enough for binary/scored classification. But if you want more nuanced filtering (e.g., distinguishing between types of expert discussion), try a 7B or 14B model. On a modern GPU, Qwen 2.5 14B can still classify in ~300ms.

### Monitor your feed quality

Log every classification decision so you can review what's being accepted and rejected:

```python
class ClassificationLog(BaseModel):
    uri = CharField()
    text = CharField()
    score = IntegerField()
    classified_at = DateTimeField(default=datetime.datetime.utcnow)
```

Periodically review the logs to tune your classifier prompt and prefilter keywords. The prompt is the most impactful thing to iterate on.

## Common Issues

**Feed shows "Unsupported algorithm"** — The `FEED_URI` in your `.env` doesn't match what was registered. Run the publish script again and copy the exact URI.

**Posts aren't appearing** — Check that Ollama is running (`ollama list`), the consumer is connected (look for "Connected to Jetstream" in logs), and your classifier isn't rejecting everything (lower `QUALITY_THRESHOLD` to 1 temporarily to test).

**Feed loads slowly** — Add database indexes on the columns you sort by. Peewee's `index=True` on field definitions handles this.

**"database disk image is malformed"** — Usually a corrupt index from a crash during schema migration. Fix with: `sqlite3 feed.db "REINDEX"`.

## License

MIT
