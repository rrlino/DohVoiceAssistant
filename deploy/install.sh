#!/bin/bash
# Deploy systemd services to Pi 5
# Usage: ./deploy/install.sh [pi-host]
# Defaults to rrlino@192.168.68.104

PI_HOST="${1:-rrlino@192.168.68.104}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

set -e

echo "Deploying to $PI_HOST ..."

# Copy service files
echo "Copying service files ..."
scp "$SCRIPT_DIR/hailo-ollama.service" "$PI_HOST:/tmp/hailo-ollama.service"
scp "$SCRIPT_DIR/doh-voice-assistant.service" "$PI_HOST:/tmp/doh-voice-assistant.service"

# Install and enable on Pi
echo "Installing services ..."
ssh "$PI_HOST" bash -s <<'REMOTE'
set -e

# Install service files (requires sudo)
sudo cp /tmp/hailo-ollama.service /etc/systemd/system/
sudo cp /tmp/doh-voice-assistant.service /etc/systemd/system/
rm -f /tmp/hailo-ollama.service /tmp/doh-voice-assistant.service

# Reload systemd
sudo systemctl daemon-reload

# Enable both services (start on boot)
sudo systemctl enable hailo-ollama.service
sudo systemctl enable doh-voice-assistant.service

# Start hailo-ollama now
sudo systemctl start hailo-ollama.service

echo ""
echo "Services installed and enabled."
echo ""
echo "Commands:"
echo "  sudo systemctl status hailo-ollama    # Check LLM server"
echo "  sudo systemctl status doh-voice       # Check voice assistant"
echo "  sudo systemctl start doh-voice        # Start voice assistant"
echo "  sudo systemctl stop doh-voice         # Stop voice assistant"
echo "  journalctl -u hailo-ollama -f         # Tail LLM logs"
echo "  journalctl -u doh-voice -f            # Tail voice logs"
REMOTE

echo ""
echo "Done."
