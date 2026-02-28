"""Analyze political post frequency among followed accounts and optionally unfollow."""

import time
import sys

from atproto import Client
from peewee import fn

from src.config import HANDLE, PASSWORD
from src.database import init_db, PoliticsLog


def get_rankings(min_count=2):
    """Return accounts ranked by political post count."""
    return (
        PoliticsLog
        .select(PoliticsLog.did, fn.COUNT(PoliticsLog.id).alias("count"))
        .group_by(PoliticsLog.did)
        .having(fn.COUNT(PoliticsLog.id) >= min_count)
        .order_by(fn.COUNT(PoliticsLog.id).desc())
    )


def resolve_handle(client, did):
    """Resolve a DID to a handle."""
    try:
        profile = client.get_profile(did)
        return profile.display_name or profile.handle, profile.handle
    except Exception:
        return did, did


def main():
    init_db()

    min_count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rankings = list(get_rankings(min_count))

    if not rankings:
        print(f"No accounts with {min_count}+ political posts detected yet.")
        print("Let the consumer run for a while to collect data.")
        return

    client = Client()
    client.login(HANDLE, PASSWORD)

    print(f"Accounts with {min_count}+ political posts detected:\n")
    print(f"  {'#':<4} {'Count':<7} {'Handle':<30} {'Name'}")
    print(f"  {'-'*4} {'-'*7} {'-'*30} {'-'*20}")

    accounts = []
    for i, row in enumerate(rankings, 1):
        name, handle = resolve_handle(client, row.did)
        accounts.append((row.did, handle, name, row.count))
        print(f"  {i:<4} {row.count:<7} @{handle:<29} {name}")

    total = PoliticsLog.select().count()
    print(f"\n  Total political posts logged: {total}")
    print(f"  Accounts above threshold: {len(accounts)}")

    # Ask about unfollowing
    print(f"\nUnfollow all {len(accounts)} accounts listed above?")
    answer = input("Type YES to proceed, anything else to cancel: ").strip()
    if answer != "YES":
        print("Cancelled.")
        return

    # Unfollow with rate limiting — 1 per 3 seconds to be safe
    # Bluesky allows ~5000 writes/hr but no reason to rush
    print()
    for i, (did, handle, name, count) in enumerate(accounts, 1):
        try:
            # Find the follow record to delete
            follows_resp = client.get_follows(client.me.did, limit=1)
            # Use the API to unfollow by DID
            profile = client.get_profile(did)
            if profile.viewer and profile.viewer.following:
                rkey = profile.viewer.following.split("/")[-1]
                client.delete_follow(rkey)
                print(f"  [{i}/{len(accounts)}] Unfollowed @{handle} ({count} political posts)")
            else:
                print(f"  [{i}/{len(accounts)}] Already not following @{handle}")
            time.sleep(3)
        except Exception as e:
            print(f"  [{i}/{len(accounts)}] Failed to unfollow @{handle}: {e}")
            time.sleep(5)

    print("\nDone!")


if __name__ == "__main__":
    main()
