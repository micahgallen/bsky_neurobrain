"""Register or update the NeuroBrain Top feed on Bluesky.

Idempotent — uses put_record so re-running refreshes the display name and
description without changing the rkey (which would break subscriptions).
"""

from atproto import Client, models
from src.config import HANDLE, PASSWORD, SERVICE_DID

RKEY = "neurobrain"


def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    record = models.AppBskyFeedGenerator.Record(
        did=SERVICE_DID,
        display_name="NeuroBrain Top",
        description=(
            "The best neuroscience and cognitive science on Bluesky, filtered "
            "and ranked by AI. Quality-sorted digest of the past week — papers, "
            "expert discussion, methods debates. No politics, no pop-sci.\n\n"
            "For fresh trending content, see NeuroBrain Rising."
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
