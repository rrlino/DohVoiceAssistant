#!/usr/bin/env bash
# Chat interface: type questions, hear Joe speak the replies on the Lenrue.
# Run on the Pi. Requires hailo-ollama on port 8000 and Lenrue connected.
# Usage: ~/pi_chat_with_joe.sh   (then type at "You:" prompt; Ctrl+C to quit)

set -e
SINK=$(pactl list short sinks 2>/dev/null | grep -i bluez | head -1 | cut -f2)
[ -n "$SINK" ] && pactl set-default-sink "$SINK" 2>/dev/null || true

export PIPER_VOICE=en_US-joe-medium
echo "Chat with Joe — type your question, hear the reply on the speaker. Ctrl+C to quit."
echo ""
exec python3 ~/voice_assistant_pi.py --tts piper --loop "$@"
