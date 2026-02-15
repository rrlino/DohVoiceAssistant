# DohVoiceAssistant

> A privacy-first, offline voice assistant running entirely on Raspberry Pi 5 + Hailo-10H

**No cloud. No subscription. Your voice never leaves your home.**

Started as a fun experiment ("I want Darth Vader to tell me my schedule"). Became a mission when I realized this technology could actually help people—like the father building accessible home automation for his visually impaired daughter.

---

## What It Does

| Component | Technology | Runs On |
|-----------|------------|---------|
| **Speech-to-Text** | Hailo Whisper | Hailo-10H accelerator |
| **LLM** | hailo-ollama (Qwen 2:1.5B) | Hailo-10H accelerator |
| **Text-to-Speech** | Piper (19+ voices) | Pi 5 CPU |

**Current State:** Text in → LLM reply → Voice out works
**In Progress:** Microphone input (ReSpeaker Lite on order)

---

## Hardware Requirements

| Component | Approx. Cost | Notes |
|-----------|--------------|-------|
| Raspberry Pi 5 (16GB) | ~£120 | 8GB may work, 16GB recommended |
| Hailo AI HAT+ (Hailo-10H) | ~£140 | AI accelerator for STT/LLM |
| ReSpeaker Lite | ~£36 | USB mic + speaker |
| **Total** | **~£300** | One-time cost, no subscription |

---

## Quick Start

### 1. Prerequisites

- Raspberry Pi 5 with Hailo AI HAT+ installed
- Hailo software stack (`hailort`, `hailo-ollama`)
- Python 3.10+

### 2. Install hailo-apps

```bash
git clone https://github.com/hailo-ai/hailo-apps.git
cd hailo-apps
sudo ./install.sh
source setup_env.sh
```

### 3. Install Piper TTS

```bash
cd ~/hailo-apps/local_resources/piper_models
python3 -m piper.download_voices en_US-joe-medium
```

### 4. Run the Voice Assistant

```bash
# Start hailo-ollama (LLM server)
nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &

# Run voice assistant
./scripts/run_hailo_voice_assistant.sh
```

---

## Project Structure

```
DohVoiceAssistant/
├── docs/                    # Detailed documentation
│   ├── VOICE_ASSISTANT_PLAN.md
│   ├── TTS_SOLUTION_PI5.md
│   └── HAILO_PI_SETUP.md
├── scripts/                 # Setup and utility scripts
│   ├── run_hailo_voice_assistant.sh
│   ├── pi_chat_with_joe.sh
│   └── ...
├── src/                     # Python source code
│   ├── voice_assistant_pi.py
│   └── test_pi_qwen.py
├── hardware/                # Hardware setup guides
├── examples/                # Example configurations
└── README.md
```

---

## The Challenges We're Solving

### TTS Latency

Piper gives us RTF (Real-Time Factor) of 0.5-1.0 — too slow for natural conversation.

**Solution:** Researching Sherpa-ONNX for RTF < 0.1

### Hailo Can't Do TTS

The Hailo architecture doesn't support 1D convolutions needed for audio synthesis.

- STT (Whisper): Accelerated on Hailo
- LLM: Accelerated on Hailo
- TTS: Must run on Pi CPU

### CPU Spikes

80-100% CPU usage during TTS. Streaming playback helps reduce perceived latency.

---

## Roadmap

- [x] Text → LLM → Voice output
- [ ] Microphone input (ReSpeaker Lite)
- [ ] Full voice loop (speak → listen → respond)
- [ ] RAG / personal context (feed it your MD files)
- [ ] Wake word detection
- [ ] Voice-to-action (home automation)
- [ ] Character voices (Darth Vader, Homer Simpson)

---

## Why This Matters

**Privacy:** Everything runs locally. No data leaves your home.

**Accessibility:** Voice assistants that actually work for people who need them.

**Affordability:** ~£300 one-time vs. subscription lock-in.

**Learning:** This is a learning-in-public project. Code, learnings, and mistakes—all shared.

---

## Contributing

This project is in early stages. Contributions welcome:

- Bug reports and fixes
- Documentation improvements
- TTS optimization (Sherpa-ONNX integration)
- Hardware alternatives
- Accessibility use cases

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Resources

- [Hailo Apps Repository](https://github.com/hailo-ai/hailo-apps)
- [Piper TTS Voices](https://huggingface.co/rhasspy/piper-voices)
- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) (planned TTS upgrade)

---

## Author

Building in public. Learning out loud.

Connect: [LinkedIn](https://www.linkedin.com/in/rrlino/)

---

*"Sometimes the best projects start as jokes and end up mattering."*
