"""Register the Interoception feed with Bluesky."""

from atproto import Client, models
from src.config import HANDLE, PASSWORD, HOSTNAME, SERVICE_DID


def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    feed_did = SERVICE_DID
    record = models.AppBskyFeedGenerator.Record(
        did=feed_did,
        display_name="Interoception",
        description="Posts about bodily sensations and interoceptive experience.",
        created_at=client.get_current_time_iso(),
    )

    client.app.bsky.feed.generator.create(client.me.did, record, rkey="intero")
    print("Feed published successfully!")
    print(f"Feed URI: at://{client.me.did}/app.bsky.feed.generator/intero")
    print("Set INTERO_FEED_URI in .env to the URI above.")


if __name__ == "__main__":
    main()
