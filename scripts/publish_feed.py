"""Register the NeuroBrain feed with Bluesky."""

from atproto import Client, models
from src.config import HANDLE, PASSWORD, HOSTNAME, SERVICE_DID


def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    feed_did = SERVICE_DID
    record = models.AppBskyFeedGenerator.Record(
        did=feed_did,
        display_name="NeuroBrain",
        description=(
            "Neuroscience and cognitive science, filtered and ranked by AI. "
            "Papers, expert discussion, methods debates. No politics, no pop-sci."
        ),
        created_at=client.get_current_time_iso(),
    )

    client.app.bsky.feed.generator.create(client.me.did, record, rkey="neurobrain")
    print("Feed published successfully!")
    print(f"Feed URI: at://{client.me.did}/app.bsky.feed.generator/neurobrain")


if __name__ == "__main__":
    main()
