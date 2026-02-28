import logging

from atproto import Client

logger = logging.getLogger(__name__)


def load_follows(handle: str, password: str) -> set[str]:
    """Fetch all DIDs the user follows. Returns a set for O(1) lookup."""
    client = Client()
    client.login(handle, password)

    follows = set()
    cursor = None
    while True:
        resp = client.get_follows(client.me.did, cursor=cursor, limit=100)
        for f in resp.follows:
            follows.add(f.did)
        if not resp.cursor:
            break
        cursor = resp.cursor

    logger.info("Loaded %d follows", len(follows))
    return follows
