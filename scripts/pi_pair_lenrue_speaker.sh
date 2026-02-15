#!/usr/bin/env bash
# Pair Lenrue Bluetooth speaker (shows as "A12") with Pi 5 and set as default audio output.
# Run on the Pi when the speaker is in pairing mode.
# Usage: ./pi_pair_lenrue_speaker.sh   (or: bash pi_pair_lenrue_speaker.sh)

set -e

SPEAKER_MAC="0B:B1:E3:49:9B:D9"
SPEAKER_NAME="A12"

echo "=== Lenrue speaker (A12) - Pi 5 ==="
echo "MAC: $SPEAKER_MAC"
echo "Put the speaker in PAIRING MODE (hold BT button until it blinks), then press Enter."
read -r

bluetoothctl power on
bluetoothctl pairable on

echo "Scanning for 12 seconds..."
timeout 12 hcitool scan 2>/dev/null || true
echo ""

echo "Pairing $SPEAKER_MAC ($SPEAKER_NAME)..."
bluetoothctl pair "$SPEAKER_MAC" || true
sleep 2
echo "Connecting..."
bluetoothctl connect "$SPEAKER_MAC" || true
bluetoothctl trust "$SPEAKER_MAC" || true
sleep 2

echo ""
echo "Checking connection..."
bluetoothctl info "$SPEAKER_MAC" 2>/dev/null | head -15

echo ""
echo "Setting as default audio sink (PulseAudio)..."
if command -v pactl &>/dev/null; then
  SINK=$(pactl list short sinks | grep -i bluez | head -1 | cut -f2)
  if [ -n "$SINK" ]; then
    pactl set-default-sink "$SINK"
    echo "Default sink set to: $SINK"
  else
    echo "No BlueZ sink found. List sinks: pactl list short sinks"
  fi
else
  echo "pactl not found; set default output in system sound settings."
fi

echo ""
echo "Done. Test TTS or play a sound: speaker-test -t wav -c 2 -l 1"
