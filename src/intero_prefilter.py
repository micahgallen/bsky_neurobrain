"""Two-tier prefilter for interoception (bodily sensation) posts.

Loads the interoception dictionary (1,615 terms across 10 body-sensation domains)
and applies a two-tier matching strategy:

  Tier 1 — Single match passes:
    Scientific anchor terms (e.g., "interoception", "heartbeat perception")
    + multi-word dictionary entries (e.g., "chest pressure", "heart racing")
    + dictionary phrases (e.g., "butterflies in stomach")

  Tier 2 — Need 2+ matches from different domains:
    Single-word dictionary terms (e.g., "nauseous", "shaky", "sleepy")
    + stem patterns (e.g., nause* → "nauseous", dizz* → "dizzy")
    are too common alone, but cross-domain co-occurrence signals relevance.
"""

import json
import re
import unicodedata
from pathlib import Path

_DICT_PATH = Path(__file__).parent.parent / "data" / "interoception_dictionary.json"

with open(_DICT_PATH) as f:
    _DICT = json.load(f)

# NSFW exclusion — reject before any matching
_NSFW_TERMS = [
    r"porn\w*", r"hentai", r"xxx", r"nsfw",
    r"orgasm\w*", r"masturbat\w*", r"erection\w*",
    r"cum\b", r"cumming", r"blowjob\w*", r"handjob\w*",
    r"dildo\w*", r"vibrator\w*", r"anal\b", r"bdsm",
    r"kink\w*", r"fetish\w*", r"dominatrix",
    r"nude\w*", r"naked", r"genitals?",
    r"penis", r"vagina\w*", r"clitor\w*",
    r"cock\b", r"dick\b", r"pussy\b", r"tits?\b", r"boobs?\b",
    r"fuck\w*", r"sex\b", r"sexual\w*", r"sexy",
    r"onlyfans", r"camgirl\w*", r"escort\w*",
    r"hookup\w*", r"hook up", r"smut",
    r"threesome", r"gangbang", r"orgy",
]
_NSFW_RE = re.compile(r"\b(?:" + "|".join(_NSFW_TERMS) + r")\b", re.IGNORECASE)

# Scientific anchor terms — always tier 1
_ANCHORS = [
    # Interoception and all forms
    r"interoception", r"interoceptiv\w*", r"interoceptor\w*",
    r"intero\w+",  # catches any intero-prefixed term
    # Synonyms / closely related scientific terms
    r"heartbeat perception", r"heartbeat detection", r"heartbeat counting",
    r"body awareness", r"bodily sensation\w*", r"body signal\w*",
    r"somatic", r"visceral sensation\w*", r"visceral awareness",
    r"afferent", r"autonomic nervous", r"vagal tone", r"vagus nerve",
    r"proprioception", r"proprioceptiv\w*",
    r"nociception", r"nociceptiv\w*",
    r"somatosensory", r"somatosensation",
    r"body perception", r"body schema",
    r"internal sensation\w*", r"internal body",
    r"gut feeling\w*", r"gut.brain",
    r"heartbeat awareness", r"cardiac awareness",
]

# Build tier 1 regex: anchors + multi-word terms + phrases + stems
_tier1_parts = list(_ANCHORS)

# Build tier 2: single-word terms mapped to domain for cross-domain matching
_tier2_by_domain: dict[str, list[str]] = {}

for _domain, _data in _DICT["domains"].items():
    for _entry in _data.get("terms", []):
        term = _entry["entry"]
        if " " in term:
            _tier1_parts.append(re.escape(term))
        else:
            _tier2_by_domain.setdefault(_domain, []).append(re.escape(term))

    for _entry in _data.get("phrases", []):
        _tier1_parts.append(re.escape(_entry["entry"]))

    for _entry in _data.get("stems", []):
        stem = _entry["entry"].rstrip("*")
        _tier2_by_domain.setdefault(_domain, []).append(re.escape(stem) + r"\w*")

_TIER1_RE = re.compile(r"\b(?:" + "|".join(_tier1_parts) + r")\b", re.IGNORECASE)

_TIER2_DOMAIN_RES: dict[str, re.Pattern] = {}
for _domain, _patterns in _tier2_by_domain.items():
    _TIER2_DOMAIN_RES[_domain] = re.compile(
        r"\b(?:" + "|".join(_patterns) + r")\b", re.IGNORECASE
    )

# Clean up module-level build variables
del _domain, _data, _entry, _patterns


def _normalize_unicode(text: str) -> str:
    """Normalize fancy Unicode (bold/italic/script) to ASCII for matching."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def passes_intero_prefilter(text: str) -> bool:
    """Return True if the text likely relates to bodily sensations / interoception.

    Tier 1: any single match from scientific anchors, multi-word terms, phrases, stems.
    Tier 2: matches from 2+ different body-sensation domains (single-word terms).
    """
    text = _normalize_unicode(text)

    if _NSFW_RE.search(text):
        return False

    if _TIER1_RE.search(text):
        return True

    matched_domains = 0
    for regex in _TIER2_DOMAIN_RES.values():
        if regex.search(text):
            matched_domains += 1
            if matched_domains >= 2:
                return True

    return False
