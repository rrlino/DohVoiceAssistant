#!/usr/bin/env python3
"""
Voice assistant for Pi: STT (mic) → LLM (hailo-ollama) → TTS → speaker.
Run on the Pi with ReSpeaker Lite or other USB audio device.

Who processes what:
  - Speech-to-text (your voice → text): faster-whisper or whisper.cpp on Pi CPU
  - Text generation (your prompt → assistant reply): hailo-ollama on port 8000, running on the Hailo-10H
    accelerator (qwen2:1.5b). So the "thinking" and reply text are produced by the Hailo HAT.
  - Text-to-speech (reply text → audio): Sherpa-ONNX VITS (NEON-optimized) or Piper TTS on Pi CPU.

Usage:
  # Threaded mode (recommended): continuous conversation with Silero VAD
  python3 voice_assistant_pi.py --threaded --tts sherpa

  # Voice input (full voice assistant)
  python3 voice_assistant_pi.py --voice
  python3 voice_assistant_pi.py --voice --wake  # Wait for wake word "assistant"

  # Text input modes
  echo "What is the weather?" | python3 voice_assistant_pi.py
  python3 voice_assistant_pi.py   # prompts for input each time
  python3 voice_assistant_pi.py --once "Hello"
"""
import argparse
import gc
import json
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:8000")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2:1.5b")

# TTS: "pyttsx3" (espeak), "piper" (smoother), "sherpa" (fast, NEON-optimized), or "supertonic" (highest quality)
TTS_ENGINE = os.environ.get("TTS_ENGINE", "sherpa")
PIPER_MODEL_DIR = os.environ.get("PIPER_MODEL_DIR", os.path.expanduser("~/piper_models"))
# Medium quality = less robotic than "low". High = most natural: en_US-ryan-high, en_US-amy-high (larger download)
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-amy-medium")
# Pacing: 1.0 = normal; < 1 = faster (e.g. 0.9 = ~10% faster, 0.85 = snappier). Default 0.9 for quicker replies.
PIPER_LENGTH_SCALE = os.environ.get("PIPER_LENGTH_SCALE", "0.9")
PIPER_SENTENCE_SILENCE = os.environ.get("PIPER_SENTENCE_SILENCE", "0.1")  # seconds after each sentence; lower = less pause
PIPER_NOISE_SCALE = os.environ.get("PIPER_NOISE_SCALE", "0.7")   # slight variation = less robotic
PIPER_NOISE_W = os.environ.get("PIPER_NOISE_W", "0.85")
# Piper standalone binary (from https://github.com/rhasspy/piper/releases 2023.11.14-2, piper_linux_aarch64.tar.gz)
PIPER_BIN = os.environ.get("PIPER_BIN", os.path.expanduser("~/piper/piper"))
PIPER_ESPEAK_DATA = os.environ.get("PIPER_ESPEAK_DATA", os.path.expanduser("~/piper/espeak-ng-data"))
PIPER_LD_LIBRARY_PATH = os.environ.get("PIPER_LD_LIBRARY_PATH", os.path.expanduser("~/piper"))

# Sherpa-ONNX TTS settings (VITS models, NEON-optimized for Pi 5)
SHERPA_TTS_MODEL = os.environ.get("SHERPA_TTS_MODEL", os.path.expanduser("~/tts-models/vits-piper-en_US-joe-medium"))
SHERPA_TTS_THREADS = int(os.environ.get("SHERPA_TTS_THREADS", "4"))  # Pi 5 has 4 cores
SHERPA_TTS_SPEAKER = int(os.environ.get("SHERPA_TTS_SPEAKER", "0"))  # Speaker ID for multi-speaker models
SHERPA_TTS_SPEED = float(os.environ.get("SHERPA_TTS_SPEED", "1.0"))  # Speech speed (1.0 = normal)

# Supertonic TTS settings
SUPERTONIC_DIR = os.environ.get("SUPERTONIC_DIR", os.path.expanduser("~/supertonic/py"))
SUPERTONIC_VOICE = os.environ.get("SUPERTONIC_VOICE", "M1")  # Options: M1, M2, F1, F2
SUPERTONIC_VENV = os.environ.get("SUPERTONIC_VENV", None)  # Path to venv, or None to use system Python

# STT: "faster-whisper" (recommended), "whisper.cpp", or "whisper" (openai)
STT_ENGINE = os.environ.get("STT_ENGINE", "faster-whisper")
STT_MODEL = os.environ.get("STT_MODEL", "base.en")  # tiny.en (fast), base.en (balanced), small.en (accurate but slow)
WHISPER_CPP_BIN = os.environ.get("WHISPER_CPP_BIN", os.path.expanduser("~/whisper.cpp/main"))
WHISPER_CPP_MODEL = os.environ.get("WHISPER_CPP_MODEL", os.path.expanduser("~/whisper.cpp/models/ggml-tiny.en.bin"))

# Audio input settings
AUDIO_SAMPLE_RATE = int(os.environ.get("AUDIO_SAMPLE_RATE", "16000"))
AUDIO_CHANNELS = int(os.environ.get("AUDIO_CHANNELS", "1"))
VAD_SILENCE_MS = int(os.environ.get("VAD_SILENCE_MS", "1000"))  # Silence duration to stop recording
VAD_THRESHOLD = float(os.environ.get("VAD_THRESHOLD", "0.5"))  # Voice activity threshold (0-1)

# Resource guardrails
MAX_MEMORY_PERCENT = int(os.environ.get("MAX_MEMORY_PERCENT", "85"))  # Warn at this % memory usage
CRITICAL_MEMORY_PERCENT = int(os.environ.get("CRITICAL_MEMORY_PERCENT", "95"))  # Force cleanup at this %
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))  # Timeout for LLM requests (seconds)
TTS_TIMEOUT = int(os.environ.get("TTS_TIMEOUT", "30"))  # Timeout for TTS (seconds)
WATCHDOG_TIMEOUT = int(os.environ.get("WATCHDOG_TIMEOUT", "60"))  # Max seconds between heartbeats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Voice Activity Detection (Silero VAD via sherpa-onnx)
# ============================================================================

# Silero VAD model path - download if not present
SILERO_VAD_MODEL = os.environ.get(
    "SILERO_VAD_MODEL",
    os.path.expanduser("~/sherpa_models/silero_vad.onnx")
)


# ============================================================================
# Resource Monitoring and Guardrails
# ============================================================================

class Watchdog:
    """Thread health monitor - tracks heartbeats to detect hung threads."""

    def __init__(self, timeout_seconds: int = WATCHDOG_TIMEOUT):
        self.last_heartbeat = time.time()
        self.timeout = timeout_seconds
        self._lock = threading.Lock()

    def heartbeat(self):
        """Record a heartbeat to indicate thread is alive."""
        with self._lock:
            self.last_heartbeat = time.time()

    def is_healthy(self) -> bool:
        """Check if thread has heartbeated recently."""
        with self._lock:
            return time.time() - self.last_heartbeat < self.timeout

    def time_since_heartbeat(self) -> float:
        """Return seconds since last heartbeat."""
        with self._lock:
            return time.time() - self.last_heartbeat


def check_memory() -> tuple[int, int]:
    """
    Check current memory usage.

    Returns:
        (used_percent, available_mb)
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.percent, mem.available // (1024 * 1024)
    except ImportError:
        # psutil not installed, return safe values
        return 0, 4096


def emergency_cleanup() -> None:
    """Force garbage collection and clear caches to free memory."""
    logger.warning("[Resource] Performing emergency cleanup")
    gc.collect()
    # Clear any module-level caches if possible
    # Note: whisper model cache is in processor thread, cleared separately


def log_resource_status(component: str = "") -> None:
    """Log current resource usage for debugging."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        prefix = f"[{component}] " if component else ""
        logger.info(f"{prefix}Memory: {mem.percent}% used ({mem.available // (1024*1024)}MB available), CPU: {cpu}%")
    except ImportError:
        pass


class VoiceActivityDetector:
    """Silero VAD using sherpa-onnx for accurate speech detection."""

    def __init__(self, sample_rate: int = 16000):
        try:
            import sherpa_onnx
        except ImportError:
            raise ImportError("pip install sherpa-onnx")

        if not os.path.isfile(SILERO_VAD_MODEL):
            raise FileNotFoundError(
                f"Silero VAD model not found at {SILERO_VAD_MODEL}. "
                f"Download with: curl -L -o {SILERO_VAD_MODEL} "
                "'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx'"
            )

        self.sample_rate = sample_rate
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = SILERO_VAD_MODEL
        config.silero_vad.min_silence_duration = 0.5  # Seconds of silence to end speech
        config.silero_vad.min_speech_duration = 0.25  # Minimum speech length to trigger
        config.sample_rate = sample_rate
        # Buffer size in seconds - how much audio to buffer before processing
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)

    def process(self, samples):
        """
        Process audio samples and return complete speech segment if detected.

        Args:
            samples: Float32 audio samples normalized to [-1, 1]

        Returns:
            Speech segment as float32 numpy array, or None if no complete speech yet
        """
        self.vad.accept_waveform(samples)
        if not self.vad.empty():
            segment = self.vad.front
            self.vad.pop()
            return segment.samples
        return None

    def reset(self):
        """Reset VAD state for fresh start."""
        self.vad.flush()
        while not self.vad.empty():
            self.vad.pop()


# ============================================================================
# Threaded Voice Assistant
# ============================================================================

def listener_thread(audio_queue: queue.Queue, stop_event: threading.Event, processing_event: threading.Event, sample_rate: int = 16000):
    """
    Thread 1: Continuously listen for speech using Silero VAD.

    Records audio in chunks, detects speech via VAD, and puts complete
    speech segments into the audio queue for processing.

    Skips detection when processing_event is set (TTS is playing).
    """
    import numpy as np

    watchdog = Watchdog(timeout_seconds=WATCHDOG_TIMEOUT)

    try:
        vad = VoiceActivityDetector(sample_rate=sample_rate)
    except ImportError as e:
        print(f"[Listener] Failed to init VAD: {e}", file=sys.stderr)
        return

    chunk_duration = 0.1  # 100ms chunks
    chunk_size = int(sample_rate * chunk_duration)  # samples per chunk
    bytes_per_chunk = chunk_size * 2  # 16-bit = 2 bytes per sample

    # Start recording from default microphone
    cmd = [
        "parecord", "--device=@DEFAULT_SOURCE@", "--raw",
        f"--rate={sample_rate}", "--channels=1", "--format=s16le"
    ]

    proc = None
    memory_check_counter = 0
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        print("[Listener] Listening... (speak to interact)", file=sys.stderr, flush=True)

        while not stop_event.is_set():
            watchdog.heartbeat()

            chunk = proc.stdout.read(bytes_per_chunk)
            if not chunk or len(chunk) < bytes_per_chunk:
                continue

            # Periodic memory check (every ~50 chunks = 5 seconds)
            memory_check_counter += 1
            if memory_check_counter >= 50:
                memory_check_counter = 0
                mem_percent, _ = check_memory()
                if mem_percent >= CRITICAL_MEMORY_PERCENT:
                    logger.warning(f"[Listener] Critical memory: {mem_percent}%, triggering cleanup")
                    emergency_cleanup()
                elif mem_percent >= MAX_MEMORY_PERCENT:
                    logger.warning(f"[Listener] High memory: {mem_percent}%")

            # Skip VAD processing while TTS is playing (processing_event set)
            if processing_event.is_set():
                vad.reset()  # Clear VAD buffer to avoid stale audio
                continue

            # Convert to float32 normalized to [-1, 1]
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0

            # Process through VAD
            speech = vad.process(samples)
            if speech is not None:
                duration = len(speech) / sample_rate
                print(f"[Listener] Detected {duration:.1f}s speech segment", file=sys.stderr, flush=True)

                # Put in queue (non-blocking, drop if full to avoid backlog)
                try:
                    audio_queue.put_nowait(speech)
                except queue.Full:
                    print("[Listener] Queue full, dropping segment", file=sys.stderr)

    except Exception as e:
        print(f"[Listener] Error: {e}", file=sys.stderr)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


def processor_thread(audio_queue: queue.Queue, stop_event: threading.Event, processing_event: threading.Event, args):
    """
    Thread 2: Process speech segments through STT → LLM → TTS pipeline.

    Gets audio from queue, transcribes, generates LLM response, and speaks.
    Sets processing_event while processing to prevent listener from detecting TTS audio.
    """
    import numpy as np

    watchdog = Watchdog(timeout_seconds=WATCHDOG_TIMEOUT)

    # Lazy-load whisper model (only when first audio arrives)
    whisper_model = None

    def get_whisper_model():
        nonlocal whisper_model
        if whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                print("[Processor] Loading Whisper model...", file=sys.stderr, flush=True)
                whisper_model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
            except ImportError:
                sys.exit("pip install faster-whisper")
        return whisper_model

    while not stop_event.is_set():
        watchdog.heartbeat()

        try:
            audio = audio_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        # Signal that we're processing (listener will skip VAD detection)
        processing_event.set()

        try:
            # Check memory before processing
            mem_percent, mem_available = check_memory()
            if mem_percent >= CRITICAL_MEMORY_PERCENT:
                logger.warning(f"[Processor] Critical memory before processing: {mem_percent}%")
                emergency_cleanup()
                # Force reload of whisper model if needed
                whisper_model = None
            elif mem_percent >= MAX_MEMORY_PERCENT:
                logger.warning(f"[Processor] High memory before processing: {mem_percent}%")

            # Transcribe audio
            print("[Processor] Transcribing...", file=sys.stderr, flush=True)
            model = get_whisper_model()

            # faster-whisper expects a file path or file-like object
            # Save audio to temp WAV file for reliable transcription
            temp_wav = tempfile.mktemp(suffix=".wav", prefix="vad_")
            text = ""
            try:
                # Convert to numpy array if needed (sherpa-onnx returns list)
                audio_array = np.array(audio, dtype=np.float32)
                # Convert float32 back to int16 for WAV
                audio_int16 = (audio_array * 32768).astype(np.int16)
                with wave.open(temp_wav, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio_int16.tobytes())

                segments, _ = model.transcribe(temp_wav, beam_size=5)
                text = " ".join(s.text.strip() for s in segments).strip()
            finally:
                if os.path.isfile(temp_wav):
                    os.unlink(temp_wav)

            if not text:
                print("[Processor] No speech detected in segment", file=sys.stderr)
                continue

            print(f"You: {text}", flush=True)

            # Check for exit commands
            if any(w in text.lower() for w in ["goodbye", "bye", "exit", "quit", "stop listening"]):
                print("Goodbye!", flush=True)
                speak("Goodbye!", args.tts)
                stop_event.set()
                break

            # Check for voice commands
            is_cmd, cmd_response = handle_voice_command(text)
            if is_cmd:
                print(f"[Command: {cmd_response}]", file=sys.stderr)
                speak(cmd_response, args.tts)
                continue

            # Send to LLM
            print("Thinking...", file=sys.stderr, flush=True)
            print("Assistant:", end="", flush=True)

            # Stream LLM response and speak sentence by sentence
            buffer = ""
            try:
                for chunk in call_llm_stream(text, args.host, timeout=LLM_TIMEOUT):
                    watchdog.heartbeat()  # Keep heartbeat during streaming
                    print(chunk, end="", flush=True)
                    buffer += chunk
                    sentences = _split_sentences(buffer)
                    if len(sentences) > 1:
                        to_speak = " ".join(sentences[:-1])
                        speak(to_speak, args.tts, timeout=TTS_TIMEOUT)
                        buffer = sentences[-1]
                print(flush=True)
                if buffer.strip():
                    speak(buffer.strip(), args.tts, timeout=TTS_TIMEOUT)
            except Exception as e:
                print(f"\n[Processor] LLM error: {e}", file=sys.stderr)
                # Fallback: non-streaming
                try:
                    response = call_llm(text, args.host, timeout=LLM_TIMEOUT)
                    print(f"Assistant: {response}")
                    if response:
                        speak(response, args.tts, timeout=TTS_TIMEOUT)
                except Exception as e2:
                    print(f"[Processor] Fallback LLM also failed: {e2}", file=sys.stderr)

            # Log resource status after each turn
            log_resource_status("Processor")

            print()  # Blank line between turns
        finally:
            # Always clear processing flag when done
            processing_event.clear()


def run_threaded_assistant(args):
    """Run the 2-thread voice assistant."""
    audio_queue = queue.Queue(maxsize=3)  # Limit queue to avoid backlog
    stop_event = threading.Event()
    processing_event = threading.Event()  # Set when processing to mute listener

    listener = threading.Thread(
        target=listener_thread,
        args=(audio_queue, stop_event, processing_event, AUDIO_SAMPLE_RATE),
        name="ListenerThread"
    )
    processor = threading.Thread(
        target=processor_thread,
        args=(audio_queue, stop_event, processing_event, args),
        name="ProcessorThread"
    )

    listener.daemon = True
    processor.daemon = True

    listener.start()
    processor.start()

    print("\nThreaded voice assistant running. Say 'goodbye' or 'exit' to quit.\n")

    # Health monitoring loop
    last_health_log = time.time()

    try:
        while processor.is_alive() and listener.is_alive():
            # Periodic health logging (every 30 seconds)
            if time.time() - last_health_log > 30:
                log_resource_status("Health")
                last_health_log = time.time()

            # Quick sleep to avoid busy waiting
            time.sleep(0.5)

        # One of the threads died unexpectedly
        if not processor.is_alive():
            logger.error("[Health] Processor thread died unexpectedly")
        if not listener.is_alive():
            logger.error("[Health] Listener thread died unexpectedly")

    except KeyboardInterrupt:
        print("\n[Interrupted]", file=sys.stderr)
    finally:
        stop_event.set()
        listener.join(timeout=2)
        processor.join(timeout=2)


# ============================================================================
# Speech-to-Text (STT) Functions
# ============================================================================

def record_audio(duration: float = None, output_file: str = None, vad: bool = True) -> str:
    """
    Record audio from default microphone.

    Args:
        duration: Recording duration in seconds. If None, use VAD to auto-stop.
        output_file: Path to save WAV file. If None, creates temp file.
        vad: Use Voice Activity Detection to auto-stop on silence.

    Returns:
        Path to recorded WAV file.
    """
    if output_file is None:
        fd, output_file = tempfile.mkstemp(suffix=".wav", prefix="stt_")
        os.close(fd)

    # Try PulseAudio first, fall back to ALSA
    if duration:
        # Fixed duration recording
        cmd = [
            "parecord", "--device=@DEFAULT_SOURCE@",
            "--file-format=wav", "--rate=16000", "--channels=1",
            "--format=s16le",
            output_file
        ]
        try:
            subprocess.run(cmd, timeout=duration + 2)
            # parecord needs to be stopped - use timeout approach
        except subprocess.TimeoutExpired:
            pass
    elif vad:
        # VAD-based recording: record in chunks and detect silence
        return _record_with_vad(output_file)
    else:
        # Continuous recording (user must Ctrl+C)
        cmd = [
            "parecord", "--device=@DEFAULT_SOURCE@",
            "--file-format=wav", "--rate=16000", "--channels=1",
            "--format=s16le",
            output_file
        ]
        print("Recording... (Ctrl+C to stop)", file=sys.stderr)
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass

    return output_file


def _record_with_vad(output_file: str) -> str:
    """
    Record audio with Voice Activity Detection.
    Stops recording after VAD_SILENCE_MS of silence.
    """
    try:
        import webrtcvad
    except ImportError:
        print("webrtcvad not installed, using fixed 5-second recording", file=sys.stderr)
        return record_audio(duration=5, output_file=output_file, vad=False)

    vad = webrtcvad.Vad(2)  # Aggressiveness mode (0-3)
    frame_duration = 30  # ms
    sample_rate = 16000
    frame_size = int(sample_rate * frame_duration / 1000) * 2  # 2 bytes per sample

    # Start recording
    cmd = ["parecord", "--device=@DEFAULT_SOURCE@", "--raw", "--rate=16000",
           "--channels=1", "--format=s16le"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    frames = []
    silence_frames = 0
    max_silence_frames = int(VAD_SILENCE_MS / frame_duration)
    min_speech_frames = int(300 / frame_duration)  # Minimum 300ms of speech
    speech_frames = 0
    recording = True

    print("Listening... (speak now)", file=sys.stderr, flush=True)

    try:
        while recording:
            frame = proc.stdout.read(frame_size)
            if len(frame) < frame_size:
                break

            is_speech = vad.is_speech(frame, sample_rate)

            if is_speech:
                frames.append(frame)
                silence_frames = 0
                speech_frames += 1
            else:
                if speech_frames > 0:  # Only count silence after speech started
                    frames.append(frame)
                    silence_frames += 1

                if speech_frames >= min_speech_frames and silence_frames >= max_silence_frames:
                    recording = False

        proc.terminate()
        proc.wait(timeout=2)
    except Exception as e:
        proc.terminate()
        raise e

    # Write WAV file
    with wave.open(output_file, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))

    return output_file


def stt_faster_whisper(audio_file: str) -> str:
    """
    Transcribe audio using faster-whisper (CTranslate2 backend).
    Fast and efficient, recommended for Raspberry Pi.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("pip install faster-whisper")

    # Use int8 quantization for speed on CPU
    model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")

    segments, info = model.transcribe(audio_file, beam_size=5)
    text = " ".join(segment.text.strip() for segment in segments)

    return text.strip()


def stt_whisper_cpp(audio_file: str) -> str:
    """
    Transcribe audio using whisper.cpp binary.
    Very fast C++ implementation.
    """
    if not os.path.isfile(WHISPER_CPP_BIN):
        print(f"whisper.cpp not found at {WHISPER_CPP_BIN}", file=sys.stderr)
        return ""

    if not os.path.isfile(WHISPER_CPP_MODEL):
        print(f"whisper.cpp model not found at {WHISPER_CPP_MODEL}", file=sys.stderr)
        return ""

    cmd = [
        WHISPER_CPP_BIN,
        "-m", WHISPER_CPP_MODEL,
        "-f", audio_file,
        "-nt",  # No timestamps
        "--output-txt",  # Output to txt file
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # whisper.cpp outputs to audio_file.txt
    txt_file = audio_file + ".txt"
    if os.path.isfile(txt_file):
        with open(txt_file, "r") as f:
            text = f.read().strip()
        os.unlink(txt_file)
        return text

    # Fallback: parse from stdout
    lines = result.stdout.strip().split("\n")
    text_lines = []
    for line in lines:
        if "]" in line:
            text_lines.append(line.split("]", 1)[-1].strip())

    return " ".join(text_lines).strip()


def stt_openai_whisper(audio_file: str) -> str:
    """
    Transcribe audio using OpenAI's whisper Python package.
    Slower than faster-whisper, use only if faster-whisper is unavailable.
    """
    try:
        import whisper
    except ImportError:
        sys.exit("pip install openai-whisper")

    model = whisper.load_model(STT_MODEL.replace(".en", ""))  # whisper uses different model names
    result = model.transcribe(audio_file)

    return result["text"].strip()


def transcribe(audio_file: str, engine: str = None) -> str:
    """
    Transcribe audio file to text using specified STT engine.

    Args:
        audio_file: Path to WAV audio file.
        engine: STT engine to use. If None, uses STT_ENGINE env var.

    Returns:
        Transcribed text.
    """
    engine = engine or STT_ENGINE

    if engine == "whisper.cpp":
        return stt_whisper_cpp(audio_file)
    elif engine == "whisper":
        return stt_openai_whisper(audio_file)
    else:  # faster-whisper (default)
        return stt_faster_whisper(audio_file)


def listen(engine: str = None) -> str:
    """
    Record audio from microphone and transcribe it.
    Convenience function combining record_audio + transcribe.

    Returns:
        Transcribed text from microphone.
    """
    audio_file = record_audio(vad=True)
    try:
        text = transcribe(audio_file, engine)
    finally:
        if os.path.isfile(audio_file):
            os.unlink(audio_file)

    return text


# ============================================================================
# LLM Functions
# ============================================================================

def call_llm(prompt: str, host: str = OLLAMA_HOST, timeout: int = LLM_TIMEOUT) -> str:
    try:
        import requests
    except ImportError:
        sys.exit("pip install requests")
    payload = {"model": MODEL, "prompt": prompt, "stream": False}
    r = requests.post(
        f"{host}/api/generate",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()


def call_llm_stream(prompt: str, host: str = OLLAMA_HOST, timeout: int = LLM_TIMEOUT):
    """Yield response chunks as they arrive (Ollama NDJSON stream)."""
    try:
        import requests
    except ImportError:
        sys.exit("pip install requests")
    payload = {"model": MODEL, "prompt": prompt, "stream": True}
    r = requests.post(
        f"{host}/api/generate",
        json=payload,
        headers={"Content-Type": "application/json"},
        stream=True,
        timeout=timeout,
    )
    r.raise_for_status()
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            obj = json.loads(line)
            chunk = obj.get("response", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break
        except json.JSONDecodeError:
            continue


def _split_sentences(text: str):
    """Split on sentence boundaries (., !, ?) keeping delimiters; return list of sentences."""
    # Split after . ! ? when followed by space or end
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def tts_pyttsx3(text: str) -> None:
    import pyttsx3
    e = pyttsx3.init()
    # Slightly slower rate for smoother sound (default often 200 wpm)
    e.setProperty("rate", 150)
    e.say(text)
    e.runAndWait()


def tts_piper(text: str, timeout: int = TTS_TIMEOUT) -> None:
    """Use Piper standalone binary; stream output to paplay so playback starts as soon as first chunks are ready."""
    model_path = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx")
    config_path = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx.json")
    if not os.path.isfile(model_path) or not os.path.isfile(PIPER_BIN):
        print("Piper model or binary not found, using pyttsx3.", file=sys.stderr)
        tts_pyttsx3(text)
        return
    piper_dir = os.path.dirname(PIPER_BIN)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = os.path.pathsep.join([PIPER_LD_LIBRARY_PATH, env.get("LD_LIBRARY_PATH", "")])
    cmd = [
        PIPER_BIN,
        "--model", model_path,
        "--config", config_path,
        "--output_raw",
        "--espeak_data", PIPER_ESPEAK_DATA,
        "--length_scale", PIPER_LENGTH_SCALE,
        "--sentence_silence", PIPER_SENTENCE_SILENCE,
        "--noise_scale", PIPER_NOISE_SCALE,
        "--noise_w", PIPER_NOISE_W,
    ]
    try:
        piper_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=piper_dir,
        )
        paplay_proc = subprocess.Popen(
            ["paplay", "--raw", "--format=s16le", "--rate=22050", "--channels=1"],
            stdin=piper_proc.stdout,
            stderr=subprocess.DEVNULL,
        )
        piper_proc.stdout.close()
        piper_proc.stdin.write(text.encode("utf-8"))
        piper_proc.stdin.close()
        piper_proc.wait(timeout=timeout)
        paplay_proc.wait(timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Piper failed ({e}), using pyttsx3.", file=sys.stderr)
        try:
            piper_proc.kill()
            paplay_proc.kill()
        except Exception:
            pass
        tts_pyttsx3(text)


# Global Sherpa-ONNX TTS instance (lazy-loaded)
_SHERPA_TTS = None


def _get_sherpa_tts():
    """Lazy-load and cache Sherpa-ONNX OfflineTts instance."""
    global _SHERPA_TTS
    if _SHERPA_TTS is not None:
        return _SHERPA_TTS
    try:
        import sherpa_onnx
    except ImportError:
        return None
    if not os.path.isdir(SHERPA_TTS_MODEL):
        return None

    # Find model .onnx file (single-speaker piper or multi-speaker VCTK)
    onnx_file = None
    for f in os.listdir(SHERPA_TTS_MODEL):
        if f.endswith(".onnx") and "int8" not in f:
            onnx_file = os.path.join(SHERPA_TTS_MODEL, f)
            break
    if not onnx_file:
        return None

    tokens_file = os.path.join(SHERPA_TTS_MODEL, "tokens.txt")
    data_dir = os.path.join(SHERPA_TTS_MODEL, "espeak-ng-data")
    lexicon_file = os.path.join(SHERPA_TTS_MODEL, "lexicon.txt")

    config = sherpa_onnx.OfflineTtsConfig()
    config.model.vits.model = onnx_file
    config.model.vits.tokens = tokens_file
    # Prefer system espeak-ng-data — bundled version often mismatches sherpa-onnx
    # version, causing a C++ error that doesn't raise a Python exception
    sys_data = "/usr/lib/aarch64-linux-gnu/espeak-ng-data"
    if os.path.isdir(sys_data):
        config.model.vits.data_dir = sys_data
    elif os.path.isdir(data_dir):
        config.model.vits.data_dir = data_dir
    if os.path.isfile(lexicon_file):
        config.model.vits.lexicon = lexicon_file
    config.model.num_threads = SHERPA_TTS_THREADS
    config.model.debug = False
    config.model.provider = "cpu"

    _SHERPA_TTS = sherpa_onnx.OfflineTts(config)
    logger.info(f"Sherpa-ONNX TTS loaded: {_SHERPA_TTS.sample_rate}Hz, {SHERPA_TTS_THREADS} threads, model={os.path.basename(onnx_file)}")
    return _SHERPA_TTS


def tts_sherpa(text: str, timeout: int = TTS_TIMEOUT) -> None:
    """Use Sherpa-ONNX VITS TTS — NEON-optimized, targets RTF < 0.1 on Pi 5."""
    tts = _get_sherpa_tts()
    if tts is None:
        logger.warning("Sherpa-ONNX TTS not available, falling back to Piper")
        tts_piper(text, timeout=timeout)
        return
    try:
        audio = tts.generate(text, sid=SHERPA_TTS_SPEAKER, speed=SHERPA_TTS_SPEED)
        if not audio.samples:
            logger.warning("Sherpa-ONNX TTS produced no audio, falling back to Piper")
            tts_piper(text, timeout=timeout)
            return
        # Convert float samples to 16-bit PCM for paplay
        import array
        import struct
        samples = audio.samples
        if hasattr(samples, 'tobytes'):
            # numpy array — convert directly
            import numpy as np
            pcm_data = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        else:
            # list of floats — pack manually
            pcm_data = struct.pack(f'<{len(samples)}h',
                                   *[int(max(-1.0, min(1.0, s)) * 32767) for s in samples])
        # Play via aplay (ALSA) or paplay (PulseAudio) — raw PCM s16le
        player = "paplay" if os.path.isfile("/usr/bin/paplay") else "aplay"
        if player == "aplay":
            cmd = [player, "-q", "-t", "raw", "-f", "S16_LE", "-r", str(tts.sample_rate), "-c", "1"]
        else:
            cmd = [player, "--raw", f"--rate={tts.sample_rate}", "--format=s16le", "--channels=1"]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(input=pcm_data, timeout=timeout)
    except Exception as e:
        logger.warning(f"Sherpa-ONNX TTS failed ({e}), falling back to Piper")
        tts_piper(text, timeout=timeout)


# Global Supertonic instance (lazy-loaded)
_SUPERTONIC_TTS = None
_SUPERTONIC_STYLE = None


def tts_supertonic(text: str, timeout: int = TTS_TIMEOUT) -> None:
    """Use Supertonic ONNX TTS - higher quality at 44100Hz, optimized for speed.

    This runs Supertonic in a subprocess using its virtualenv Python, since
    Supertonic requires onnxruntime, soundfile, librosa which may not be in system Python.
    """
    if not os.path.isdir(SUPERTONIC_DIR):
        print("Supertonic not found, using piper.", file=sys.stderr)
        tts_piper(text, timeout=timeout)
        return

    # Determine the Python interpreter to use
    venv_python = os.path.join(SUPERTONIC_DIR, ".venv", "bin", "python")
    if not os.path.isfile(venv_python):
        venv_python = sys.executable  # Fall back to system Python

    # Escape text for shell
    escaped_text = text.replace("\\", "\\\\").replace("'", "'\\''")

    # Create a script to generate audio and output to stdout
    script = f'''
import sys
import os
import tempfile
os.chdir("{SUPERTONIC_DIR}")
sys.path.insert(0, "{SUPERTONIC_DIR}")

import numpy as np
import soundfile as sf
from helper import load_text_to_speech, load_voice_style

# Load model (cached globally to speed up subsequent calls)
if not hasattr(sys, '_supertonic_tts'):
    sys._supertonic_tts = load_text_to_speech("assets/onnx", use_gpu=False)
    voice_style_path = os.path.join("{SUPERTONIC_DIR}", "assets", "voice_styles", "{SUPERTONIC_VOICE}.json")
    sys._supertonic_style = load_voice_style([voice_style_path])

tts = sys._supertonic_tts
style = sys._supertonic_style

# Generate audio with optimized settings
audio, dur = tts("{escaped_text}", "en", style, total_step=3, speed=1.2)

# Output to temp file
import tempfile
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
    sf.write(tmp.name, audio[0], 44100)
    print(tmp.name)
'''

    try:
        # Run the script in Supertonic's venv
        result = subprocess.run(
            [venv_python, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SUPERTONIC_DIR,
        )

        if result.returncode != 0:
            print(f"Supertonic failed: {result.stderr[:100]}, using piper.", file=sys.stderr)
            tts_piper(text, timeout=timeout)
            return

        # Get the temp file path (last non-empty line of stdout)
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        wav_path = lines[-1] if lines else None
        if wav_path and wav_path.endswith('.wav') and os.path.exists(wav_path):
            try:
                subprocess.run(["paplay", wav_path], check=True, timeout=timeout)
            finally:
                os.unlink(wav_path)
        else:
            print("Supertonic failed to generate audio, using piper.", file=sys.stderr)
            tts_piper(text, timeout=timeout)

    except Exception as e:
        print(f"Supertonic failed ({e}), using piper.", file=sys.stderr)
        tts_piper(text, timeout=timeout)


def speak(text: str, engine: str = None, timeout: int = TTS_TIMEOUT) -> None:
    """Speak text using specified or default TTS engine."""
    if not text:
        return
    tts = engine or TTS_ENGINE
    if tts == "supertonic":
        tts_supertonic(text, timeout=timeout)
    elif tts == "sherpa":
        tts_sherpa(text, timeout=timeout)
    elif tts == "piper":
        tts_piper(text, timeout=timeout)
    else:
        tts_pyttsx3(text)


# ============================================================================
# Voice Commands
# ============================================================================

VOICE_COMMANDS = {
    "volume up": lambda: _volume_change(+10),
    "volume down": lambda: _volume_change(-10),
    "louder": lambda: _volume_change(+10),
    "quieter": lambda: _volume_change(-10),
    "softer": lambda: _volume_change(-10),
    "mute": lambda: _volume_set(0),
    "unmute": lambda: _volume_set(50),
    "stop": lambda: _stop_audio(),
    "quiet": lambda: _volume_set(20),
    "max volume": lambda: _volume_set(100),
    "full volume": lambda: _volume_set(100),
}


def _volume_change(delta: int) -> str:
    """Change volume by delta percent."""
    try:
        # Get current volume
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=5
        )
        # Parse: "Volume: front-left: 12345 /  19% / -42.00 dB, ..."
        import re
        match = re.search(r"/\s*(\d+)%/", result.stdout)
        current = int(match.group(1)) if match else 50

        new_vol = max(0, min(100, current + delta))
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{new_vol}%"],
            capture_output=True, timeout=5
        )
        return f"Volume {new_vol} percent"
    except Exception as e:
        return f"Volume change failed: {e}"


def _volume_set(level: int) -> str:
    """Set volume to specific level."""
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
            capture_output=True, timeout=5
        )
        return f"Volume set to {level} percent"
    except Exception as e:
        return f"Volume set failed: {e}"


def _stop_audio() -> str:
    """Stop any playing audio."""
    try:
        subprocess.run(["pactl", "suspend-sink", "@DEFAULT_SINK@", "1"],
                       capture_output=True, timeout=2)
        subprocess.run(["pactl", "suspend-sink", "@DEFAULT_SINK@", "0"],
                       capture_output=True, timeout=2)
        return "Stopped"
    except Exception:
        return "Stop failed"


def handle_voice_command(text: str) -> tuple[bool, str]:
    """
    Check if text is a voice command and execute it.

    Returns:
        (is_command, response): Whether it was a command and the response.
    """
    text_lower = text.lower().strip()

    # Check for exact matches
    for cmd, action in VOICE_COMMANDS.items():
        if cmd in text_lower or text_lower in cmd:
            response = action()
            return True, response

    # Check for "set volume to X" pattern
    import re
    match = re.search(r"(?:set )?volume (?:to )?(\d+)", text_lower)
    if match:
        level = int(match.group(1))
        level = max(0, min(100, level))
        response = _volume_set(level)
        return True, response

    return False, ""


def main():
    ap = argparse.ArgumentParser(description="Voice assistant: STT → LLM → TTS")
    ap.add_argument("--host", default=OLLAMA_HOST, help="Ollama/hailo-ollama base URL")
    ap.add_argument("--model", default=MODEL, help="Model name")
    ap.add_argument("--once", metavar="TEXT", help="Single prompt (no interactive loop)")
    ap.add_argument("--tts", choices=("pyttsx3", "piper", "sherpa", "supertonic"), default=TTS_ENGINE, help="TTS engine")
    ap.add_argument("--stt", choices=("faster-whisper", "whisper.cpp", "whisper"), default=STT_ENGINE, help="STT engine")
    ap.add_argument("--no-speak", action="store_true", help="Print response only, no TTS")
    ap.add_argument("--loop", action="store_true", help="Interactive loop: keep prompting until Ctrl+C")
    ap.add_argument("--voice", action="store_true", help="Voice input mode: use microphone for input")
    ap.add_argument("--wake", action="store_true", help="Wake word mode: listen for 'assistant' before each query (implies --voice)")
    ap.add_argument("--threaded", action="store_true", help="2-thread mode: continuous VAD listening with parallel processing")
    ap.add_argument("--record", metavar="SECONDS", type=float, help="Record audio for N seconds and save to /tmp/recording.wav")
    ap.add_argument("--transcribe", metavar="FILE", help="Transcribe audio file to text (no LLM)")
    ap.add_argument("--read", action="store_true", help="Read-only mode: speak text from stdin, no LLM")
    ap.add_argument("--read-file", metavar="PATH", help="Speak contents of file, no LLM")
    args = ap.parse_args()

    # Wake mode implies voice mode
    if args.wake:
        args.voice = True

    # Read-only TTS: speak text from file or stdin, no LLM
    if args.read_file or args.read:
        text = ""
        if args.read_file:
            path = os.path.expanduser(args.read_file)
            if not os.path.isfile(path):
                print(f"File not found: {path}", file=sys.stderr)
                sys.exit(1)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        text = text.strip()
        if not text:
            sys.exit(0)
        print("Speaking...", file=sys.stderr)
        speak(text, args.tts)
        return

    # Record-only mode: record audio and save to file
    if args.record:
        output_file = "/tmp/recording.wav"
        print(f"Recording for {args.record} seconds...", file=sys.stderr)
        record_audio(duration=args.record, output_file=output_file, vad=False)
        print(f"Saved to {output_file}", file=sys.stderr)
        return

    # Transcribe-only mode: transcribe audio file
    if args.transcribe:
        path = os.path.expanduser(args.transcribe)
        if not os.path.isfile(path):
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)
        print("Transcribing...", file=sys.stderr)
        text = transcribe(path, args.stt)
        print(text)
        return

    def one_turn(prompt: str) -> None:
        if not prompt.strip():
            return
        print("Thinking...")
        if args.no_speak:
            for chunk in call_llm_stream(prompt.strip(), args.host):
                print(chunk, end="", flush=True)
            print()
            return
        # Stream LLM and speak each sentence as soon as it's complete (chunk-by-chunk audio)
        buffer = ""
        print("Assistant:", end="", flush=True)
        try:
            for chunk in call_llm_stream(prompt.strip(), args.host):
                print(chunk, end="", flush=True)
                buffer += chunk
                sentences = _split_sentences(buffer)
                if len(sentences) > 1:
                    to_speak = " ".join(sentences[:-1])
                    speak(to_speak, args.tts)
                    buffer = sentences[-1]
            print(flush=True)
            if buffer.strip():
                speak(buffer.strip(), args.tts)
        except Exception as e:
            print(f"\nStream error: {e}", file=sys.stderr)
            # Fallback: get full response and speak once
            response = call_llm(prompt.strip(), args.host)
            print("Assistant:", response)
            if response:
                speak(response, args.tts)

    if args.once:
        one_turn(args.once)
        return

    # Threaded mode: 2-thread architecture with continuous VAD listening
    # Check before stdin.isatty() so it works over SSH
    if args.threaded:
        print("Threaded voice assistant (continuous listening with Silero VAD).")
        print("Say 'volume up', 'volume down', or ask any question.")
        run_threaded_assistant(args)
        return

    if not sys.stdin.isatty():
        one_turn(sys.stdin.read())
        return

    # Voice input mode
    if args.voice:
        print("Voice assistant (voice input). Press Ctrl+C to quit.")
        print("Say 'volume up', 'volume down', or ask any question.")
        print()

        # Use fixed 5-second recording for SSH compatibility
        record_duration = float(os.environ.get("VOICE_RECORD_SECONDS", "5"))
        print(f"[Recording {record_duration}s per turn]", file=sys.stderr)

        while True:
            try:
                # Record audio (fixed duration for SSH compatibility)
                print(f"[Listening for {record_duration}s...]", file=sys.stderr, flush=True)
                audio_file = tempfile.mktemp(suffix=".wav", prefix="voice_")

                # Use parecord with timeout
                proc = subprocess.Popen(
                    ["parecord", "--device=@DEFAULT_SOURCE@",
                     "--file-format=wav", "--rate=16000", "--channels=1",
                     "--format=s16le", audio_file],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

                # Wait for recording duration
                time.sleep(record_duration)
                proc.terminate()
                proc.wait(timeout=2)

                # Transcribe
                print("[Transcribing...]", file=sys.stderr, flush=True)
                try:
                    prompt = transcribe(audio_file, args.stt)
                finally:
                    if os.path.isfile(audio_file):
                        os.unlink(audio_file)

                if not prompt.strip():
                    print("[No speech detected]", file=sys.stderr)
                    continue

                print(f"You: {prompt}")

                # Check for voice commands first
                is_command, cmd_response = handle_voice_command(prompt)
                if is_command:
                    print(f"[Command: {cmd_response}]", file=sys.stderr)
                    if not args.no_speak:
                        speak(cmd_response, args.tts)
                    print()
                    continue

                # Not a command, send to LLM
                one_turn(prompt)
                print()

            except (EOFError, KeyboardInterrupt):
                print("\n[Exiting]", file=sys.stderr)
                break
            except Exception as e:
                print(f"[Error: {e}]", file=sys.stderr)
                time.sleep(1)

        return

    # Interactive text mode
    print("Voice assistant (text input). Type your message and press Enter. Ctrl+C to quit.")
    if args.loop:
        print("Loop mode: will keep asking for input.")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        one_turn(prompt)
        if not args.loop:
            break


if __name__ == "__main__":
    main()
