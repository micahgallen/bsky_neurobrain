"""Register the NeuroBrain v2 test feed with Bluesky."""

from atproto import Client, models
from src.config import HANDLE, PASSWORD, SERVICE_DID


def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    record = models.AppBskyFeedGenerator.Record(
        did=SERVICE_DID,
        display_name="NeuroBrain v2",
        description=(
            "Experimental neuroscience feed with fresher ranking. "
            "Same content as NeuroBrain, tuned for faster content turnover."
        ),
        created_at=client.get_current_time_iso(),
    )

    client.app.bsky.feed.generator.create(client.me.did, record, rkey="neurobrain-v2")
    print("Feed published successfully!")
    print(f"Feed URI: at://{client.me.did}/app.bsky.feed.generator/neurobrain-v2")
    print("Set NEUROBRAIN_V2_FEED_URI in .env to this URI")


if __name__ == "__main__":
    main()
