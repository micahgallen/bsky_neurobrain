# NeuroBrain

A custom Bluesky feed that surfaces high-quality neuroscience and cognitive science posts using a real-time AI pipeline. The entire firehose (~500 posts/sec) is filtered down to a handful of expert-level science discussions per hour — no politics, no pop-sci, no noise.

**[View the feed on Bluesky](https://bsky.app/profile/micahgallen.com/feed/neurobrain)** | **[v2 (experimental)](https://bsky.app/profile/micahgallen.com/feed/neurobrain-v2)**

## What it covers

- **Neuroscience** — brain research, neural mechanisms, neuroimaging, neurotransmitters
- **Psychology** — cognition, perception, memory, attention, learning, decision-making
- **Philosophy of mind** — consciousness, qualia, mental representation
- **Linguistics** — syntax, semantics, language acquisition, psycholinguistics
- **Cognitive anthropology** — cultural cognition, cognitive ecology
- **Methods** — fMRI, EEG, behavioral experiments, computational models

Posts about politics, pop psychology, self-help, crypto, and off-topic noise are filtered out.

## How it works

```
Bluesky Firehose (~500 posts/sec)
    │
    ▼
Jetstream WebSocket
    │  English-only filter, min length, emoji/bot rejection
    │
    ▼
Keyword Prefilter (~0ms, ~95% rejected)
    │  312 inclusion terms across 6 domains
    │  Exclusion terms block politics, crypto, pseudoscience
    │  Science hashtags (#neuroscience, #cogsci, etc.) bypass keywords
    │
    ▼
LLM Classifier (~170ms on GPU)
    │  Ollama + Qwen 2.5 3B — quality score 1-5
    │  Score ≥ 3 accepted into feed
    │
    ▼
SQLite + Engagement Tracking
    │  Post URIs stored with quality scores
    │  Likes, reposts, replies, quotes fetched every 5 min
    │
    ▼
Feed Ranking Algorithm
    │  Quality tiers (score 3/4/5) with engagement + time decay
    │
    ▼
Flask API → Bluesky App
```

Each stage dramatically reduces volume before the next expensive operation. The prefilter is essentially free; only ~1-10 posts/sec reach the LLM.

### Three-stage filtering in detail

**Stage 1: Prefilter** — A regex scan against 312 science terms organized by domain (neuroscience, psychology, philosophy of mind, linguistics, cognitive anthropology, methods) plus 918 concept terms from the [Cognitive Atlas](https://www.cognitiveatlas.org/) (Poldrack et al., 2011). An exclusion list blocks posts containing political, crypto, or pseudoscience terms. Posts with science-relevant hashtags (e.g., `#neuroscience`, `#cogsci`) bypass keyword matching but still go through the LLM.

**Stage 2: LLM classifier** — Posts that pass the prefilter are scored 1-5 by a locally-hosted Qwen 2.5 3B model:

| Score | Meaning |
|-------|---------|
| 5 | Shares or discusses specific research, papers, data, or findings |
| 4 | Expert discussion: debates theories, critiques methods, shares domain insights |
| 3 | Informed content with genuine substance about the brain or cognition |
| 2 | Casual or superficial mention without depth |
| 1 | Not relevant: general health, politics, non-science |

Posts scoring 3+ are accepted. The classifier explicitly rejects general health science, clinical medicine, AI/ML (unless about biological cognition), and political content.

**Stage 3: Engagement ranking** — Accepted posts are ranked by a composite score combining quality and engagement within quality tiers. A score-3 post can never outrank a score-4 post regardless of engagement — quality is king.

### Feed ranking algorithms

Two ranking algorithms run in parallel on the same data:

**NeuroBrain (v1)** — Linear time decay:
```
engagement = likes + reposts×3 + replies×2 + quotes×4
bonus = min(log(1 + engagement) × 0.2, 0.95)
penalty = min(age_hours / 120, 0.5)
score = quality + bonus - penalty
```

**NeuroBrain v2** — Exponential decay with quality floor:
```
decay = exp(-ln(2) × age_hours / 8)          # 8-hour half-life
bonus = min(log(1 + engagement) × 0.2, 0.95) × decay
residual = 0.1 × max(0, quality - 3) × max(0, 1 - age_hours/48)
score = quality + bonus + residual
```

v2 lets fresh posts break through without needing to out-engage older content. Engagement value decays exponentially so a 16-hour-old post with 10 likes only barely leads a fresh post. Score 4-5 posts get a small residual bonus that fades over 48 hours.

## Tech stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12 |
| Firehose | Jetstream WebSocket |
| Prefilter | Regex keyword matching (312 terms + 918 Cognitive Atlas concepts) |
| LLM | Ollama + Qwen 2.5 3B via ROCm (AMD GPU) |
| Database | SQLite (WAL mode) via Peewee ORM |
| Web server | Flask |
| Tunnel | Cloudflare Tunnel |
| Process manager | systemd |

## Project structure

```
src/
  config.py             # Environment variable loading
  database.py           # SQLite models + automatic schema migration
  prefilter.py          # Keyword prefilter (312 terms + exclusions)
  classifier.py         # Ollama LLM classifier (quality score 1-5)
  consumer.py           # Jetstream WebSocket consumer with auto-reconnect
  engagement.py         # Background engagement metric updater (v1 + v2 scoring)
  server.py             # Flask API (3 XRPC endpoints)
  algos/
    neurobrain.py       # v1 feed ranking (linear decay)
    neurobrain_v2.py    # v2 feed ranking (exponential decay)
scripts/
  publish_feed.py               # Register NeuroBrain feed with Bluesky
  publish_neurobrain_v2_feed.py # Register v2 feed with Bluesky
  unpublish_feed.py             # Remove feed from Bluesky
  analyze_classifications.py    # Classification log analysis
deploy/
  neurobrain-server.service     # systemd unit for Flask
  neurobrain-consumer.service   # systemd unit for Jetstream consumer
  neurobrain-engagement.service # systemd unit for engagement updater
  neurobrain-tunnel.service     # systemd unit for Cloudflare tunnel
```

## Setup

```bash
# Clone and install
git clone https://github.com/micahgallen/bsky_neurobrain.git
cd bsky_neurobrain
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Bluesky handle, app password, hostname, etc.

# Install and pull the LLM model
# See https://ollama.com for installation instructions
ollama pull qwen2.5:3b

# Initialize database and start the pipeline
python -c "from src.database import init_db; init_db()"
python -m src.consumer &                           # Ingest posts
python -c "from src.engagement import main; main()" &  # Update engagement
python -c "from src.server import app; app.run(host='0.0.0.0', port=5000)"

# Register the feed with Bluesky (once)
PYTHONPATH=. python scripts/publish_feed.py
# Copy the printed FEED_URI into your .env file
```

## Deployment

The `deploy/` directory contains systemd service files for running the three processes and a Cloudflare tunnel as persistent services. Copy them to `/etc/systemd/system/`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now neurobrain-server neurobrain-consumer neurobrain-engagement neurobrain-tunnel
```

The consumer depends on `ollama.service` and will wait for the LLM to be available before starting.

## Architecture notes

- **Three independent processes** — The consumer, engagement updater, and server share no in-process state. They communicate through SQLite with WAL mode for concurrent read/write access.
- **Consumer resumes from cursor** — On restart, the consumer picks up exactly where it left off via a persisted Jetstream cursor. No posts are re-processed.
- **Quality tiers are inviolable** — The engagement bonus is capped below 1.0, so it can only reorder posts within the same quality tier, never promote a lower-quality post above a higher-quality one.
- **Hashtag bypass** — Posts with science-relevant hashtags (`#neuroscience`, `#cogsci`, `#neurobrain`, `#neuroskynece`, and ~20 others) skip the keyword prefilter but still go through the LLM classifier. This catches posts by scientists who don't happen to use the right vocabulary.

## Want to build your own?

See **[HOWTO.md](HOWTO.md)** for a step-by-step guide to creating your own AI-curated Bluesky feed for any topic.

## Acknowledgments

The keyword prefilter incorporates 918 cognitive science concept terms from the [Cognitive Atlas](https://www.cognitiveatlas.org/), a collaborative knowledge base for cognitive neuroscience.

> Poldrack RA, Kittur A, Kalar D, Miller E, Seppa C, Gil Y, Parker DS, Sabb FW and Bilder RM (2011). The Cognitive Atlas: Towards a knowledge foundation for cognitive neuroscience. *Front. Neuroinform.* 5:17. doi: [10.3389/fninf.2011.00017](https://doi.org/10.3389/fninf.2011.00017)

## License

MIT
