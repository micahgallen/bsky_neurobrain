# NeuroBrain: Bluesky Cognitive Science Feed Generator

## Project Overview

A custom Bluesky feed that surfaces high-signal cognitive science posts using a locally-hosted LLM for classification. The feed covers neuroscience, psychology, cognitive anthropology, philosophy of mind, linguistics, and closely related fields — with strict exclusion of politics, culture war, and off-topic noise.

**Deployed on:** Local Linux server (nexus) — Ryzen 7 5800X, 32GB RAM, AMD RX 6700 XT (12GB VRAM)

---

## Architecture

```
Bluesky Network
     |
     v
[Jetstream WebSocket] ──> wss://jetstream1.us-east.bsky.network/subscribe
     |                     (filtered to app.bsky.feed.post only)
     v
[Keyword Pre-Filter] ──> Fast regex/keyword scan (~95% of posts rejected here)
     |                    Cost: ~0ms per post
     v
[Ollama / Qwen 2.5 3B] ──> Binary classification: RELEVANT or NOT_RELEVANT
     |                      Running on RX 6700 XT via ROCm
     |                      ~50-80 tok/s, <1s per classification
     v
[SQLite Database] ──> Store approved post URIs + CIDs
     |
     v
[Flask API Server] ──> Serves getFeedSkeleton to Bluesky
     |                  Endpoints: /.well-known/did.json
     |                             /xrpc/app.bsky.feed.describeFeedGenerator
     |                             /xrpc/app.bsky.feed.getFeedSkeleton
     v
Bluesky App (users see the feed)
```

---

## Tech Stack

| Layer           | Technology                          | Why                                                    |
|-----------------|-------------------------------------|--------------------------------------------------------|
| Language        | Python 3.13                         | Best ecosystem for AI/ML, good AT Protocol SDK         |
| Firehose        | Jetstream (WebSocket, JSON)         | Much simpler than raw CBOR firehose, no decoding needed|
| WebSocket Client| `websockets` library                | Async, lightweight, well-maintained                    |
| Pre-filter      | Regex + keyword matching            | Eliminates ~95% of posts before LLM sees them          |
| LLM Runtime     | Ollama with ROCm                    | Simplest path to GPU inference on AMD                  |
| LLM Model       | Qwen 2.5 3B (Q8 quantization)      | ~3.5GB VRAM, 50-80 tok/s, accurate enough for classification |
| Database        | SQLite via Peewee ORM               | Simple, no server needed, plenty fast for this volume  |
| Web Server      | Flask                               | Lightweight, serves 3 XRPC endpoints                   |
| AT Protocol SDK | `atproto` (MarshalX)                | Feed registration, models, types                       |
| Process Manager | systemd                             | Runs firehose consumer + web server as services        |

### Fallback Model Options

If Qwen 2.5 3B isn't accurate enough:
- **Qwen 2.5 7B (Q4_K_M)**: ~5-6GB VRAM, ~35-45 tok/s — more accurate, still fast
- **GPT-OSS 20B**: Tight on 12GB VRAM, ~30 tok/s — nuclear option for accuracy

---

## Component Details

### 1. Jetstream Consumer (`consumer.py`)

Connects to Bluesky's Jetstream and processes posts in real-time.

```
Connection URL:
  wss://jetstream1.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post

Message format (post create):
{
  "did": "did:plc:...",
  "time_us": 1725911162329308,
  "kind": "commit",
  "commit": {
    "rev": "3l3qo2vutsw2b",
    "operation": "create",
    "collection": "app.bsky.feed.post",
    "rkey": "3l3qo2vutsw2b",
    "record": {
      "text": "The post content...",
      "createdAt": "2024-09-09T15:00:00.000Z",
      "langs": ["en"]
    },
    "cid": "bafyrei..."
  }
}
```

**Responsibilities:**
- Maintain persistent WebSocket connection with auto-reconnect
- Track cursor position (Unix microseconds) for replay on restart
- Filter to English-language posts only (`langs` contains "en")
- Pass posts through keyword pre-filter
- Send candidates to LLM classifier
- Store approved posts in SQLite
- Handle post deletions (remove from DB)

### 2. Keyword Pre-Filter (`prefilter.py`)

Fast first-pass to reduce LLM load. The firehose produces hundreds of posts/second — we only want to send ~1-10/sec to the LLM.

**Strategy:** Case-insensitive regex matching against a curated keyword list. A post must contain at least one keyword to be considered a candidate.

**Keyword categories:**

```
NEUROSCIENCE:
  neurosci, neuron, synapse, synaptic, cortex, cortical, hippocampus,
  amygdala, prefrontal, cerebellum, dopamine, serotonin, norepinephrine,
  GABA, glutamate, neuroplasticity, axon, dendrite, glia, astrocyte,
  microglia, myelin, fMRI, EEG, MEG, neuroimaging, brain scan,
  connectome, tractography, optogenetics, electrophysiology,
  neurotransmitter, neuropeptide, neural circuit, brain region,
  thalamus, basal ganglia, striatum, brainstem, white matter,
  gray matter, blood-brain barrier, neural network (biological context),
  brain, neuro, CNS, PNS

PSYCHOLOGY:
  cognition, cognitive, perception, attention, working memory,
  long-term memory, episodic memory, semantic memory, procedural memory,
  executive function, decision making, metacognition, cognitive load,
  priming, implicit, explicit memory, cognitive bias, heuristic,
  psychophysics, reaction time, signal detection, mental model,
  schema, chunking, interference, encoding, retrieval, recognition,
  recall, habituation, sensitization, conditioning, reinforcement,
  developmental psych, cognitive development, Piaget, Vygotsky,
  theory of mind, false belief, joint attention, psycholinguistics,
  visual perception, auditory perception, multisensory, crossmodal

PHILOSOPHY OF MIND:
  consciousness, qualia, phenomenal, hard problem, explanatory gap,
  intentionality, mental representation, functionalism, dualism,
  physicalism, panpsychism, integrated information, global workspace,
  higher-order thought, neural correlates of consciousness, NCC,
  free will, determinism, mental causation, supervenience, emergence,
  philosophy of mind, phenomenology, embodied cognition,
  enactivism, extended mind, predictive processing, Bayesian brain,
  active inference, free energy principle

LINGUISTICS:
  syntax, morphology, phonology, phonetics, semantics, pragmatics,
  linguistic, language acquisition, universal grammar, Chomsky,
  minimalism, generative grammar, psycholinguistics, neurolinguistics,
  Broca, Wernicke, aphasia, dyslexia, bilingual, multilingual,
  speech perception, speech production, prosody, discourse,
  language processing, garden path, parsing, lexical access,
  word recognition, sentence processing, language comprehension

COGNITIVE ANTHROPOLOGY:
  cognitive anthropology, cultural cognition, ethnoscience,
  folk taxonomy, cognitive ecology, distributed cognition,
  situated cognition, cultural evolution, cognitive niche,
  cumulative culture, social learning, imitation, emulation,
  cultural transmission, cognitive archaeology

METHODS / GENERAL:
  peer-reviewed, preprint, journal, study finds, researchers found,
  meta-analysis, replication, effect size, statistical significance,
  p-value, confidence interval, sample size, longitudinal,
  randomized controlled, double-blind, neuropsychology,
  computational model, simulation, cognitive science, cogsci,
  behavioral experiment, eye tracking, pupillometry, TMS,
  tDCS, lesion study, case study, single-cell recording
```

**Exclusion keywords** (reject even if science keywords present):
```
  Trump, Biden, Democrat, Republican, GOP, MAGA, election, vote,
  politician, Congress, Senate, legislation, partisan, liberal,
  conservative, left-wing, right-wing, woke, anti-woke, cancel culture,
  culture war, immigration policy, gun control, abortion,
  crypto, bitcoin, NFT, stonks, meme stock,
  astrology, horoscope, zodiac, manifesting, vibes,
  sports score, fantasy league, game tonight
```

### 3. LLM Classifier (`classifier.py`)

Sends candidate posts to Ollama for semantic classification.

**Ollama API call:**
```
POST http://localhost:11434/api/generate
{
  "model": "qwen2.5:3b",
  "prompt": "<system prompt + post text>",
  "stream": false,
  "options": {
    "temperature": 0,
    "num_predict": 10
  }
}
```

**System prompt (draft):**
```
You are a classifier for a cognitive science feed. Classify the following
social media post as RELEVANT or NOT_RELEVANT.

RELEVANT posts are about:
- Neuroscience (brain research, neural mechanisms, neuroimaging, neurotransmitters)
- Psychology (cognition, perception, memory, attention, learning, decision-making)
- Cognitive anthropology (cultural cognition, cognitive ecology)
- Philosophy of mind (consciousness, qualia, mental representation, free will)
- Linguistics (syntax, semantics, language acquisition, psycholinguistics)
- Cognitive science methods (fMRI, EEG, behavioral experiments, computational models)

NOT_RELEVANT posts include:
- Political opinions or policy debates, even if they mention science
- Pop psychology or self-help without scientific substance
- Science-adjacent content that is primarily social commentary
- Posts about AI/ML unless explicitly about biological cognition or brain-inspired models
- Clinical/medical advice (psychiatry prescriptions, therapy recommendations)
- Posts primarily promoting a product, event, or personal brand

Respond with ONLY "RELEVANT" or "NOT_RELEVANT". Nothing else.

Post: "{post_text}"
Classification:
```

**Implementation notes:**
- Use `temperature: 0` for deterministic classification
- Use `num_predict: 10` to cap output (we only need one word)
- Parse response: if starts with "RELEVANT" → approve, otherwise reject
- Timeout after 5 seconds, treat as NOT_RELEVANT
- Log all classifications for later analysis and prompt tuning

### 4. Database (`database.py`)

SQLite via Peewee ORM. Minimal schema — Bluesky hydrates post content itself.

```python
class Post:
    uri         # at://did:plc:.../app.bsky.feed.post/rkey (indexed)
    cid         # Content ID
    indexed_at  # When we approved this post (indexed, for cursor pagination)

class SubscriptionState:
    service     # "jetstream" (unique)
    cursor      # Last processed time_us for resume on restart

class ClassificationLog:  # Optional, for tuning
    uri         # Post URI
    text        # Post text (for review)
    result      # RELEVANT / NOT_RELEVANT
    classified_at
```

**Retention:** Posts older than 30 days are pruned (cron job or on-startup cleanup). Nobody scrolls a feed that far back.

### 5. Web Server (`server.py`)

Flask app serving the three required XRPC endpoints.

**Endpoint 1: `GET /.well-known/did.json`**
Returns DID document for service discovery.

**Endpoint 2: `GET /xrpc/app.bsky.feed.describeFeedGenerator`**
Returns feed metadata (DID + list of feed URIs).

**Endpoint 3: `GET /xrpc/app.bsky.feed.getFeedSkeleton`**
The core endpoint. Accepts `feed`, `cursor`, `limit` params. Returns paginated list of approved post URIs from SQLite, ordered by `indexed_at` descending.

**Cursor format:** `{timestamp_ms}::{cid}` — standard approach from the reference implementation.

### 6. Feed Registration (`publish_feed.py`)

One-time script to register the feed with Bluesky using the `atproto` SDK.

```
Record type: app.bsky.feed.generator
Record name: neurobrain
Display name: NeuroBrain
Description: Curated cognitive science feed — neuroscience, psychology,
             philosophy of mind, linguistics. Pure science, no politics.
```

---

## Server Setup (nexus)

### ROCm + Ollama Setup

```bash
# 1. Install ROCm 6.4+ (follow AMD docs for Ubuntu)
# 2. Set GPU override for RX 6700 XT (gfx1031 → gfx1030)
echo 'export HSA_OVERRIDE_GFX_VERSION=10.3.0' >> ~/.bashrc

# 3. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 4. Configure Ollama systemd for AMD GPU
sudo systemctl edit ollama.service
# Add:
# [Service]
# Environment="HSA_OVERRIDE_GFX_VERSION=10.3.0"

# 5. Pull the model
ollama pull qwen2.5:3b

# 6. Verify GPU inference
ollama run qwen2.5:3b "Hello, world"
# Check: nvidia-smi equivalent → rocm-smi should show GPU utilization
```

### Application Setup

```bash
# Clone/create project on nexus
cd /opt/neurobrain  # or wherever

# Python venv
python3.13 -m venv venv
source venv/bin/activate

# Dependencies
pip install flask peewee websockets requests python-dotenv atproto

# Environment variables (.env)
HOSTNAME=neurobrain.yourdomain.com  # or use a tunnel
FEED_URI=at://did:plc:YOUR_DID/app.bsky.feed.generator/neurobrain
HANDLE=your-handle.bsky.social
PASSWORD=your-app-password
SERVICE_DID=did:web:neurobrain.yourdomain.com
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

### Exposing to the Internet

The feed server needs to be reachable via HTTPS on port 443. Options:

1. **Cloudflare Tunnel (recommended):** Free, no port forwarding, automatic HTTPS
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```
   Then configure a permanent tunnel with a custom domain.

2. **Reverse proxy (nginx + Let's Encrypt):** If you have a domain pointed at your IP
3. **ngrok:** Quick for testing, not great for production

---

## Project Structure

```
bsky_neurobrain/
├── docs/
│   └── PROJECT_PLAN.md          # This file
├── src/
│   ├── __init__.py
│   ├── server.py                # Flask web server (3 XRPC endpoints)
│   ├── consumer.py              # Jetstream WebSocket consumer (async)
│   ├── prefilter.py             # Keyword pre-filter
│   ├── classifier.py            # Ollama LLM classifier
│   ├── database.py              # SQLite models (Peewee)
│   ├── config.py                # Environment variable loading
│   └── algos/
│       ├── __init__.py          # Algorithm registry
│       └── neurobrain.py        # Feed algorithm (query + pagination)
├── scripts/
│   ├── publish_feed.py          # One-time feed registration
│   └── unpublish_feed.py        # Feed removal
├── .env.example
├── requirements.txt
└── README.md                    # (only if needed)
```

---

## Implementation Order

### Phase 1: Core Infrastructure
1. Set up project structure, virtualenv, dependencies
2. Implement `config.py` (env loading)
3. Implement `database.py` (SQLite schema)
4. Implement `server.py` (Flask + 3 endpoints)
5. Implement `algos/neurobrain.py` (feed query + cursor pagination)

### Phase 2: Ingestion Pipeline
6. Implement `prefilter.py` (keyword matching)
7. Implement `classifier.py` (Ollama API client)
8. Implement `consumer.py` (Jetstream WebSocket + pipeline integration)

### Phase 3: Deployment
9. Set up Ollama + ROCm on nexus
10. Deploy application on nexus (systemd services)
11. Set up Cloudflare Tunnel or reverse proxy
12. Register feed with Bluesky (`publish_feed.py`)

### Phase 4: Tuning
13. Monitor classification logs, tune prompt
14. Adjust keyword lists based on false positives/negatives
15. Consider stepping up to Qwen 7B if accuracy needs improvement

---

## Key Design Decisions

**Why Jetstream over raw firehose?**
Raw firehose uses DAG-CBOR binary encoding and requires the `atproto` SDK's `FirehoseSubscribeReposClient`. Jetstream gives us clean JSON over WebSocket — much simpler to work with, debug, and log. The tradeoff is a slight delay (milliseconds) which doesn't matter for a curated feed.

**Why keyword pre-filter before LLM?**
The firehose is ~500+ posts/second. Even with a fast model, sending every post to the LLM would create a bottleneck. The keyword filter is essentially free and eliminates ~95%+ of posts. The LLM only sees plausible candidates.

**Why Qwen 2.5 3B over smaller/larger?**
- 0.5B/1.5B: Fast but may struggle with nuanced classification (e.g., distinguishing pop psychology from real research)
- 3B: Sweet spot — fits easily in 12GB VRAM at Q8 (best quantization quality), fast enough at 50-80 tok/s
- 7B: Available as fallback but unnecessary overhead for binary classification
- GPT-OSS 20B: Too large for the task, tight on VRAM

**Why SQLite over PostgreSQL?**
We're storing post URIs (tiny records), querying by timestamp (simple index), on a single server. SQLite is perfect for this scale and eliminates a dependency. If the feed somehow goes viral and needs to scale, PostgreSQL is an easy migration.

**Why Flask over FastAPI?**
The web server is dead simple — 3 endpoints, no async needed on the serving side. Flask is the path of least resistance. The async work (WebSocket consumer) runs in a separate process.

---

## Estimated Data Volume

- Bluesky firehose: ~500 posts/second (and growing)
- After English filter: ~200 posts/second
- After keyword pre-filter: ~1-10 posts/second (rough estimate)
- After LLM classification: ~0.1-2 posts/second approved
- Daily approved posts: ~5,000-50,000 (very rough)
- Database size at 30-day retention: Negligible (< 100MB)
