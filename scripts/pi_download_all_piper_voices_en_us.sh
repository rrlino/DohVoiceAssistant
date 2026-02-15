#!/usr/bin/env bash
# Download all en_US Piper TTS voices (one quality per speaker) to ~/piper_models on the Pi.
# Run on the Pi. Requires: pip install piper-tts (or piper from rhasspy).
# Usage: ~/pi_download_all_piper_voices_en_us.sh
# Then use with: PIPER_VOICE=en_US-ryan-low python3 ~/voice_assistant_pi.py --tts piper --once "Hello"

set -e
PIPER_MODELS="${PIPER_MODEL_DIR:-$HOME/piper_models}"
mkdir -p "$PIPER_MODELS"
cd "$PIPER_MODELS"

# One voice per speaker (low when available to save space; else medium).
# Full list: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US
VOICES=(
  en_US-amy-low
  en_US-amy-medium
  en_US-arctic-medium
  en_US-bryce-medium
  en_US-danny-low
  en_US-hfc_female-medium
  en_US-hfc_male-medium
  en_US-joe-medium
  en_US-john-medium
  en_US-kathleen-low
  en_US-kristin-medium
  en_US-kusal-medium
  en_US-l2arctic-medium
  en_US-lessac-low
  en_US-ljspeech-medium
  en_US-norman-medium
  en_US-reza_ibrahim-medium
  en_US-ryan-low
  en_US-sam-medium
)

echo "Downloading ${#VOICES[@]} en_US Piper voices to $PIPER_MODELS"
for v in "${VOICES[@]}"; do
  if [ -f "${v}.onnx" ]; then
    echo "Skip (exists): $v"
  else
    echo "Downloading: $v"
    python3 -m piper.download_voices "$v" || true
  fi
done
echo "Done. List: ls $PIPER_MODELS/*.onnx"
echo "Try: PIPER_VOICE=en_US-ryan-low ~/pi_play_poem_lenrue.sh"
