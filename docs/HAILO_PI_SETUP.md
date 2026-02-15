# Hailo on Pi 5 — Setup & Voice Assistant Options

**Pi access:** `ssh <username>@pi5.local` — if hostname doesn't resolve: `ssh <username>@<pi-ip-address>`  
**Target:** Raspberry Pi 5 16GB + AI HAT+2 (Hailo-10H)

---

## 1. Current Pi Status (verified via SSH)

| Component | Status |
|-----------|--------|
| **Hailo device** | HAILO10H, FW 5.1.1, identified at `0001:01:00.0` |
| **Ollama** | `/usr/local/bin/ollama` v0.15.2 |
| **hailo-ollama** | `/usr/bin/hailo-ollama` (runs as service; port in use when started) |
| **Installed models** | `llama3.2:1b` (ollama, port 11434); **qwen2:1.5b** (hailo-ollama, port **8000**) |
| **Hailo packages** | h10-hailort 5.1.1, hailo-gen-ai-model-zoo 5.1.1, hailo-tappas-core 5.1.0, hailo-models, python3-h10-hailort, rpicam-apps-hailo-postprocess |
| **Hailo models (HEF)** | `/usr/share/hailo-models/` — YOLO, pose, ResNet, etc. (vision); `/usr/share/hailo-ollama/models/` — GenAI (blob, manifests) |

---

## 2. hailo-ollama — How It Fits

### What it is

- **hailo-ollama** = Ollama-compatible server (C++) on top of **HailoRT**, so LLM/VLM inference runs on the **Hailo-10H** accelerator, not CPU.
- Same HTTP API as standard Ollama (and OpenAI-compatible), so existing Ollama/OpenAI clients work.
- **Standard `ollama`** on the Pi runs CPU-only; **hailo-ollama** uses the HAT for acceleration.

### Relationship on your Pi

- **hailo-ollama** listens on **port 8000** (config: `/etc/xdg/hailo-ollama/hailo-ollama.json`).
- They typically share the same port (e.g. 11434); only one can run at a time (hence “Address already in use” when both try to bind).
- For **voice assistant + low latency**, use **hailo-ollama** at `http://pi5.local:8000` so the 1B/1.5B models run on Hailo-10H.

### Supported models (Hailo-10H)

- **Llama 3.2 1B** (you already have `llama3.2:1b`)
- **DeepSeek-R1-Distill 1.5B** (and others from Hailo’s GenAI model zoo)
- Models are Hailo-compiled (HEF/GenAI zoo), not arbitrary Hugging Face GGUF; use what’s provided for hailo-ollama.

### Leveraging it for our applications

1. **Voice assistant (Phase 1)**  
   - Use **hailo-ollama** as the LLM backend (Ollama/OpenAI API).  
   - Pipeline: Mic → STT (Hailo Whisper) → LLM (hailo-ollama, e.g. `llama3.2:1b`) → TTS (Piper).  
   - Ensures LLM runs on Hailo-10H for better latency and frees CPU for STT/TTS/IO.

2. **RAG / vector DB on Pi**  
   - Same idea: ingestion on Mac, vector DB on Pi, LLM on Pi via **hailo-ollama**.  
   - Your app queries local vector DB and sends the augmented prompt to `http://pi5.local:8000` (hailo-ollama).

3. **Practical usage**  
   - **hailo-ollama** runs on **port 8000** (bind: `0.0.0.0`, so reachable from Mac at `http://pi5.local:8000`).  
   - Point your app at `OLLAMA_HOST=http://pi5.local:8000` (or `http://localhost:8000` when on the Pi).  
   - Use existing Ollama/OpenAI client code; no change except ensuring the server is hailo-ollama when you want Hailo acceleration.

---

## 3. Hailo Voice Options for the Voice Assistant

### 3.1 hailo-apps (recommended for full stack)

Repository: **https://github.com/hailo-ai/hailo-apps**

Provides a full voice stack that matches our roadmap:

| App | Role | Notes |
|-----|------|--------|
| **Voice Assistant** | End-to-end: STT → LLM → TTS | Uses Hailo Whisper (STT), Piper (TTS), and an LLM (Ollama-compatible API → use hailo-ollama). |
| **Speech Recognition** | Standalone STT (Whisper on Hailo) | Whisper-tiny / Whisper-base on Hailo-8/8L/10H; CLI + GUI (Streamlit). |
| **Agent Tools Example** | Voice-to-action | Natural language → hardware control (GPIO, servos, LEDs, etc.); same voice pipeline. |
| **voice_processing** (module) | Reusable building blocks | `SpeechToTextProcessor`, `TextToSpeechProcessor`, `AudioRecorder`, `VoiceInteractionManager`, VAD. |

So for **our** voice assistant we can:

- Use **hailo-apps** for STT (Hailo Whisper) + TTS (Piper) + audio I/O and VAD.
- Use **hailo-ollama** as the LLM backend (Ollama API).
- Optionally start from their **Voice Assistant** or **Agent Tools** and swap the LLM endpoint to hailo-ollama.

### 3.2 STT (Speech-to-Text)

- **Primary:** Hailo Whisper (via hailo-apps)  
  - **Speech Recognition** app: `python3 -m app.app_hailo_whisper [--hw-arch hailo10h] [--variant base|tiny]`  
  - **Voice Assistant** uses the same pipeline via `SpeechToTextProcessor` (voice_processing).  
  - Use `--hw-arch hailo10h` on Pi 5 + HAT+2.

- **Fallback (roadmap):** whisper.cpp on CPU if Hailo STT is unavailable or for debugging.

### 3.3 TTS (Text-to-Speech)

- **Piper** (as in hailo-apps and our roadmap):  
  - Install Piper model(s) in `local_resources/piper_models/` (e.g. `en_US-amy-low`).  
  - Voice processing module: `TextToSpeechProcessor` with streaming and interrupt (barge-in).  
- **Tool:** `hailo-audio-troubleshoot` for device selection and `hailo-audio-troubleshoot --install-tts` for Piper.

#### TTS voice options

| Option | Description |
|--------|-------------|
| **Piper (default)** | Neural TTS; you have **en_US-amy-low** and **en_US-amy-medium** in `~/piper_models` (and in hailo-apps `local_resources/piper_models`). Default voice in our script: `en_US-amy-medium`. |
| **pyttsx3** | System TTS (espeak on Pi); more robotic, no download. Use: `TTS_ENGINE=pyttsx3 python3 ~/voice_assistant_pi.py --once "Hello"`. |

**Switch Piper voice (same engine, different speaker):** set `PIPER_VOICE` and put the model in `PIPER_MODEL_DIR` (default `~/piper_models`).

- **Currently on Pi:** `en_US-amy-low`, `en_US-amy-medium` (female).
- **More Piper voices (en_US):** download with `python3 -m piper.download_voices <name>` from the Piper models dir. Examples:
  - **en_US-ryan-low** / **en_US-ryan-medium** / **en_US-ryan-high** — male (high = most natural, larger file).
  - **en_US-danny-low**, **en_US-joe-low**, **en_US-john-low**, **en_US-norman-low** — other male voices.
  - **en_US-kathleen-low**, **en_US-kristin-low** — other female voices.
- **Use a different voice:**  
  `PIPER_VOICE=en_US-ryan-low python3 ~/voice_assistant_pi.py --tts piper --once "Hello"`  
  (after downloading: `cd ~/piper_models && python3 -m piper.download_voices en_US-ryan-low`).

**Voice catalog:** [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US) (en_US: amy, ryan, danny, joe, john, kathleen, kristin, norman, sam, and more; each has low/medium/high).

**Download all en_US voices (one per speaker):** Copy and run on the Pi: `scripts/pi_download_all_piper_voices_en_us.sh` → `~/pi_download_all_piper_voices_en_us.sh` then `~/pi_download_all_piper_voices_en_us.sh`. Requires `python3 -m piper` (e.g. `pip install piper-tts` or use from `~/hailo-apps` env). Voices go to `~/piper_models`.

**Darth Vader / Homer Simpson (character voices):** Piper only has natural-speaker voices, not character or celebrity clones. For Darth Vader– or Homer-style TTS you’d need:
- **Voice cloning:** Train or use a model on character samples (e.g. [Coqui TTS](https://github.com/coqui-ai/TTS), [ZeroVox](https://github.com/gooofy/zerovox)) — requires voice samples and more setup.
- **Online services:** Some sites offer Homer/Darth-style TTS (e.g. anyvoicelab.com, vocalize.fm); they’re usually cloud-based, not offline.
- **Roadmap:** “Fun character voices” are listed as Phase 3+ in `VOICE_ASSISTANT_ROADMAP.md` (e.g. after RAG and polish).

### 3.4 Audio and diagnostics

- **hailo-audio-troubleshoot**
  - List devices, test mic/speaker, select and save preferred devices.
- **TTS testing before ReSpeaker:** Lenrue wireless stereo speaker — **mapped on Pi as A12**, MAC **0B:B1:E3:49:9B:D9**. Copy and run `scripts/pi_pair_lenrue_speaker.sh` on the Pi (speaker in pairing mode); or manually `bluetoothctl pair 0B:B1:E3:49:9B:D9` then `connect` / `trust`, then set default sink in PulseAudio so Piper TTS plays through it.
  - Use for Pi audio setup (USB mic recommended).  
- Preferences: `local_resources/audio_device_preferences.json`.  
- VAD: `VoiceInteractionManager` supports VAD (hands-free), configurable sensitivity.

### 3.5 Installing and running hailo-apps on the Pi

1. Clone and install (on Pi):
   ```bash
   git clone https://github.com/hailo-ai/hailo-apps.git
   cd hailo-apps
   sudo ./install.sh
   source setup_env.sh
   ```
2. Install Piper TTS (from repo root):
   ```bash
   cd local_resources/piper_models
   python3 -m piper.download_voices en_US-amy-low
   ```
3. Audio:
   ```bash
   hailo-audio-troubleshoot --select-devices   # if needed
   ```
4. Run Voice Assistant (uses Ollama-compatible API; ensure hailo-ollama is running on port 8000):
   ```bash
   ~/run_hailo_voice_assistant.sh
   ```
   Copy the script from this repo: `scripts/run_hailo_voice_assistant.sh` to Pi home and `chmod +x ~/run_hailo_voice_assistant.sh`. The script sets `OLLAMA_HOST=http://127.0.0.1:8000` and launches the hailo-apps Voice Assistant. Or run manually:
   ```bash
   cd ~/hailo-apps && source setup_env.sh
   export OLLAMA_HOST=http://127.0.0.1:8000
   python -m hailo_apps.python.gen_ai_apps.voice_assistant.voice_assistant
   ```
5. Optional: run standalone Speech Recognition (Whisper on Hailo):
   ```bash
   cd hailo_apps/python/standalone_apps/speech_recognition/app
   python3 -m app.app_hailo_whisper --hw-arch hailo10h --variant base
   ```

---

## 4. Summary: How We Use Hailo for the Voice Assistant

| Layer | Technology | Where it runs |
|-------|------------|----------------|
| **STT** | Hailo Whisper (hailo-apps) | Hailo-10H |
| **LLM** | hailo-ollama (e.g. llama3.2:1b) | Hailo-10H |
| **TTS** | Piper (hailo-apps voice_processing) | Pi CPU |
| **Audio I/O** | sounddevice + hailo-audio-troubleshoot | Pi |
| **RAG (Phase 2)** | Vector DB on Pi, ingestion on Mac | Pi (storage + query), Mac (ingestion) |

This keeps STT and LLM on the accelerator and fits the latency and offline goals in `VOICE_ASSISTANT_ROADMAP.md`.

### TTS speed and the Hailo HAT

**Can we run TTS on the Hailo HAT?** No. Hailo’s current software does **not** support TTS (text-to-speech) on the accelerator. The Hailo Model Zoo and GenAI stack provide:
- **LLM** (hailo-ollama) and **STT** (Hailo Whisper) on Hailo-10H  
- **No** neural TTS or Piper-on-Hailo

So TTS (Piper) stays on the **Pi CPU**. To make conversation feel faster and more natural:

| What we do | Effect |
|------------|--------|
| **Streaming playback** | Piper’s raw output is piped straight to `paplay` so playback starts as soon as the first audio chunks are ready (lower time-to-first-audio). |
| **Faster pacing** | `PIPER_LENGTH_SCALE=0.9`, `PIPER_SENTENCE_SILENCE=0.1` (defaults in our script) for quicker speech and shorter pauses. |
| **Low-quality voice (optional)** | Use `en_US-joe-low` instead of `en_US-joe-medium` for faster CPU inference (smaller model); download with `python3 -m piper.download_voices en_US-joe-low` if needed. |
| **Shorter replies** | Add a system prompt or instruction so the LLM gives brief answers → less text → less TTS work. |

The CPU spike during TTS is normal; streaming reduces how long you wait before hearing the start of the reply.

---

## 5. References

- **hailo-apps:** https://github.com/hailo-ai/hailo-apps  
- **Hailo Model Zoo (vision):** https://github.com/hailo-ai/hailo_model_zoo  
- **Hailo GenAI / hailo-ollama (RPi):** Hailo Developer Zone + [hailo-rpi5-examples](https://github.com/hailo-ai/hailo-rpi5-examples)  
- **Voice processing (Piper, STT, VAD):** `hailo_apps/python/gen_ai_apps/gen_ai_utils/voice_processing/README.md`  
- **Voice Assistant roadmap:** `VOICE_ASSISTANT_ROADMAP.md`
