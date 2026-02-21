# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Privacy-first offline voice assistant running on Raspberry Pi 5 + Hailo-10H AI HAT+. No cloud dependency - STT, LLM, and TTS all run locally.

## Architecture

### Single-Thread (Basic)
```
User Voice → [faster-whisper STT on Pi CPU] → [Qwen LLM on Hailo-10H] → [Piper TTS on Pi CPU] → Speaker
```

### 2-Thread (Recommended for Natural Conversation)
```
Thread 1 (Listener):  Mic → [Silero VAD] → Audio Queue
Thread 2 (Processor): Queue → [faster-whisper] → [hailo-ollama] → [Piper TTS] → Speaker
```

| Component | Technology | Hardware | Why |
|-----------|------------|----------|-----|
| VAD | Silero (sherpa-onnx) | Pi 5 CPU | 92% accuracy, <1ms latency |
| STT | faster-whisper (tiny.en) | Pi 5 CPU | Fast transcription, works well on ARM |
| LLM | hailo-ollama (Qwen 2:1.5B) | Hailo-10H | Accelerated inference |
| TTS | Piper | Pi 5 CPU | Hailo can't do 1D convolutions needed for audio synthesis |

## Setup (One-time)

### 1. Install Python dependencies
```bash
pip3 install -r requirements.txt
```

### 2. Start the LLM server (on Pi)
```bash
nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &
```

### 3. Verify audio devices
```bash
# Check ReSpeaker Lite is recognized
arecord -l  # Should show "ReSpeaker Lite"
aplay -l    # Should show "ReSpeaker Lite"
```

## Commands

### Voice Assistant (with microphone)
```bash
# 2-thread mode (recommended): continuous listening with Silero VAD
python3 src/voice_assistant_pi.py --threaded --tts piper

# Basic voice mode - fixed 5s recording per turn
python3 src/voice_assistant_pi.py --voice

# Wake word mode - say "assistant" to activate
python3 src/voice_assistant_pi.py --voice --wake
```

### Text Input Modes
```bash
# Text chat with spoken replies
python3 src/voice_assistant_pi.py --tts piper --loop

# Single query
python3 src/voice_assistant_pi.py --once "What time is it?"

# Read text aloud (no LLM)
echo "Hello world" | python3 src/voice_assistant_pi.py --read
```

### Audio Utilities
```bash
# Record 5 seconds of audio
python3 src/voice_assistant_pi.py --record 5

# Transcribe audio file
python3 src/voice_assistant_pi.py --transcribe /tmp/recording.wav
```

### Test LLM connectivity
```bash
# From development machine
python3 src/test_pi_qwen.py --prompt "Hello"

# List available models
python3 src/test_pi_qwen.py --list
```

### Benchmark latency
```bash
# Run full benchmark (5 iterations per prompt)
python3 src/benchmark_latency.py

# More iterations for statistical significance
python3 src/benchmark_latency.py --iterations 10

# Test specific prompt types
python3 src/benchmark_latency.py --prompts short medium

# Output as JSON for logging
python3 src/benchmark_latency.py --json > benchmark_results.json
```

## Environment Variables

### LLM Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://127.0.0.1:8000` | hailo-ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2:1.5b` | Model name |

### STT Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `STT_ENGINE` | `faster-whisper` | STT engine: `faster-whisper`, `whisper.cpp`, `whisper` |
| `STT_MODEL` | `tiny.en` | Whisper model size: `tiny.en`, `base.en`, `small.en` |
| `VAD_SILENCE_MS` | `1000` | Silence duration to stop recording (ms) |

### TTS Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_ENGINE` | `piper` | `pyttsx3`, `piper`, or `supertonic` |
| `PIPER_VOICE` | `en_US-amy-medium` | Piper voice name |
| `PIPER_BIN` | `~/piper/piper` | Piper binary path |
| `PIPER_MODEL_DIR` | `~/piper_models` | Voice models directory |

### Resource Guardrails
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_MEMORY_PERCENT` | `85` | Warn when memory exceeds this % |
| `CRITICAL_MEMORY_PERCENT` | `95` | Force cleanup at this % |
| `LLM_TIMEOUT` | `30` | Timeout for LLM requests (seconds) |
| `TTS_TIMEOUT` | `30` | Timeout for TTS (seconds) |
| `WATCHDOG_TIMEOUT` | `60` | Max seconds between thread heartbeats |

## Key Files

- `src/voice_assistant_pi.py` - Main voice assistant with STT → LLM → TTS pipeline. Supports voice and text input.
- `src/benchmark_latency.py` - Latency benchmarking script. Measures LLM TTFT, TTS RTF, and full turn latency.
- `src/benchmark_tts_comparison.py` - Compare Piper vs Supertonic TTS performance.
- `src/test_pi_qwen.py` - Test harness for hailo-ollama API from remote machine.
- `requirements.txt` - Python dependencies for the voice assistant.

## Current State

- **Working:**
  - Text input → LLM response → Voice output
  - Voice input (STT) → LLM response → Voice output
  - ReSpeaker Lite microphone and speaker
  - 2-thread continuous conversation with Silero VAD (`--threaded`)
- **Pending:** Hailo-accelerated STT (Phase 2)

## Dependencies

Python dependencies (install on Pi):
```bash
pip3 install -r requirements.txt
```

System dependencies (on Pi):
- `hailort` - Hailo runtime
- `hailo-ollama` - LLM server
- Piper binary + voice models at `~/piper/` and `~/piper_models/`
- PulseAudio for audio I/O

## Hardware Notes

Target hardware: Raspberry Pi 5 16GB + Hailo AI HAT+ (Hailo-10H) + ReSpeaker Lite.

The ReSpeaker Lite must have USB firmware v2.0.7 flashed to appear as an audio device. See the project's setup notes for firmware flashing instructions.
