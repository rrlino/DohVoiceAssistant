#!/usr/bin/env bash
# Loop through each Piper voice: introduce by name and say a random fun fact.
# Run on the Pi. Requires Lenrue (or default sink) for playback.
# Usage: ~/pi_voice_showcase_loop.sh   (Ctrl+C to stop)

set -e
PIPER_MODELS="${PIPER_MODEL_DIR:-$HOME/piper_models}"
VOICE_SCRIPT="$HOME/voice_assistant_pi.py"

# voice_id|Friendly name|Message (intro + fun fact)
VOICES=(
  "en_US-amy-low|Amy|This is Amy. Fun fact: Amy holds the record in our lab for the most poetry readings in a single afternoon."
  "en_US-ryan-low|Ryan|This is Ryan. Fun fact: Ryan is the most downloaded male Piper voice. He's basically famous."
  "en_US-danny-low|Danny|This is Danny. Fun fact: Danny's voice has been used to test talking appliances. Yes, really."
  "en_US-joe-medium|Joe|This is Joe. Fun fact: Joe is the voice you hear in your head when someone says average American guy."
  "en_US-john-medium|John|This is John. Fun fact: John shares his name with over a million people in the US. He's used to it."
  "en_US-bryce-medium|Bryce|This is Bryce. Fun fact: Bryce once said hello in fourteen different ways for a linguistics study."
  "en_US-norman-medium|Norman|This is Norman. Fun fact: Norman sounds like the neighbor who knows how to fix your Wi-Fi."
  "en_US-sam-medium|Sam|This is Sam. Fun fact: Sam could be short for Samuel or Samantha. We're not telling."
  "en_US-kathleen-low|Kathleen|This is Kathleen. Fun fact: Kathleen can pronounce Worcestershire correctly on the first try. Most humans cannot."
  "en_US-kristin-medium|Kristin|This is Kristin. Fun fact: Kristin's accent is so clear she's often used for language learning apps."
  "en_US-amy-medium|Amy medium|This is Amy, medium quality. Fun fact: Medium Amy uses a bigger model than low. She's got more range."
  "en_US-hfc_female-medium|HFC Female|This is HFC Female. Fun fact: This voice comes from the HFC corpus—great for clear, neutral narration."
  "en_US-hfc_male-medium|HFC Male|This is HFC Male. Fun fact: HFC Male has narrated over 100 hours of test text. He never gets tired."
  "en_US-arctic-medium|Arctic|This is Arctic. Fun fact: Arctic is named after the Arctic speech corpus—no snow required."
  "en_US-lessac-low|Lessac|This is Lessac. Fun fact: Lessac is named after the Lessac speech method. Very precise articulation."
  "en_US-ljspeech-medium|LJ Speech|This is LJ Speech. Fun fact: LJ Speech comes from LibriVox—thousands of public domain audiobooks."
  "en_US-kusal-medium|Kusal|This is Kusal. Fun fact: Kusal is from the Kusal dataset—multilingual and versatile."
  "en_US-reza_ibrahim-medium|Reza Ibrahim|This is Reza Ibrahim. Fun fact: Reza brings a distinct, expressive character to the lineup."
  "en_US-l2arctic-medium|L2 Arctic|This is L2 Arctic. Fun fact: L2 Arctic comes from non-native English speakers—great for accent diversity."
)

# Ensure Lenrue is default sink if available
SINK=$(pactl list short sinks 2>/dev/null | grep -i bluez | head -1 | cut -f2)
[ -n "$SINK" ] && pactl set-default-sink "$SINK" 2>/dev/null || true

echo "Voice showcase: ${#VOICES[@]} voices. Loop until Ctrl+C."
echo ""

while true; do
  for entry in "${VOICES[@]}"; do
    IFS='|' read -r voice_id _ message <<< "$entry"
    [ ! -f "$PIPER_MODELS/${voice_id}.onnx" ] && continue
    echo "[$voice_id] $message"
    export PIPER_VOICE="$voice_id"
    python3 "$VOICE_SCRIPT" --tts piper --once "$message" 2>/dev/null || true
    sleep 1
  done
  echo "--- end of round ---"
  sleep 2
done
