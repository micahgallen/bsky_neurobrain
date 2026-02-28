import logging
import datetime

import requests

from src.config import OLLAMA_URL, OLLAMA_MODEL, CLASSIFIER_VERSION
from src.database import db, ClassificationLog

logger = logging.getLogger(__name__)

# v1: Topic relevance — "is this post about cognitive science?"
_PROMPT_V1 = """\
You are a classifier for a cognitive science feed. Rate the following social \
media post on a scale of 1-5 for relevance to cognitive science.

SCORING RUBRIC:
5 - Original research, paper discussion, expert scientific insight
4 - Substantive discussion of a cognitive science topic with real content
3 - Science-adjacent, interesting but not deep (e.g., pop-sci article summary)
2 - Casual mention of a scientific topic, pop-psychology without substance
1 - Noise: figurative language, off-topic despite scientific vocabulary

RELEVANT topics include:
- Neuroscience (brain research, neural mechanisms, neuroimaging, neurotransmitters)
- Psychology (cognition, perception, memory, attention, learning, decision-making)
- Cognitive anthropology (cultural cognition, cognitive ecology)
- Philosophy of mind (consciousness, qualia, mental representation, free will)
- Linguistics (syntax, semantics, language acquisition, psycholinguistics)
- Cognitive science methods (fMRI, EEG, behavioral experiments, computational models)

SCORE 1-2 (not relevant) for:
- Political opinions or policy debates, even if they mention science
- Pop psychology or self-help without scientific substance
- Science-adjacent content that is primarily social commentary
- Posts about AI/ML unless explicitly about biological cognition or brain-inspired models
- Clinical/medical advice (psychiatry prescriptions, therapy recommendations)
- Posts primarily promoting a product, event, or personal brand
- Casual or figurative uses of "brain", "mind", "memory", or "free will"
- Personal anecdotes about thinking or feeling, even if using scientific vocabulary
- Motivational or poetic statements about cognition without scientific content

Respond with ONLY a single digit: 1, 2, 3, 4, or 5. Nothing else."""

# v2: Expert detection — "does this sound like a scientist being a scientist?"
_PROMPT_V2 = """\
You are a classifier for a cognitive science feed. Your job is to detect \
whether a post sounds like it was written by a scientist or academic expert.

We want to catch scientists being scientists: sharing their papers, debating \
theories, musing about ideas, discussing findings, even academic drama and \
gossip. The specific topic matters less than whether the author demonstrates \
genuine scientific expertise and insider knowledge.

Rate the post 1-5:
5 - Clearly a scientist: shares or discusses specific research, papers, data, \
or findings with insider knowledge and technical fluency
4 - Very likely a scientist: engages with scientific ideas at a professional \
level, expresses informed opinions, debates with nuance and depth
3 - Informed contributor: demonstrates real knowledge of the field, could be \
a grad student, science journalist, or educated enthusiast adding genuine insight
2 - Layperson: uses scientific terms but without real expertise, restates \
textbook basics, shares pop-sci links without adding insight
1 - Not scientific: uses science words as metaphor, political commentary, \
personal anecdote, self-help, motivational content

SOUNDS LIKE A SCIENTIST (score 4-5):
- References specific studies, papers, datasets, or conferences
- Uses technical terminology naturally as part of normal vocabulary
- Discusses methodology, limitations, or implications
- Expresses informed disagreement or debate with other researchers
- Shares their own or colleagues' work
- Discusses scientific ideas with assumed background knowledge
- Academic tone: even casual posts show deep familiarity with the field
- Inside-baseball academic discussion (hiring, review, scientific culture)

DOES NOT SOUND LIKE A SCIENTIST (score 1-2):
- Uses scientific terms as political weapons ("dementia", "brainwashed")
- Restates textbook definitions without adding original thought
- Personal anecdotes dressed in scientific vocabulary
- Pop-psychology platitudes or self-help framing
- Primarily emotional or political rather than analytical
- Vague "studies show" without specifics or engagement

Respond with ONLY a single digit: 1, 2, 3, 4, or 5. Nothing else."""

_PROMPTS = {
    "v1": _PROMPT_V1,
    "v2": _PROMPT_V2,
}


def classify_post(text: str, uri: str = "") -> int:
    """Classify a post using Ollama. Returns quality score 1-5 (0 on error)."""
    system_prompt = _PROMPTS.get(CLASSIFIER_VERSION, _PROMPT_V2)
    prompt = f'{system_prompt}\n\nPost: "{text}"\nScore:'

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 5,
                },
            },
            timeout=5,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()

        # Parse score: extract first digit 1-5
        score = 0
        for ch in answer:
            if ch.isdigit() and 1 <= int(ch) <= 5:
                score = int(ch)
                break

        if score == 0:
            # Fallback for unexpected model output
            if answer.upper().startswith("RELEVANT"):
                score = 4
            else:
                score = 1
                logger.warning("Unparseable classifier response: %r", answer)

    except Exception:
        logger.exception("Ollama classification failed")
        score = 0
        answer = "ERROR"

    # Log the classification
    try:
        db.connect(reuse_if_open=True)
        ClassificationLog.create(
            uri=uri,
            text=text[:500],
            result=f"{CLASSIFIER_VERSION}:{answer}",
            quality_score=score,
            classified_at=datetime.datetime.utcnow(),
        )
    except Exception:
        logger.exception("Failed to log classification")

    return score
