"""Unregister the NeuroBrain feed from Bluesky."""

from atproto import Client
from src.config import HANDLE, PASSWORD


def main():
    client = Client()
    client.login(HANDLE, PASSWORD)

    client.app.bsky.feed.generator.delete(client.me.did, "neurobrain")
    print("Feed unpublished successfully!")


if __name__ == "__main__":
    main()
