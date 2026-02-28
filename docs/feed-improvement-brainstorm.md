# Feed Improvement Brainstorm

Date: 2026-02-28

## Diagnosis

Three compounding problems:

1. **Recall gap at prefilter** — keyword list is thorough for technical vocabulary but misses accessible-language posts about neuroscience/cogsci. "New study shows sleep consolidates what we learned today" hits zero regexes.
2. **Precision gap at classifier** — Qwen 2.5 3B with zero-shot binary prompt can't distinguish substantive science from casual keyword usage ("my brain is fried lol serotonin machine broke").
3. **No quality signal in feed** — pure chronological ordering. A landmark paper with 200 likes sits at same level as a shower thought.

## Ideas

### A. Widen the prefilter funnel

Add broader terms (`brain`, `memory`, `attention`, `learning`, `psychology`, `study shows`, `research`, `experiment`). Require 2+ matches for vague terms, or pair a vague term with a science-adjacent term. Prefilter is ~0ms so even 3x candidate volume is fine for the classifier to handle.

### B. Use hashtags/facets from Jetstream records

Bluesky post records include structured `facets` with hashtags. Posts tagged `#neuroscience`, `#cogsci`, `#brainscience` etc. should auto-pass prefilter. Free signal currently being ignored.

### C. Graduated scoring instead of binary classification

Change classifier from RELEVANT/NOT_RELEVANT to 1-5 quality score:
- **5**: Original research, paper discussion, expert insight
- **4**: Substantive discussion of cogsci topic
- **3**: Science-adjacent, interesting but not deep
- **2**: Casual mention, pop-sci
- **1**: Noise that happens to use scientific vocabulary

Store score in Post table. Threshold (>= 3) for inclusion, use score for ranking. Fixes both precision and ranking.

### D. Author reputation tracking

Track `{DID -> count_of_quality_posts}`. Authors with 3+ quality posts get:
- Auto-pass through prefilter
- Score boost in feed

Creates positive flywheel: good sources discovered, future posts prioritized.

### E. Engagement-based boosting ("rising posts")

Background job every ~10 minutes:
1. Call Bluesky API (`app.bsky.feed.getPosts`) for recent approved posts (batch 25 URIs per call)
2. Fetch like count, repost count, reply count
3. Compute engagement velocity: `(likes + 2*reposts) / hours_since_posted`
4. Posts with high velocity get boosted in feed ranking

Surfaces posts the broader community finds valuable.

### F. Embedding-based semantic prefilter

Use small embedding model (`all-MiniLM-L6-v2`, ~1ms on CPU). Cosine similarity against seed embeddings from best classified posts. Threshold ~0.3 to pass. Catches semantic matches no keyword list finds — e.g., "how does the hippocampus know which memories to keep?"

### G. Hybrid feed ranking score

Replace pure `indexed_at DESC` with composite:

```
feed_score = (quality_score * author_reputation * engagement_boost) / age_decay
```

Where `age_decay = hours_since_posted ^ 0.5` (gentle decay). Makes feed feel alive — high-quality posts from known-good authors with engagement rise to top.

### H. Seed list bootstrap

Curate 20-50 known neuroscience/cogsci accounts. Bypass prefilter for their posts. Use output to calibrate classifier. Periodic backfill by polling their feeds hourly.

## Implementation Priority

**First batch:**
1. C — Graduated scoring (highest leverage, fixes ranking + precision)
2. B — Hashtags (trivially easy, immediate recall improvement)
3. A — Loosen prefilter (easy, improves recall)
4. E — Engagement boosting (the "rising" algorithm)

**Second batch:**
- F — Embedding prefilter (great recall improvement, more setup work)
- G — Hybrid ranking (natural extension once C and E are done)
- D — Author reputation (flywheel effect, needs data accumulation)
- H — Seed list (good bootstrap, manual curation effort)
