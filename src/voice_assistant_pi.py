#!/usr/bin/env python3
"""
Voice assistant for Pi: input (text for now) → LLM (hailo-ollama) → TTS → play on default sink (Lenrue).
Run on the Pi. When a mic is available, STT can be added.

Who processes what:
  - Text generation (your prompt → assistant reply): hailo-ollama on port 8000, running on the Hailo-10H
    accelerator (qwen2:1.5b). So the "thinking" and reply text are produced by the Hailo HAT.
  - Speech (reply text → audio): Piper TTS runs on the Pi's CPU and plays through the default sink (e.g. Lenrue).
    So only the LLM uses Hailo; TTS and audio I/O are on the Pi CPU.

Usage:
  echo "What is the weather?" | python3 voice_assistant_pi.py
  python3 voice_assistant_pi.py   # prompts for input each time
  python3 voice_assistant_pi.py --once "Hello"
"""
import argparse
import json
import os
import re
import subprocess
import sys

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:8000")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2:1.5b")

# TTS: "pyttsx3" (espeak, works everywhere) or "piper" (smoother, needs Piper binary + voice on Pi)
TTS_ENGINE = os.environ.get("TTS_ENGINE", "pyttsx3")  # use "piper" for smoother voice (requires Piper binary at ~/piper)
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


def call_llm(prompt: str, host: str = OLLAMA_HOST) -> str:
    try:
        import requests
    except ImportError:
        sys.exit("pip install requests")
    payload = {"model": MODEL, "prompt": prompt, "stream": False}
    r = requests.post(
        f"{host}/api/generate",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()


def call_llm_stream(prompt: str, host: str = OLLAMA_HOST):
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
        timeout=120,
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


def tts_piper(text: str) -> None:
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
        piper_proc.wait(timeout=60)
        paplay_proc.wait(timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Piper failed ({e}), using pyttsx3.", file=sys.stderr)
        try:
            piper_proc.kill()
            paplay_proc.kill()
        except Exception:
            pass
        tts_pyttsx3(text)


def speak(text: str) -> None:
    if not text:
        return
    if TTS_ENGINE == "piper":
        tts_piper(text)
    else:
        tts_pyttsx3(text)


def main():
    ap = argparse.ArgumentParser(description="Voice assistant: input → LLM → TTS")
    ap.add_argument("--host", default=OLLAMA_HOST, help="Ollama/hailo-ollama base URL")
    ap.add_argument("--model", default=MODEL, help="Model name")
    ap.add_argument("--once", metavar="TEXT", help="Single prompt (no interactive loop)")
    ap.add_argument("--tts", choices=("pyttsx3", "piper"), default=TTS_ENGINE, help="TTS engine")
    ap.add_argument("--no-speak", action="store_true", help="Print response only, no TTS")
    ap.add_argument("--loop", action="store_true", help="Interactive loop: keep prompting until Ctrl+C")
    ap.add_argument("--read", action="store_true", help="Read-only mode: speak text from stdin, no LLM")
    ap.add_argument("--read-file", metavar="PATH", help="Speak contents of file, no LLM")
    args = ap.parse_args()

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
        if args.tts == "piper":
            tts_piper(text)
        else:
            tts_pyttsx3(text)
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
                    if args.tts == "piper":
                        tts_piper(to_speak)
                    else:
                        tts_pyttsx3(to_speak)
                    buffer = sentences[-1]
            print(flush=True)
            if buffer.strip():
                if args.tts == "piper":
                    tts_piper(buffer.strip())
                else:
                    tts_pyttsx3(buffer.strip())
        except Exception as e:
            print(f"\nStream error: {e}", file=sys.stderr)
            # Fallback: get full response and speak once
            response = call_llm(prompt.strip(), args.host)
            print("Assistant:", response)
            if response and args.tts == "piper":
                tts_piper(response)
            elif response:
                tts_pyttsx3(response)

    if args.once:
        one_turn(args.once)
        return
    if not sys.stdin.isatty():
        one_turn(sys.stdin.read())
        return
    # Interactive: prompt for input
    print("Voice assistant (text input for now). Type your message and press Enter. Ctrl+C to quit.")
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
