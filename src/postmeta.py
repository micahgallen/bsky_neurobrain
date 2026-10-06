"""Post metadata helpers shared by the consumer and the backfill script.

- Topic blacklist (long COVID / ME-CFS / COVID cluster) applied at ingest.
- Reply detection from the record's `reply` field.
- Outbound link extraction + normalisation, used to cap near-duplicate
  link shares in the feeds.
"""

import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Topic blacklist. These communities are very active and niche, and their
# posts legitimately score 4-5 on the neuro rubric (brain PET, cognition
# studies), so the classifier cannot be asked to remove them. Matched against
# the post text, quoted-post text and hashtags, *before* the science-hashtag
# bypass so #LongCovid + #neurosky posts are still caught.
_BLACKLIST_TERMS = [
    r"long.?covid",
    r"covid\w*",
    r"sars.?cov\w*",
    r"coronavirus",
    r"me/?cfs",
    r"myalgic",
    r"chronic fatigue",
    r"pasc",
    r"post.?exertional",
    r"dysautonomia",
    r"pwme",
]
BLACKLIST_RE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(_BLACKLIST_TERMS) + r")(?![a-z0-9])", re.IGNORECASE)


def is_blacklisted(text: str, quoted_text: str = "", hashtags: list[str] | None = None) -> bool:
    """Return True if the post touches a blacklisted topic."""
    blob = " ".join([text or "", quoted_text or "", " ".join(hashtags or [])])
    return bool(BLACKLIST_RE.search(blob))


def is_reply(record: dict) -> bool:
    """True if the post record is a reply to another post."""
    return bool(record.get("reply"))


_TRACKING_PARAMS = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|ref|source|s|si|igshid)$", re.IGNORECASE)


def normalize_link(url: str) -> str | None:
    """Canonicalise a URL so the same article shared different ways collapses.

    Lowercases scheme/host, strips 'www.', tracking params, fragments and
    trailing slashes. Returns None for anything that is not http(s).
    """
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parts.path) or ""
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAMS.match(k)]
    query.sort()
    out = urlunsplit(("https", host, path, urlencode(query), ""))
    return out[:500]


def extract_link(record: dict) -> str | None:
    """Return the post's primary outbound link, normalised, or None.

    Prefers the link card (external embed, including recordWithMedia), then
    the first link facet in the text.
    """
    embed = record.get("embed") or {}
    external = embed.get("external")
    if not external and isinstance(embed.get("media"), dict):
        external = embed["media"].get("external")
    if isinstance(external, dict) and external.get("uri"):
        link = normalize_link(external["uri"])
        if link:
            return link
    for facet in record.get("facets") or []:
        for feature in facet.get("features") or []:
            if feature.get("$type") == "app.bsky.richtext.facet#link":
                link = normalize_link(feature.get("uri", ""))
                if link:
                    return link
    return None
