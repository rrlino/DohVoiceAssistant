#!/usr/bin/env bash
# Play the Joe voice test for Ricardo (exact script).
# Run on the Pi. Copy pi_joe_test_ricardo.txt to ~/pi_joe_test_ricardo.txt if needed.
# Usage: ~/pi_run_joe_ricardo_test.sh

TXT="${1:-$HOME/pi_joe_test_ricardo.txt}"
if [ ! -f "$TXT" ]; then
  echo "Usage: $0 [path_to_ricardo.txt]"
  echo "Copy pi_joe_test_ricardo.txt to Pi: scp scripts/pi_joe_test_ricardo.txt <username>@pi5.local:~/"
  exit 1
fi

# Use Lenrue if available
SINK=$(pactl list short sinks 2>/dev/null | grep -i bluez | head -1 | cut -f2)
[ -n "$SINK" ] && pactl set-default-sink "$SINK" 2>/dev/null || true

echo "Playing with Joe's voice (en_US-joe-medium)..."
export PIPER_VOICE=en_US-joe-medium
python3 ~/voice_assistant_pi.py --tts piper --read-file "$TXT"
echo "Done."
