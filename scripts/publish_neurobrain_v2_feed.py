"""Register or update the NeuroBrain Rising feed on Bluesky.

Idempotent — uses put_record so re-running refreshes the display name and
description without changing the rkey (which would break subscriptions).
"""

from atproto import Client, models
from src.config import HANDLE, PASSWORD, SERVICE_DID

RKEY = "neurobrain-v2"


def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    record = models.AppBskyFeedGenerator.Record(
        did=SERVICE_DID,
        display_name="NeuroBrain Rising",
        description=(
            "Trending neuroscience and cognitive science on Bluesky — "
            "what's catching fire right now. Engagement-driven ranking with "
            "a 3-day window and 6-hour engagement half-life. Refresh-worthy.\n\n"
            "For the weekly quality digest, see NeuroBrain Top."
        ),
        created_at=client.get_current_time_iso(),
    )

    client.com.atproto.repo.put_record({
        "repo": client.me.did,
        "collection": "app.bsky.feed.generator",
        "rkey": RKEY,
        "record": record,
    })
    print("Feed published/updated successfully!")
    print(f"Feed URI: at://{client.me.did}/app.bsky.feed.generator/{RKEY}")


if __name__ == "__main__":
    main()
