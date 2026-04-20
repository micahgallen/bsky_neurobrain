#!/usr/bin/env bash
# Restart all NeuroBrain services after code changes.
#
# - neurobrain-server     — serves the feed (loads src/algos/*)
# - neurobrain-consumer   — Jetstream ingest (loads src/consumer.py, classifier.py, prefilter.py)
# - neurobrain-engagement — engagement + scoring updater (loads src/engagement.py)
#
# The Cloudflare tunnel (neurobrain-tunnel) doesn't need a restart for code changes.

set -euo pipefail

SERVICES=(neurobrain-server neurobrain-consumer neurobrain-engagement)

echo "Restarting: ${SERVICES[*]}"
sudo systemctl restart "${SERVICES[@]}"

echo
echo "Status:"
systemctl is-active "${SERVICES[@]}" | paste <(printf '%s\n' "${SERVICES[@]}") -
