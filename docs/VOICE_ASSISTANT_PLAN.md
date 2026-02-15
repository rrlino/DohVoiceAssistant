# Voice Assistant — Plan, Phases & Checklist

**Target:** Raspberry Pi 5 16GB + AI HAT+2 (Hailo-10H)  
**Pi access:** `ssh <username>@pi5.local` — if hostname doesn't resolve, use IP: `ssh <username>@<pi-ip-address>`

---

## Where we are now (status)

| Done | Item |
|------|------|
| ✅ | Pi 5 + Hailo HAT; hailo-ollama on port 8000 (qwen2:1.5b) |
| ✅ | hailo-apps installed at `~/hailo-apps`; GenAI + Piper TTS |
| ✅ | Piper: 19 en_US voices in `~/piper_models`; **Joe (en_US-joe-medium)** chosen for replies |
| ✅ | Lenrue speaker (A12) paired and default sink; TTS plays on Bluetooth |
| ✅ | **Text → LLM → TTS → speaker:** `voice_assistant_pi.py` with `--tts piper` and `PIPER_VOICE=en_US-joe-medium` |
| ✅ | Sample scripts: Ricardo intro, Helena intro (Joe voice); poem (Piper) |
| ❌ | **No mic yet** — ReSpeaker Lite on order; no STT (speak-to-type) until mic is connected |

**Current capability:** You can **type** a question on the Pi and get an **LLM reply spoken** by Joe on the Lenrue. Full **voice-in → spoken-out** (ask by speaking) needs a microphone (ReSpeaker or USB mic) and then hailo-apps Voice Assistant.

---

## Next steps — Chat interface (ask freely, responses read)

**Goal:** A chat flow where you ask freely (text or, later, voice) and every response is read aloud by Joe on the Lenrue.

### Option A — Text chat with spoken replies (available now)

Use the existing script in **interactive loop** mode so you type questions and hear Joe speak the answers:

**On the Pi:**
```bash
# Ensure Lenrue is default sink, then:
pactl set-default-sink bluez_sink.0B_B1_E3_49_9B_D9.a2dp_sink   # if needed
PIPER_VOICE=en_US-joe-medium python3 ~/voice_assistant_pi.py --tts piper --loop
```
- You’ll see `You:` — type your question and press Enter.
- The LLM (hailo-ollama) generates a reply; it’s printed and **spoken by Joe** on the Lenrue.
- Repeats until you press Ctrl+C.

**Prereqs:** hailo-ollama running on port 8000; Lenrue connected and set as default sink.

### Option B — Voice chat (ask by speaking, hear Joe reply) — after mic

When the **ReSpeaker Lite** (or a USB mic) is connected:

1. **Select devices:** On the Pi run `hailo-audio-troubleshoot --select-devices` and choose ReSpeaker mic (input) and Lenrue or ReSpeaker speaker (output).
2. **Run hailo-apps Voice Assistant:**  
   `~/run_hailo_voice_assistant.sh`
3. **Use it:** Press **Space** to start/stop recording; ask your question aloud; the assistant will transcribe (STT), send to the LLM, and speak the reply (TTS). You can optionally configure hailo-apps to use Joe’s Piper voice if supported.

**Prereqs:** ReSpeaker (or USB mic) + speaker connected; hailo-ollama on 8000; `~/run_hailo_voice_assistant.sh` on the Pi.

### One-command chat (text → spoken reply)

Copy and run on the Pi:
```bash
# Copy from repo once:
scp scripts/pi_chat_with_joe.sh <username>@pi5.local:~/
ssh <username>@pi5.local 'chmod +x ~/pi_chat_with_joe.sh'

# Then on the Pi:
~/pi_chat_with_joe.sh
```
At the `You:` prompt, type your question and press Enter; Joe will speak the reply on the Lenrue. Ctrl+C to quit.

### Optional improvements (chat interface)

- **Default Joe in script:** Set `PIPER_VOICE=en_US-joe-medium` as the default in `voice_assistant_pi.py` so any `--loop` run uses Joe without setting the env.
- **Web UI (later):** Simple local web page (e.g. Flask + WebSocket) where you type (or speak when mic exists) and see replies + trigger TTS playback on the Pi.

---

## Hardware (Audio — When It Arrives)

You’re ordering:

| Item | Description | Source |
|------|-------------|--------|
| **ReSpeaker Lite with XIAO ESP32S3** | USB audio + mic array (Seeed) | The Pi Hut — £28.80 |
| **Mono Enclosed Speaker for ReSpeaker Lite** | 4 Ω, 5 W | The Pi Hut — £2.40 |
| **Black DIY Case for ReSpeaker Lite** | Enclosure | The Pi Hut — £4.80 |

**Current speaker for TTS testing (before ReSpeaker arrives):** Lenrue wireless stereo speaker (generic Chinese / Lenrue brand).

| Pi mapping | Value |
|------------|--------|
| **Name** | A12 |
| **MAC** | 0B:B1:E3:49:9B:D9 |

Pair when speaker is in **pairing mode**: on the Pi run `~/pi_pair_lenrue_speaker.sh` (script is already on the Pi), or use bluetoothctl in one session: `scan on` → wait for A12 → `pair` / `connect` / `trust`. For **audio playback**: install PulseAudio + BT module (`sudo apt install pulseaudio pulseaudio-module-bluetooth`), start PulseAudio (`pulseaudio --start`), connect speaker (`bluetoothctl connect 0B:B1:E3:49:9B:D9`), set default sink (`pactl set-default-sink bluez_sink.0B_B1_E3_49_9B_D9.a2dp_sink`). Then TTS (e.g. Piper) plays through the Lenrue.

**Milestone — Lenrue speaker working for TTS (done):**
- [x] Speaker paired (A12, 0B:B1:E3:49:9B:D9) via bluetoothctl in one session
- [x] PulseAudio + pulseaudio-module-bluetooth installed on Pi
- [x] Connect: `bluetoothctl connect 0B:B1:E3:49:9B:D9` (with PulseAudio running)
- [x] Default sink set to `bluez_sink.0B_B1_E3_49_9B_D9.a2dp_sink`
- [x] Test sound played (`speaker-test -t wav -c 2 -l 1`) on Lenrue
- [x] TTS played on Lenrue (pyttsx3 used for first test; Piper via hailo-apps when installed)

Until the ReSpeaker hardware arrives, we run in **Phase 0** (no mic/speaker): install everything and validate the pipeline with **text-in → LLM → text-out**, **TTS to file**, and **STT from sample WAV** where possible.

---

## Phases Overview

| Phase | Name | Goal | Blocker |
|-------|------|------|---------|
| **Phase 0** | No mic/speaker | Install stack; validate LLM, TTS (to file), STT (from file if supported) | — |
| **Phase 1** | ReSpeaker + speaker | Full voice: mic → STT → LLM → TTS → speaker | ReSpeaker + speaker + case arrive |
| **Phase 2** | RAG / knowledge | Vector DB on Pi, optional static prompt | After Phase 1 stable |
| **Phase 3** | Polish | VAD, wake word, service mode, voice-to-action | Per roadmap |

---

## Phase 0 — No Mic/Speaker (Start Here)

**Goal:** Install and test the full pipeline without live audio. Validate LLM, TTS output to file, and STT from a test file (if the app supports it).

### Phase 0 — Checklist

#### 0.1 — Pi & Hailo

- [ ] SSH to Pi: `ssh <username>@pi5.local`
- [ ] Hailo HAT detected: `hailortcli fw-control identify` → HAILO10H
- [ ] (Optional) GStreamer Hailo plugins: `gst-inspect-1.0 hailo` (if using pipeline apps later)

#### 0.2 — hailo-ollama (LLM)

- [ ] Start hailo-ollama on Pi: `nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &`
- [ ] From Pi: `curl -s http://127.0.0.1:8000/api/tags` → lists e.g. `qwen2:1.5b`
- [ ] From Mac: `curl -s http://pi5.local:8000/api/generate -d '{"model":"qwen2:1.5b","prompt":"Hi","stream":false}' -H "Content-Type: application/json"` → returns a reply
- [ ] From Mac: `python3 test_pi_qwen.py --list` and `python3 test_pi_qwen.py --prompt "Hello"` work

#### 0.3 — hailo-apps (clone & install)

- [ ] On Pi: `cd ~ && git clone https://github.com/hailo-ai/hailo-apps.git && cd hailo-apps`
- [ ] On Pi: `sudo ./install.sh` (finish without errors)
- [ ] On Pi: `source setup_env.sh` (then in same shell) `pip install -e ".[gen-ai]"` if needed
- [ ] On Pi: `hailo-detect-simple --help` or similar exists (confirms install)

#### 0.4 — Piper TTS (no speaker needed)

- [ ] On Pi: `cd ~/hailo-apps/local_resources/piper_models && python3 -m piper.download_voices en_US-amy-low`
- [ ] Or: `hailo-audio-troubleshoot --install-tts` (if available)
- [ ] Verify files: `ls ~/hailo-apps/local_resources/piper_models/` → `en_US-amy-low.onnx` and `.onnx.json`

#### 0.5 — Test TTS to file (no speaker)

- [ ] On Pi (with env): run a small script or hailo-apps example that synthesizes “Hello world” to a WAV file (or use Piper CLI to generate WAV)
- [ ] Copy WAV to Mac and play, or play on Pi with `aplay` if default audio exists — confirms TTS works without a physical speaker

#### 0.5b — Test TTS on Lenrue speaker (Bluetooth)

- [x] On Pi: ensure PulseAudio running, Lenrue connected, default sink set (see Lenrue milestone above)
- [x] Run TTS: used **pyttsx3** to say "Hello, this is a test of text to speech from your Raspberry Pi." — plays to default sink (Lenrue)
- [ ] (Optional) Piper: install via hailo-apps or standalone when full voice stack is set up; piper-tts (pip) needs phonemizer/espeakbridge on Pi

#### 0.6 — Test STT from file (no mic) — if supported

- [ ] Check if hailo-apps Speech Recognition or voice_processing can accept an input WAV file
- [ ] If yes: run STT on a short English WAV (e.g. 3–5 s); confirm transcript
- [ ] If no: skip; we’ll validate STT in Phase 1 with the ReSpeaker mic

#### 0.7 — Text-only pipeline (LLM only)

- [ ] From Mac or Pi: send a prompt to `http://127.0.0.1:8000` (or `pi5.local:8000`), get reply — already done with `test_pi_qwen.py`
- [ ] Optional: on Pi, run a minimal “chat” script that reads a line from stdin → calls hailo-ollama → prints reply (confirms LLM integration without voice)

#### 0.8 — Voice Assistant config (no run yet)

- [ ] Decide how to set `OLLAMA_HOST=http://127.0.0.1:8000` and model `qwen2:1.5b` (env var or wrapper script)
- [ ] Document in this repo (e.g. in `voice_assistant/README` or this plan) the exact command to run Voice Assistant when audio is ready

**Phase 0 exit:** hailo-apps installed, Piper TTS works (to file), LLM tested from Mac and Pi. Ready to plug in ReSpeaker + speaker when they arrive.

---

## Input (speak) → Response + Smoother voice (current)

**Goal:** You speak (or type for now), assistant replies with voice. Smoother TTS via Piper.

### Input (mic) — when available

- **Right now:** The Pi has **no microphone** (`arecord -l` shows no capture devices). Only the Lenrue speaker (output) is connected.
- **For “speak and be heard”:** You need a **USB microphone** or the **ReSpeaker Lite** (on order). Once a mic is connected, we add **STT** (e.g. Hailo Whisper via hailo-apps, or whisper.cpp) so the assistant listens to your voice.
- **Until then:** Use **text input**: type your message, assistant replies with voice (LLM + TTS).

### Response flow (text input for now)

On the Pi we have a script: **`~/voice_assistant_pi.py`** (also in this repo: `scripts/voice_assistant_pi.py`).

- **One shot:**  
  `python3 ~/voice_assistant_pi.py --once "What is the weather?"`  
  → LLM reply is printed and spoken on the Lenrue.
- **Interactive (one turn):**  
  `python3 ~/voice_assistant_pi.py`  
  → Prompts "You:", you type, get reply + TTS.
- **Interactive loop:**  
  `python3 ~/voice_assistant_pi.py --loop`  
  → Keeps asking "You:" until Ctrl+C.
- **Pipe:**  
  `echo "Hello" | python3 ~/voice_assistant_pi.py`  
  → Speaks the LLM reply.

Requires: **hailo-ollama** running on port 8000, **PulseAudio** + Lenrue connected and default sink set.

### Smoother voice (Piper)

- **Default TTS** in the script is **pyttsx3** (espeak) — works everywhere but sounds robotic.
- **Smoother option:** **Piper** (neural TTS). On the Pi we installed the **standalone Piper binary** at **`~/piper`** and voice **en_US-amy-medium** at **`~/piper_models`**.
- **Use Piper:**  
  `python3 ~/voice_assistant_pi.py --tts piper --once "Hello"`  
  Or set env: `PIPER_BIN=~/piper/piper PIPER_ESPEAK_DATA=~/piper/espeak-ng-data PIPER_LD_LIBRARY_PATH=~/piper`.
- **More natural sound (options):**
  - **Voice:** `PIPER_VOICE=en_US-amy-medium` (default). For even more natural: download a **high**-quality voice, e.g. `en_US-ryan-high` or `en_US-amy-high` (~100–185 MB), then set `PIPER_VOICE=en_US-ryan-high`.
  - **Pacing:** `PIPER_LENGTH_SCALE=1.2` (default) — slightly slower = more natural; try 1.25–1.3 for calmer speech.
  - **Pause:** `PIPER_SENTENCE_SILENCE=0.35` — pause after each sentence (seconds).
  - **Variation:** `PIPER_NOISE_SCALE=0.7`, `PIPER_NOISE_W=0.85` — slight variation so it sounds less “perfect” and more human.

### Who processes what (pipeline)

| Step | Who does it | Where it runs |
|------|----------------|---------------|
| **Text generation** (prompt → reply) | **hailo-ollama** (qwen2:1.5b) | **Hailo-10H** accelerator on the Pi |
| **Speech** (reply text → audio) | **Piper** TTS | **Pi CPU** (ARM) |
| **Playback** | PulseAudio → Lenrue | Pi (default sink = Bluetooth speaker) |

So: **hailo-ollama** produces the assistant’s reply text (on the Hailo HAT); **Piper** turns that text into speech (on the Pi CPU); audio goes to the Lenrue speaker.

### Checklist — input and response

- [x] Voice assistant script on Pi: text → LLM → TTS (pyttsx3 or Piper)
- [x] Piper standalone binary at ~/piper for smoother TTS
- [ ] **Mic input:** When ReSpeaker (or USB mic) is available, add STT and wire: mic → STT → same script (or hailo-apps Voice Assistant)

---

## Phase 1 — ReSpeaker + Speaker (When Hardware Arrives)

**Goal:** Full voice pipeline: ReSpeaker mic → STT → LLM → TTS → ReSpeaker speaker (or Mono Enclosed Speaker).

### Hardware to receive

- ReSpeaker Lite with XIAO ESP32S3 (USB mic/audio)
- Mono Enclosed Speaker for ReSpeaker Lite (4 Ω, 5 W)
- Black DIY Case for ReSpeaker Lite

### Phase 1 — Checklist

#### 1.1 — Unbox and connect

- [ ] Unbox ReSpeaker Lite, speaker, and case; assemble per Seeed instructions
- [ ] Connect ReSpeaker Lite to Pi via USB
- [ ] Connect Mono Enclosed Speaker to ReSpeaker Lite (correct terminals / jack)
- [ ] Power on Pi; confirm ReSpeaker is detected (e.g. `arecord -l`, `aplay -l`, or `hailo-audio-troubleshoot`)

#### 1.2 — Audio devices on Pi

- [ ] Run `hailo-audio-troubleshoot` on Pi
- [ ] List input devices: confirm ReSpeaker mic appears
- [ ] List output devices: confirm ReSpeaker (or speaker) appears
- [ ] Run device tests: record a few seconds, play back
- [ ] Save preferred devices: `hailo-audio-troubleshoot --select-devices` (input = ReSpeaker mic, output = ReSpeaker/speaker)

#### 1.3 — Voice Assistant (full pipeline) — **hailo-apps**

- [x] hailo-apps installed on Pi (`~/hailo-apps`), GenAI deps + Piper TTS in `local_resources/piper_models`
- [x] hailo-ollama on port 8000 (Hailo-10H); `OLLAMA_HOST=http://127.0.0.1:8000` (set by run script)
- [ ] **Run Voice Assistant:** On Pi run **`~/run_hailo_voice_assistant.sh`** (script in repo: `scripts/run_hailo_voice_assistant.sh` — copy to Pi home if needed). Script sets OLLAMA_HOST and launches hailo-apps Voice Assistant (STT → LLM → TTS).
- [ ] Press **Space** to start/stop recording; speak a short question; hear spoken reply on speaker (needs mic; output = default sink, e.g. Lenrue)
- [ ] Repeat 5+ times without crash (stability check)

#### 1.4 — Latency and logging

- [ ] Note or log: time from end-of-speech to first TTS audio (target ~1.5–2.0 s typical)
- [ ] If hailo-apps supports it, enable per-stage timings (STT, LLM, TTS) for tuning
- [ ] Optional: add a small wrapper in this repo that sets `OLLAMA_HOST` and model and launches the assistant

#### 1.5 — ReSpeaker-specific (if needed)

- [ ] If ReSpeaker needs extra drivers or udev rules, install per Seeed docs
- [ ] If sample rate / format issues: adjust in `hailo-audio-troubleshoot` or voice_processing config
- [ ] Document any ReSpeaker quirks in this plan or in `HAILO_PI_SETUP.md`

**Phase 1 exit:** Reliable speak → reply on Pi with ReSpeaker mic and speaker; latency in target range.

---

## Phase 2 — RAG / Static Knowledge (Later)

- [ ] Decide: static prompt file only, or vector DB on Pi (ingestion on Mac)
- [ ] If vector DB: choose (e.g. SQLite-vec, LanceDB), ingest on Mac, sync to Pi, query from assistant
- [ ] If static only: add system prompt or knowledge file; wire into Voice Assistant or wrapper
- [ ] Retrieval latency target: ≤ 150 ms (Phase 2)

---

## Phase 3 — Polish (Later)

- [ ] VAD / wake word (hands-free)
- [ ] Barge-in (interrupt TTS when user speaks)
- [ ] Voice-to-action / tools (optional)
- [ ] systemd service, config file, watchdog (run on boot)

---

## Step-by-Step Installation (Pi) — Reference

All commands on the Pi unless noted.

### 1. Prerequisites (already done)

```bash
hailortcli fw-control identify   # → HAILO10H
nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &
curl -s http://127.0.0.1:8000/api/tags
```

### 2. Clone and install hailo-apps

```bash
cd ~
git clone https://github.com/hailo-ai/hailo-apps.git
cd hailo-apps
sudo ./install.sh
source setup_env.sh
pip install -e ".[gen-ai]"   # if needed
```

### 3. Install Piper TTS

```bash
cd ~/hailo-apps/local_resources/piper_models
python3 -m piper.download_voices en_US-amy-low
```

### 4. (Phase 0) Test TTS to file

Use Piper or hailo-apps to generate a WAV (e.g. “Hello world”), save to `~/test_tts.wav`. Play on Mac or with `aplay` if output exists.

### 5. (Phase 1) Audio setup — when ReSpeaker + speaker arrive

```bash
hailo-audio-troubleshoot
hailo-audio-troubleshoot --select-devices
```

### 6. Run Voice Assistant (Phase 1)

**Preferred (one command):**
```bash
~/run_hailo_voice_assistant.sh
```
Copy the script from this repo: `scripts/run_hailo_voice_assistant.sh` → Pi home, then `chmod +x ~/run_hailo_voice_assistant.sh`.

**Or manually:**
```bash
source ~/hailo-apps/setup_env.sh
export OLLAMA_HOST=http://127.0.0.1:8000
python -m hailo_apps.python.gen_ai_apps.voice_assistant.voice_assistant
```

---

## hailo-apps voice stack (primary)

| Layer | Component | Where |
|-------|-----------|--------|
| **STT** | Hailo Whisper (hailo-apps) | Hailo-10H |
| **LLM** | hailo-ollama (Ollama API, port 8000) | Hailo-10H |
| **TTS** | Piper (hailo-apps `local_resources/piper_models`) | Pi CPU |
| **Audio I/O** | sounddevice + hailo-audio-troubleshoot | Pi |

**Run:** `~/run_hailo_voice_assistant.sh` on the Pi (script: `scripts/run_hailo_voice_assistant.sh`). Requires hailo-ollama running (`nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &`) and, for full voice, a mic (e.g. ReSpeaker) and default output (e.g. Lenrue) set in `hailo-audio-troubleshoot --select-devices`.

---

## What Lives Where

| Item | Location |
|------|----------|
| Voice assistant app | Pi: `~/hailo-apps` |
| Run script (voice assistant) | This repo: `scripts/run_hailo_voice_assistant.sh` → copy to Pi `~/run_hailo_voice_assistant.sh` |
| Chat with Joe (text → spoken) | This repo: `scripts/pi_chat_with_joe.sh` → copy to Pi `~/pi_chat_with_joe.sh`; run `~/pi_chat_with_joe.sh` |
| LLM server | Pi: hailo-ollama, port 8000 |
| Test script (Qwen from Mac) | This repo: `test_pi_qwen.py` |
| Plan / roadmap | This repo: `VOICE_ASSISTANT_PLAN.md`, `VOICE_ASSISTANT_ROADMAP.md`, `HAILO_PI_SETUP.md` |
| Future config / wrapper | This repo: e.g. `voice_assistant/` |

---

## Success Criteria

**Phase 0**

- [ ] hailo-apps and Piper installed on Pi; LLM and TTS (to file) verified; STT from file if supported.

**Phase 1**

- [ ] ReSpeaker + speaker connected and selected in hailo-audio-troubleshoot.
- [ ] Voice Assistant: speak → hear reply; 5+ turns stable; full-turn latency ~1.5–2.0 s.

**Phase 2+**

- [ ] Optional RAG or static knowledge; then VAD, wake word, service mode per roadmap.
