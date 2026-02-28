#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/micah/vibes/bsky_neurobrain"
SERVICES=(neurobrain-consumer neurobrain-server neurobrain-engagement neurobrain-tunnel)

echo "=== NeuroBrain Deploy ==="

# 1. Stop running services
echo "Stopping services..."
for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        sudo systemctl stop "$svc"
        echo "  stopped $svc"
    else
        echo "  $svc not running"
    fi
done

# 2. Install/update service files
echo "Installing service files..."
for f in "$PROJECT_DIR"/deploy/*.service; do
    sudo cp "$f" /etc/systemd/system/
    echo "  copied $(basename "$f")"
done
sudo systemctl daemon-reload

# 3. Enable all services
echo "Enabling services..."
for svc in "${SERVICES[@]}"; do
    sudo systemctl enable "$svc" --quiet
done

# 4. Run database migration
echo "Running database migration..."
cd "$PROJECT_DIR"
venv/bin/python -c "from src.database import init_db; init_db(); print('  migration OK')"

# 5. Start services
echo "Starting services..."
for svc in "${SERVICES[@]}"; do
    sudo systemctl start "$svc"
    echo "  started $svc"
done

# 6. Verify
echo ""
echo "=== Service Status ==="
for svc in "${SERVICES[@]}"; do
    status=$(systemctl is-active "$svc" 2>/dev/null || true)
    echo "  $svc: $status"
done

echo ""
echo "Deploy complete. Watch logs with:"
echo "  journalctl -u neurobrain-consumer -u neurobrain-engagement -f"
