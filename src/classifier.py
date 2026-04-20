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

# v2: Expert science conversation — interesting and apolitical
_PROMPT_V2 = """\
You are a classifier for a neuroscience and cognitive science feed. Is this \
post an interesting, expert-level discussion about neuroscience or cognitive science?

RELEVANT fields:
- Neuroscience (brain research, neural mechanisms, neuroimaging, neurotransmitters)
- Cognitive science (cognition, perception, memory, attention, learning, decision-making)
- Psychology (experimental, cognitive, developmental, behavioral)
- Philosophy of mind (consciousness, qualia, mental representation)
- Linguistics (psycholinguistics, language processing, syntax, semantics)
- Cognitive anthropology (cultural cognition, cognitive ecology)

Score 1-5:
5 - Shares or discusses specific research, papers, data, or findings in these fields
4 - Expert discussion: debates theories, critiques methods, or shares domain insights
3 - Informed content with genuine substance about the brain or cognition
2 - Casual or superficial mention without depth
1 - Not relevant: general health/medicine, biology, chemistry, physics, or non-science

ALWAYS score 1 for:
- General health science, epidemiology, oncology, cardiology, immunology, genetics
- Clinical medicine, medical advice, therapy recommendations
- Political content, even if it mentions science
- AI/ML unless explicitly about biological cognition or brain-inspired models
- Personal anecdotes, self-help, pop psychology without scientific substance

Respond with ONLY a single digit: 1, 2, 3, 4, or 5."""

_PROMPTS = {
    "v1": _PROMPT_V1,
    "v2": _PROMPT_V2,
}


def classify_post(text: str, uri: str = "") -> int:
    """Classify a post using Ollama. Returns quality score 1-5 (0 on error)."""
    system_prompt = _PROMPTS.get(CLASSIFIER_VERSION, _PROMPT_V2)

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f'Post: "{text}"\nScore:'},
                ],
                "stream": False,
                "think": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 20,
                    "num_predict": 5,
                },
            },
            timeout=45,
        )
        resp.raise_for_status()
        answer = resp.json().get("message", {}).get("content", "").strip()

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


