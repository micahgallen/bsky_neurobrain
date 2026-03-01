"""60-second firehose experiment: count interoception prefilter matches by tier."""

import asyncio
import json
import sys
import time

import websockets

from src.intero_prefilter import (
    _normalize_unicode,
    _TIER1_RE,
    _TIER2_DOMAIN_RES,
)

JETSTREAM_URL = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)

DURATION = 60  # seconds


async def main():
    total = 0
    english = 0
    tier1_hits = 0
    tier2_hits = 0

    start = time.monotonic()
    last_status = start

    async with websockets.connect(JETSTREAM_URL) as ws:
        print(f"Connected — sampling for {DURATION}s...\n", flush=True)
        async for raw in ws:
            elapsed = time.monotonic() - start
            if elapsed > DURATION:
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            total += 1

            if msg.get("kind") != "commit":
                continue
            commit = msg.get("commit", {})
            if commit.get("operation") != "create":
                continue
            record = commit.get("record", {})
            langs = record.get("langs") or []
            if "en" not in langs:
                continue
            text = record.get("text", "")
            if len(text) < 30:
                continue

            english += 1
            normalized = _normalize_unicode(text)

            if _TIER1_RE.search(normalized):
                tier1_hits += 1
                snippet = text[:120].replace("\n", " ")
                print(f"  T1 [{tier1_hits}] {snippet}", flush=True)
                continue

            matched_domains = []
            for domain, regex in _TIER2_DOMAIN_RES.items():
                if regex.search(normalized):
                    matched_domains.append(domain)
            if len(matched_domains) >= 2:
                tier2_hits += 1
                domains_tag = "+".join(matched_domains)
                snippet = text[:100].replace("\n", " ")
                print(f"  T2 [{tier2_hits}] ({domains_tag}) {snippet}", flush=True)

            # Print status line every 10 seconds
            now = time.monotonic()
            if now - last_status >= 10:
                last_status = now
                print(
                    f"\n--- {elapsed:.0f}s | {total:,} msgs | "
                    f"{english:,} en | T1={tier1_hits} T2={tier2_hits} ---\n",
                    flush=True,
                )

    elapsed = time.monotonic() - start
    print(f"\n{'='*60}")
    print(f"Duration: {elapsed:.1f}s")
    print(f"Total messages: {total:,} ({total/elapsed:.0f}/sec)")
    print(f"English posts (≥30 chars): {english:,} ({english/elapsed:.1f}/sec)")
    print(f"Tier 1 hits (multi-word/anchor): {tier1_hits} ({tier1_hits/elapsed:.2f}/sec)")
    print(f"Tier 2 hits (2+ domain singles): {tier2_hits} ({tier2_hits/elapsed:.2f}/sec)")
    print(f"Total matches: {tier1_hits + tier2_hits} ({(tier1_hits+tier2_hits)/elapsed:.2f}/sec)")
    print(f"\nEstimated posts/hour: {(tier1_hits + tier2_hits) / elapsed * 3600:.0f}")


if __name__ == "__main__":
    asyncio.run(main())
