# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Privacy-first offline voice assistant running on Raspberry Pi 5 + Hailo-10H AI HAT+. No cloud dependency - STT, LLM, and TTS all run locally.

## Architecture

```
User Voice → [Whisper STT on Hailo-10H] → [Qwen LLM on Hailo-10H] → [Piper TTS on Pi CPU] → Speaker
```

| Component | Technology | Hardware | Why |
|-----------|------------|----------|-----|
| STT | Hailo Whisper | Hailo-10H | Accelerated inference |
| LLM | hailo-ollama (Qwen 2:1.5B) | Hailo-10H | Accelerated inference |
| TTS | Piper | Pi 5 CPU | Hailo can't do 1D convolutions needed for audio synthesis |

The Hailo architecture doesn't support 1D convolutions required for audio synthesis, so TTS must run on the Pi CPU.

## Commands

### Start the LLM server (on Pi)
```bash
nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &
```

### Run the voice assistant
```bash
# Full voice assistant (requires mic)
./scripts/run_hailo_voice_assistant.sh

# Text chat with spoken replies (works now)
python3 src/voice_assistant_pi.py --tts piper --loop

# Single query
python3 src/voice_assistant_pi.py --once "What time is it?"

# Read text aloud (no LLM)
echo "Hello world" | python3 src/voice_assistant_pi.py --read
```

### Test LLM connectivity
```bash
# From development machine
python3 src/test_pi_qwen.py --prompt "Hello"

# List available models
python3 src/test_pi_qwen.py --list
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://127.0.0.1:8000` | hailo-ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2:1.5b` | Model name |
| `TTS_ENGINE` | `pyttsx3` | `pyttsx3` (robotic) or `piper` (natural) |
| `PIPER_VOICE` | `en_US-amy-medium` | Piper voice name |
| `PIPER_BIN` | `~/piper/piper` | Piper binary path |
| `PIPER_MODEL_DIR` | `~/piper_models` | Voice models directory |

## Key Files

- `src/voice_assistant_pi.py` - Main voice assistant (text → LLM → TTS). Streams LLM response and speaks sentence-by-sentence for lower perceived latency.
- `src/test_pi_qwen.py` - Test harness for hailo-ollama API from remote machine.
- `scripts/run_hailo_voice_assistant.sh` - Wrapper for hailo-apps Voice Assistant (full STT → LLM → TTS pipeline).
- `docs/TTS_SOLUTION_PI5.md` - Sherpa-ONNX integration planned for RTF < 0.1 (Piper currently achieves RTF 0.5-1.0).
- `examples/voice_config.example.json` - Configuration template.

## Current State

- **Working:** Text input → LLM response → Voice output
- **Pending:** Microphone input (ReSpeaker Lite hardware)

## Dependencies

Python dependencies (install on Pi):
```
requests
pyttsx3
```

System dependencies (on Pi):
- `hailort` - Hailo runtime
- `hailo-ollama` - LLM server
- `hailo-apps` - Voice assistant framework
- Piper binary + voice models at `~/piper/` and `~/piper_models/`
- PulseAudio + `pulseaudio-module-bluetooth` for Bluetooth speakers

## Hardware Notes

See `hardware/HARDWARE_SETUP.md` for assembly and `docs/HAILO_PI_SETUP.md` for software installation.

Target hardware: Raspberry Pi 5 16GB + Hailo AI HAT+ (Hailo-10H) + ReSpeaker Lite or Bluetooth speaker.
