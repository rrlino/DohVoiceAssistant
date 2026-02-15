#!/usr/bin/env bash
# Run hailo-apps Voice Assistant on the Pi.
# Uses hailo-ollama on port 8000 (Hailo-10H) for LLM; Hailo Whisper for STT; Piper for TTS.
#
# On Pi: copy this script to home, then run from anywhere:
#   ~/run_hailo_voice_assistant.sh
# Or: bash ~/run_hailo_voice_assistant.sh
#
# Prereqs: hailo-apps installed at ~/hailo-apps, hailo-ollama running on port 8000.
# Optional: OLLAMA_HOST=http://127.0.0.1:8000 (default); OLLAMA_MODEL=qwen2:1.5b if supported.

export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:8000}"
cd ~/hailo-apps && source setup_env.sh
exec python -m hailo_apps.python.gen_ai_apps.voice_assistant.voice_assistant "$@"
