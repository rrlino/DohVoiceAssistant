# Voice Assistant (Offline, Low-Latency) — Roadmap

## Goals

- Fully offline operation (no external APIs required for core functionality)
- Good interactive latency on Raspberry Pi 5 (16GB) + AI HAT+2 (Hailo-10H)
- Reliable audio UX (barge-in, interruption, noise robustness)
- Modular architecture so STT/LLM/TTS can be swapped without redesign

## Non-Goals (initially)

- High-quality voice cloning (requires heavier models and/or complex conversion)
- Multi-user speaker identification / diarization
- Cloud fallback (optional later)

## Target Platform

- Raspberry Pi 5 16GB
- Raspberry Pi AI HAT+2 (Hailo-10H)
- Raspberry Pi OS 64-bit (Bookworm or Trixie)

## Phase 1 — Fast Chatbot with Static Knowledge (No RAG)

**Outcome**: Assistant answers quickly using a large static prompt as its knowledge base.

- Load a single large prompt file at startup (concatenated markdown knowledge)
- Keep the prompt within the LLM’s context window
- Prioritize low-latency responses; no retrieval step

## Phase 2 — RAG + Vector DB (Future)

**Outcome**: Assistant can search a larger knowledge base (100+ docs) with low-latency retrieval.

- Add a vector database
- Ingest markdown documents
- Retrieve top-k chunks on each turn
- Tune retrieval to stay within latency budget

## High-Level Architecture

### Pipeline (Phase 1)

1. Audio capture (mic)
2. VAD / wake word (always-listening + fallback)
3. STT (speech-to-text)
4. NLU / conversation manager (static prompt)
5. LLM inference (fast model, reduced context)
6. TTS synthesis
7. Audio playback (speaker) with barge-in (interrupt) — TODO post-MVP

### Pipeline (Phase 2)

1. Audio capture (mic)
2. VAD / wake word (always-listening + fallback)
3. STT (speech-to-text)
4. NLU / conversation manager
5. RAG retrieval (vector DB)
6. LLM inference (retrieved context + prompt)
7. TTS synthesis
8. Audio playback (speaker) with barge-in (interrupt) — TODO post-MVP

### Recommended “v1” tech choices

- STT:
  - Use the Hailo-provided Whisper-based speech recognition pipeline where possible (via `hailo-apps`).
  - If needed, use `whisper.cpp` as a CPU fallback.
- LLM:
  - **With Hailo HAT:** use **hailo-ollama** (Ollama-compatible API, LLM on Hailo-10H). Supported models: Llama 3.2 1B, DeepSeek-R1-Distill 1.5B, etc. See `HAILO_PI_SETUP.md`.
  - Without Hailo: `llama.cpp` (direct) or `ollama` (CPU); run a 7B model quantized to 4-bit (GGUF Q4) for best latency/memory tradeoff.
- TTS:
  - Piper (offline, fast on ARM); hailo-apps voice_processing includes Piper + streaming + barge-in.

**Implementation (Phase 1):** The primary stack is **hailo-apps** Voice Assistant on the Pi: STT (Hailo Whisper) → LLM (hailo-ollama, port 8000) → TTS (Piper). Run with **`~/run_hailo_voice_assistant.sh`** on the Pi (script in repo: `scripts/run_hailo_voice_assistant.sh`). See `VOICE_ASSISTANT_PLAN.md` and `HAILO_PI_SETUP.md` for setup and checklist.

## Latency Targets (Acceptance Criteria)

### Phase 1 (Static Prompt)

- Time-to-first-text (end of speech → first transcript text): <= 700ms
- Time-to-first-token (STT final → first LLM token): <= 500ms
- Time-to-first-audio (first LLM token → first audible audio): <= 800ms
- Full turn latency (end of speech → start of spoken reply): <= 1.5–2.0s typical
- Barge-in: TODO post-MVP
  - When user starts speaking, TTS stops within <= 200ms

### Phase 2 (RAG)

- Same as Phase 1, plus:
- RAG retrieval (top-k from vector DB): <= 150ms
- Full turn latency (end of speech → start of spoken reply): <= 2.0–2.5s typical

## Milestones

### M0 — Hardware + OS bring-up (Hailo + audio)

**Outcome**: device recognized, stable runtime, audio I/O works.

- Install Hailo runtime and verify device:
  - `hailortcli fw-control identify`
- Verify GStreamer plugins (if using pipelines):
  - `gst-inspect-1.0 hailo`
  - `gst-inspect-1.0 hailotools`
- Configure audio devices and validate mic/speaker:
  - Use `hailo-audio-troubleshoot` (from `hailo-apps`) or equivalent

**Exit criteria**

- Hailo device visible and stable after reboot
- Mic capture and speaker playback validated

### M1 — STT baseline (offline) with measurable latency

**Outcome**: STT can transcribe short commands reliably.

- Implement a CLI STT test harness:
  - press-to-talk recording
  - STT returns text + timestamps
  - save WAV + transcript for evaluation

**Exit criteria**

- Can transcribe 30 sample utterances with acceptable accuracy
- Time-to-first-text measured and logged

### M2 — TTS baseline (offline) + streaming playback

**Outcome**: generate and play speech quickly; can interrupt.

- Install and validate Piper voice model(s)
- Implement TTS harness:
  - synthesize “Hello world”
  - streaming or chunked playback
  - interrupt support

**Exit criteria**

- Time-to-first-audio measured and logged
- Barge-in stopping works

### M3 — LLM offline inference (fast model) + static prompt

**Outcome**: local LLM responds fast using a static knowledge prompt.

- Choose LLM engine:
  - `llama.cpp` (recommended for maximum control)
  - or Ollama (fast setup; less control)
- Choose a fast 7B GGUF 4-bit model (or smaller if latency is critical)
- Prepare a single large prompt file:
  - Concatenate markdown knowledge into the system prompt
  - Keep within the model’s context window
- Define prompt template:
  - system policy + static knowledge
  - constraints for brevity / safety / offline behavior

**Exit criteria**

- Tokens/sec benchmarked on-device
- LLM produces correct “short answer” outputs for a small eval set
- Static prompt loads quickly at startup

### M4 — End-to-end voice assistant (Phase 1: static prompt)

**Outcome**: speak → assistant answers → speaks back using static knowledge.

- Integrate STT → LLM (static prompt) → TTS pipeline
- Maintain short conversation context
- Ensure error handling:
  - STT failures
  - LLM timeouts
  - TTS failures

**Exit criteria**

- 20 consecutive turns without crash
- Typical full-turn latency within Phase 1 target range

### M5 — Hands-free mode (VAD / wake word)

**Outcome**: always-on assistant with low false triggers.

- Add VAD to segment speech
- Add wake word (simple/fast engine)
- Add fallback to push-to-talk if wake word fails
- Tune thresholds and noise handling

**Exit criteria**

- False activation rate acceptable in your environment
- Stable, low-latency segmentation

### M6 — “Voice-to-action” tools (offline device control)

**Outcome**: assistant can execute local actions safely.

- Add tool layer:
  - GPIO control
  - local scripts
  - home automation hooks
- Add permissions / confirmation rules
- Add structured logging

**Exit criteria**

- Tools execute reliably with a safety confirmation step
- No internet needed

### M7 — Packaging + service mode

**Outcome**: runs on boot as a service, easy to update.

- Provide systemd unit
- Provide configuration file
- Add watchdog / restart strategy

**Exit criteria**

- Reboot → service comes up automatically
- Logs stored persistently

### M8 — Phase 2: RAG + Vector DB (Future)

**Outcome**: assistant can search 100+ markdown docs with low-latency retrieval.

- Choose vector DB optimized for speed on Pi (e.g., SQLite-vec or LanceDB)
- Ingest markdown documents
- Implement retrieval pipeline (top-k chunks)
- Tune retrieval to stay within Phase 2 latency budget

**Exit criteria**

- Retrieval latency <= 150ms
- Answers improve with added documents
- Full-turn latency stays within Phase 2 target range

## Model Strategy

### STT

- Primary: Hailo-supported Whisper pipeline (from `hailo-apps` / their speech recognition app)
- Fallback: `whisper.cpp` (CPU)

### LLM (up to 7B)

- Phase 1: Fast 7B GGUF 4-bit model via `llama.cpp` / Ollama
  - Keep context window modest to preserve latency
  - Static knowledge prompt concatenated into system prompt
- Phase 2: Same LLM, but context includes retrieved chunks from vector DB

### TTS

- Phase 1: Piper voices (offline, fast)
- Future (Phase 3+): Fun character voices (Darth Vader, Homer Simpson, etc.) — home use only

### Vector DB (Phase 2)

- Choose a speed-optimized local DB (e.g., SQLite-vec or LanceDB)
- Goal: retrieval <= 150ms on Pi 5

## Observability & Testing

- Always log per-stage timings:
  - record duration
  - STT latency
  - LLM TTFT + tokens/sec
  - TTS TTFA
  - (Phase 2) RAG retrieval latency
- Keep a small regression suite:
  - 20–50 representative utterances
  - expected intents + short expected responses

## Risks / Open Questions

- Qwen3-TTS on ARM64:
  - likely CPU-only and slow on Pi; not currently a good “latency-first” choice
  - Hailo acceleration would require export/compile to HEF (non-trivial)
- Audio I/O variability:
  - USB microphone selection, ALSA/pipewire config, echo cancellation
- LLM latency drift:
  - larger context, slower quant, thermal throttling
- Static prompt size vs context window:
  - Must fit within the chosen LLM’s context; may need chunking or summarization
- Vector DB performance on Pi (Phase 2):
  - Need to verify retrieval can stay under 150ms with 100+ docs

## Future Fun (Non-Public)

- Character voices (Darth Vader, Homer Simpson, etc.) for home use
  - This is explicitly for fun at home; not for public sharing
  - Can be added after latency targets are met

## References

- **VOICE_ASSISTANT_PLAN.md** — Refined Phase 1 plan, concrete tech stack, and step-by-step installation on the Pi (hailo-apps + Piper + hailo-ollama).
- **HAILO_PI_SETUP.md** — Pi 5 + Hailo HAT: hailo-ollama (LLM on Hailo-10H), Hailo voice options (STT/TTS/VAD), hailo-apps voice assistant and speech recognition.
- Hailo apps (voice assistant / speech recognition): https://github.com/hailo-ai/hailo-apps
- Hailo model zoo (HEF compilation pipeline): https://github.com/hailo-ai/hailo_model_zoo
- Qwen3-TTS repository (CUDA-oriented TTS): https://github.com/QwenLM/Qwen3-TTS
