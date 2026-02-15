#!/usr/bin/env bash
# Connect Lenrue (A12) if needed, set as default sink, then play the Frost poem via TTS.
# Run on the Pi. Turn the Lenrue speaker ON first (and in range).
# Usage: ~/pi_play_poem_lenrue.sh   or: bash ~/pi_play_poem_lenrue.sh

SPEAKER_MAC="0B:B1:E3:49:9B:D9"
POEM_FILE="/tmp/poem.txt"

# Ensure poem exists
if [ ! -f "$POEM_FILE" ]; then
  cat > "$POEM_FILE" << 'POEM'
Whose woods these are I think I know.
His house is in the village though;
He will not see me stopping here
To watch his woods fill up with snow.
— Robert Frost
POEM
fi

echo "Connecting to Lenrue (A12)..."
bluetoothctl power on 2>/dev/null
bluetoothctl connect "$SPEAKER_MAC" 2>/dev/null || true
sleep 4

SINK=$(pactl list short sinks 2>/dev/null | grep -i bluez | head -1 | cut -f2)
if [ -n "$SINK" ]; then
  pactl set-default-sink "$SINK"
  echo "Default sink set to: $SINK"
  echo "Playing poem..."
  python3 ~/voice_assistant_pi.py --tts piper --read-file "$POEM_FILE"
else
  echo "Lenrue sink not found. Is the speaker ON and in range? List: pactl list short sinks"
  exit 1
fi
