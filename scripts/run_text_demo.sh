#!/bin/bash
# Interactive text-in / voice-out demo with the same resilience knobs
# as the systemd service. Use this for friend demos / single-turn use.
# Pinning to cores 0-2 + nice=5 keeps the kernel responsive so SSH
# and the Ethernet link don't drop while TTS is rendering.

set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# Cap thread counts (matches doh-voice-assistant.service)
export SHERPA_TTS_THREADS="${SHERPA_TTS_THREADS:-2}"
export STT_THREADS="${STT_THREADS:-2}"
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:8000}"
export SHERPA_TTS_MODEL="${SHERPA_TTS_MODEL:-$HOME/tts-models/vits-piper-en_US-joe-medium}"

# Make sure ReSpeaker is at audible volume + unmuted (idempotent)
pactl set-sink-volume @DEFAULT_SINK@ 90% 2>/dev/null || true
pactl set-sink-mute   @DEFAULT_SINK@ 0    2>/dev/null || true

# Pin to cores 0-2 (keep core 3 for kernel) + nice=5 (lower than network IRQs)
exec nice -n 5 taskset -c 0-2 \
    "$REPO/.venv/bin/python3" "$REPO/src/voice_assistant_pi.py" \
        --tts sherpa --loop "$@"
