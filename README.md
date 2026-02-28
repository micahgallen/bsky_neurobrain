# NeuroBrain

A custom Bluesky feed that surfaces high-signal cognitive science posts using a locally-hosted LLM for classification.

**[View the feed on Bluesky](https://bsky.app/profile/micahgallen.com/feed/neurobrain)**

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
        |
        v
  Jetstream WebSocket (English posts only)
        |
        v
  Keyword Pre-Filter (regex, ~95% rejected)
        |
        v
  Ollama / Qwen 2.5 3B (binary classification, ~170ms on GPU)
        |
        v
  SQLite (approved post URIs)
        |
        v
  Flask API --> Bluesky app
```

1. A WebSocket consumer connects to Bluesky's Jetstream firehose and receives every new post in real time.
2. A keyword pre-filter does a fast regex scan against ~150 science terms. Posts without any matches are discarded immediately.
3. Posts that pass the pre-filter are sent to a Qwen 2.5 3B model running on Ollama for binary classification (RELEVANT / NOT_RELEVANT). The LLM distinguishes real research discussion from casual uses of science words.
4. Approved posts are stored in SQLite and served to the Bluesky app via a Flask API.

### Classification prompt

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
- Casual or figurative uses of "brain", "mind", "memory", or "free will"
- Personal anecdotes about thinking or feeling, even if using scientific vocabulary
- Motivational or poetic statements about cognition without scientific content

Respond with ONLY "RELEVANT" or "NOT_RELEVANT". Nothing else.

Post: "{post_text}"
Classification:
```

### Keyword pre-filter

Posts must contain at least one inclusion keyword and no exclusion keywords to reach the LLM. All matching is case-insensitive with word boundaries.

**Inclusion keywords:**

| Category | Keywords |
|----------|----------|
| Neuroscience | neurosci*, neuron*, synaps*, cortex, cortical, hippocampus, hippocampal, amygdala, prefrontal, cerebellum, dopamine, serotonin, norepinephrine, GABA, glutamate, neuroplasticity, axon*, dendrit*, glia*, astrocyte*, microglia, myelin, fMRI, EEG, MEG, neuroimaging, brain scan, connectome, tractography, optogenetics, electrophysiology, neurotransmitter*, neuropeptide*, neural circuit*, brain region*, thalamus, basal ganglia, striatum, brainstem, white matter, gray matter, blood-brain barrier, neuro*, CNS, PNS |
| Psychology | cognition, cognitive, perception, working memory, long-term memory, episodic memory, semantic memory, procedural memory, executive function, decision making, metacognition, cognitive load, priming, implicit memory, explicit memory, cognitive bias, heuristic*, psychophysics, reaction time, signal detection, mental model*, schema, chunking, interference, encoding, retrieval, habituation, sensitization, conditioning, reinforcement, developmental psych*, cognitive development, Piaget, Vygotsky, theory of mind, false belief, joint attention, psycholinguistic*, visual perception, auditory perception, multisensory, crossmodal |
| Philosophy of mind | consciousness, qualia, phenomenal, hard problem, explanatory gap, intentionality, mental representation, functionalism, dualism, physicalism, panpsychism, integrated information, global workspace, higher-order thought, neural correlates of consciousness, NCC, determinism, mental causation, supervenience, philosophy of mind, phenomenology, embodied cognition, enactivism, extended mind, predictive processing, Bayesian brain, active inference, free energy principle |
| Linguistics | syntax, morphology, phonology, phonetics, semantics, pragmatics, linguistic*, language acquisition, universal grammar, Chomsky, minimalism, generative grammar, neurolinguistic*, Broca, Wernicke, aphasia, dyslexia, bilingual*, multilingual*, speech perception, speech production, prosody, discourse, language processing, garden path, parsing, lexical access, word recognition, sentence processing, language comprehension |
| Cognitive anthropology | cognitive anthropology, cultural cognition, ethnoscience, folk taxonomy, cognitive ecology, distributed cognition, situated cognition, cultural evolution, cognitive niche, cumulative culture, social learning, imitation, emulation, cultural transmission, cognitive archaeology |
| Methods | peer-reviewed, preprint, study finds, researchers found, meta-analysis, replication, effect size, statistical significance, p-value, confidence interval, sample size, longitudinal, randomized controlled, double-blind, neuropsychology, computational model*, simulation, cognitive science, cogsci, behavioral experiment*, eye tracking, pupillometry, TMS, tDCS, lesion study, case study, single-cell recording |

**Exclusion keywords** (reject even if inclusion keywords match):

| Category | Keywords |
|----------|----------|
| Politics | Trump, Biden, Democrat*, Republican*, GOP, MAGA, election, vote, politician*, Congress, Senate, legislation, partisan, liberal, conservative, left-wing, right-wing, woke, anti-woke, cancel culture, culture war, immigration policy, gun control, abortion |
| Crypto | crypto, bitcoin, NFT, stonks, meme stock* |
| Pseudoscience | astrology, horoscope, zodiac, manifesting |
| Sports | sports score*, fantasy league*, game tonight |

## Tech stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12 |
| Firehose | Jetstream (WebSocket, JSON) |
| Pre-filter | Regex keyword matching |
| LLM | Ollama + Qwen 2.5 3B (Q4_K_M) via ROCm |
| Database | SQLite via Peewee ORM |
| Web server | Flask |
| Tunnel | Cloudflare Tunnel |
| Process manager | systemd |

## Project structure

```
src/
  config.py         # Environment variable loading
  database.py       # SQLite models (Post, SubscriptionState, ClassificationLog)
  prefilter.py      # Keyword pre-filter (~150 inclusion terms, exclusion terms)
  classifier.py     # Ollama LLM classifier (binary RELEVANT/NOT_RELEVANT)
  consumer.py       # Jetstream WebSocket consumer with auto-reconnect
  server.py         # Flask API (3 XRPC endpoints)
  algos/
    neurobrain.py   # Feed query + cursor pagination
scripts/
  publish_feed.py   # One-time feed registration with Bluesky
  unpublish_feed.py # Feed removal
  analyze_classifications.py  # Classification log analysis
deploy/
  neurobrain-server.service   # systemd unit for Flask
  neurobrain-consumer.service # systemd unit for Jetstream consumer
  neurobrain-tunnel.service   # systemd unit for Cloudflare tunnel
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

# Pull the LLM model
ollama pull qwen2.5:3b

# Initialize database and run
python -c "from src.database import init_db; init_db()"
python -m src.consumer &    # Start ingesting posts
python -c "from src.server import app; app.run(host='0.0.0.0', port=5000)"

# Register the feed with Bluesky
PYTHONPATH=. python scripts/publish_feed.py
```

## Deployment

The `deploy/` directory contains systemd service files for running the server, consumer, and Cloudflare tunnel as persistent services. See `docs/PROJECT_PLAN.md` for detailed deployment instructions.

## License

MIT
