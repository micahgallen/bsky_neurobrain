import logging
import datetime

import requests

from src.config import OLLAMA_URL, OLLAMA_MODEL
from src.database import db, ClassificationLog

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a classifier for a cognitive science feed. Classify the following \
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

Respond with ONLY "RELEVANT" or "NOT_RELEVANT". Nothing else."""


def classify_post(text: str) -> bool:
    """Classify a post using Ollama. Returns True if RELEVANT, False otherwise."""
    prompt = f'{_SYSTEM_PROMPT}\n\nPost: "{text}"\nClassification:'

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 10,
                },
            },
            timeout=5,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        is_relevant = answer.upper().startswith("RELEVANT")
    except Exception:
        logger.exception("Ollama classification failed")
        is_relevant = False
        answer = "ERROR"

    # Log the classification
    try:
        uri = ""  # URI is set by the consumer when context is available
        db.connect(reuse_if_open=True)
        ClassificationLog.create(
            uri=uri,
            text=text[:500],
            result=answer,
            classified_at=datetime.datetime.utcnow(),
        )
    except Exception:
        logger.exception("Failed to log classification")

    return is_relevant
