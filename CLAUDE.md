# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run consumer (ingests posts from Bluesky firehose)
venv/bin/python -m src.consumer

# Run Flask server
venv/bin/python -c "from src.server import app; app.run(host='0.0.0.0', port=5000)"

# Run engagement updater (fetches likes/reposts, computes feed scores)
venv/bin/python -c "from src.engagement import main; main()"

# Register/unregister feeds with Bluesky
PYTHONPATH=. venv/bin/python scripts/publish_feed.py
PYTHONPATH=. venv/bin/python scripts/publish_signal_feed.py
PYTHONPATH=. venv/bin/python scripts/unpublish_feed.py

# Analyze classification logs
venv/bin/python scripts/analyze_classifications.py

# Test prefilter
venv/bin/python -c "from src.prefilter import passes_prefilter; print(passes_prefilter('fMRI study on hippocampal memory'))"

# Test classifier (requires Ollama running)
venv/bin/python -c "from src.classifier import classify_post; print(classify_post('dopamine modulates working memory'))"

# Test politics classifier
venv/bin/python -c "from src.classifier import classify_politics; print(classify_politics('Trump is ruining the country'))"

# Test follow list loading
venv/bin/python -c "from src.follows import load_follows; from src.config import HANDLE, PASSWORD; print(f'{len(load_follows(HANDLE, PASSWORD))} follows')"

# Manage production services
sudo systemctl restart neurobrain-server neurobrain-consumer neurobrain-engagement neurobrain-tunnel
journalctl -u neurobrain-consumer -f   # watch consumer logs
journalctl -u neurobrain-engagement -f # watch engagement updater
```

## Architecture

Real-time pipeline that filters Bluesky's firehose down to cognitive science posts:

```
Jetstream WebSocket (~500 posts/sec)
    → consumer.py: English filter
    → consumer.py: hashtag extraction from facets (science tags bypass prefilter)
    → prefilter.py: two-tier keyword scan (~95% rejected, ~0ms)
        - Specific terms: single match passes (e.g., "hippocampal", "fMRI")
        - Broad terms: 2+ distinct matches required (e.g., "brain" + "memory")
    → classifier.py: Ollama/Qwen 2.5 3B quality scoring 1-5 (~170ms on GPU)
        - Score >= 3 accepted into feed
    → database.py: store post URI + quality score in SQLite
    → engagement.py: background job updates engagement metrics every 5 min
    → server.py: serve ranked feed skeleton to Bluesky via Flask
```

Each stage dramatically reduces volume before the next expensive operation. The prefilter is essentially free; only ~1-10 posts/sec reach the LLM.

### Signal feed (politics-free following feed)

Parallel path in the same consumer process:

```
Jetstream (~500 posts/sec)
    → consumer.py: Is author in follow set? (O(1) set lookup) — no → skip
    → consumer.py: English filter, min length
    → classifier.py: classify_politics() — YES/NO via Ollama (~140ms)
        - Political → drop
    → database.py: store in SignalPost table (chronological, no scoring)
    → algos/signal.py: serve chronological feed via 2-part cursor
```

Follow set is loaded at startup and refreshed every 30 minutes. A post can appear in both feeds.

### Key module relationships

- **`consumer.py`** is the pipeline orchestrator. It runs both NeuroBrain and Signal paths. For NeuroBrain: extracts hashtags, calls `prefilter.passes_prefilter()` and `prefilter.check_hashtags()`, then `classifier.classify_post()`. For Signal: checks follow set membership, calls `classifier.classify_politics()`. Writes to `Post`, `SignalPost`, and `SubscriptionState` tables.
- **`classifier.py`** calls Ollama's HTTP API (`POST /api/generate`) and returns a quality score 1-5. Logs every result to `ClassificationLog`. Takes an optional `uri` parameter for traceability.
- **`engagement.py`** runs as a separate process. Every 5 minutes it fetches engagement metrics (likes, reposts, replies, quotes) from the Bluesky API for posts from the last 48 hours and computes a composite `feed_score`.
- **`server.py`** is independent of the consumer. It reads from the `Post` table via the algo handler registered in `src/algos/__init__.py`.
- **`algos/neurobrain.py`** queries posts by `feed_score DESC, indexed_at DESC` with cursor pagination (`{score_x100}::{timestamp_ms}::{cid}` format, with legacy 2-part cursor support).
- **`algos/signal.py`** queries `SignalPost` by `indexed_at DESC` with simple 2-part cursor (`{timestamp_ms}::{cid}`).
- **`follows.py`** fetches the user's follow list via `atproto` client, returns a `set[str]` of DIDs for O(1) lookup.
- **`config.py`** loads `.env` via python-dotenv. `SERVICE_DID` auto-derives from `HOSTNAME` as `did:web:{HOSTNAME}` if not set explicitly.

### Three independent processes

The consumer, engagement updater, and server run as separate processes. The consumer writes posts to SQLite; the engagement updater reads and updates engagement data; the server reads for feed serving. They share no in-process state. SQLite WAL mode enables concurrent access.

## Deployment

Four systemd services in `deploy/`:
- `neurobrain-server.service` — Flask on port 5000
- `neurobrain-consumer.service` — Jetstream consumer (depends on `ollama.service`)
- `neurobrain-engagement.service` — Engagement metric updater
- `neurobrain-tunnel.service` — Cloudflare named tunnel (`neurobrain.uk` → localhost:5000)

Cloudflare tunnel config: `~/.cloudflared/config.yml`

Ollama systemd override: `/etc/systemd/system/ollama.service.d/override.conf` (sets `OLLAMA_HOST=127.0.0.1` and `HSA_OVERRIDE_GFX_VERSION=10.3.0` for AMD RX 6700 XT)

## Constraints

- **NeuroBrain cursor format is `{score_x100}::{timestamp_ms}::{cid}`** — used by the NeuroBrain feed handler for keyset pagination. Legacy `{timestamp_ms}::{cid}` format also supported.
- **Signal cursor format is `{timestamp_ms}::{cid}`** — simple chronological pagination.
- **Scripts need `PYTHONPATH=.`** — `scripts/` files import from `src.*` but aren't inside the package.
- **Ollama must be running** for the consumer to classify posts. Without it, posts that pass the prefilter get logged as ERROR and rejected.
- **Consumer resumes from cursor** — `SubscriptionState` stores `time_us` (Unix microseconds). On restart, no posts are re-processed. Cursor is persisted every 50 messages.
- **Flask must NOT run with `debug=True`** in production — it enables remote code execution via the Werkzeug debugger.
- **`.env` contains the Bluesky app password** — never commit it. File permissions should be `600`.
- **SQLite WAL mode** — enabled for concurrent read/write access from consumer, engagement updater, and server.
