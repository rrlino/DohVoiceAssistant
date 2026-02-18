#!/usr/bin/env python3
"""
Compare TTS engines: Piper vs Supertonic on Raspberry Pi 5.

Usage:
    python3 src/benchmark_tts_comparison.py
"""

import os
import subprocess
import sys
import tempfile
import time

# Test texts of varying lengths
TEXTS = {
    "short": "Hello, how are you?",
    "medium": "The quick brown fox jumps over the lazy dog. This is a test of the TTS system.",
    "long": "This morning, I took my dog for a walk in the park. We saw many birds and squirrels. The weather was beautiful with clear blue skies. It was a lovely start to the day.",
}


def get_wav_duration(wav_path: str) -> float:
    """Get duration of a WAV file in seconds by parsing the header."""
    try:
        with open(wav_path, "rb") as f:
            # RIFF header
            riff = f.read(4)
            if riff != b"RIFF":
                return 0
            f.read(4)  # file size
            wave = f.read(4)
            if wave != b"WAVE":
                return 0

            # Find fmt chunk
            while True:
                chunk_id = f.read(4)
                chunk_size = int.from_bytes(f.read(4), "little")
                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    channels = int.from_bytes(fmt_data[2:4], "little")
                    sample_rate = int.from_bytes(fmt_data[4:8], "little")
                    bits_per_sample = int.from_bytes(fmt_data[14:16], "little")
                    break
                else:
                    f.read(chunk_size)

            # Find data chunk
            while True:
                chunk_id = f.read(4)
                chunk_size = int.from_bytes(f.read(4), "little")
                if chunk_id == b"data":
                    bytes_per_sample = bits_per_sample // 8
                    total_samples = chunk_size // (channels * bytes_per_sample)
                    duration = total_samples / sample_rate
                    return duration
                else:
                    f.read(chunk_size)
    except Exception:
        return 0


def benchmark_piper(text: str, iterations: int = 3) -> dict:
    """Benchmark Piper TTS."""
    PIPER_MODEL_DIR = os.environ.get("PIPER_MODEL_DIR", os.path.expanduser("~/piper_models"))
    PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-amy-medium")
    PIPER_BIN = os.environ.get("PIPER_BIN", os.path.expanduser("~/piper/piper"))
    PIPER_ESPEAK_DATA = os.environ.get("PIPER_ESPEAK_DATA", os.path.expanduser("~/piper/espeak-ng-data"))
    PIPER_LD_LIBRARY_PATH = os.environ.get("PIPER_LD_LIBRARY_PATH", os.path.expanduser("~/piper"))

    model_path = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx")
    config_path = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx.json")

    if not os.path.isfile(model_path) or not os.path.isfile(PIPER_BIN):
        return {"error": "Piper not found"}

    times = []
    durations = []

    for _ in range(iterations):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = os.path.pathsep.join([
                PIPER_LD_LIBRARY_PATH,
                env.get("LD_LIBRARY_PATH", "")
            ])

            cmd = [
                PIPER_BIN,
                "--model", model_path,
                "--config", config_path,
                "--output_file", wav_path,
                "--espeak_data", PIPER_ESPEAK_DATA,
            ]

            start = time.perf_counter()
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                env=env,
                cwd=os.path.dirname(PIPER_BIN),
                timeout=60,
            )
            elapsed = time.perf_counter() - start

            if proc.returncode == 0:
                duration = get_wav_duration(wav_path)
                times.append(elapsed)
                durations.append(duration)
        except Exception as e:
            return {"error": str(e)}
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    if not times:
        return {"error": "No successful runs"}

    avg_time = sum(times) / len(times)
    avg_duration = sum(durations) / len(durations)
    rtf = avg_time / avg_duration if avg_duration > 0 else 0

    return {
        "generation_ms": round(avg_time * 1000),
        "audio_duration_s": round(avg_duration, 2),
        "rtf": round(rtf, 3),
        "sample_rate": 22050,
    }


def benchmark_supertonic(text: str, iterations: int = 3) -> dict:
    """Benchmark Supertonic TTS via Python."""
    supertonic_path = os.path.expanduser("~/supertonic/py")

    if not os.path.isdir(supertonic_path):
        return {"error": "Supertonic not found"}

    # Escape text for Python string
    escaped_text = text.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")

    # Create a benchmark script to run in the supertonic venv
    bench_script = '''
import sys
sys.path.insert(0, "''' + supertonic_path + '''")
import os
os.chdir("''' + supertonic_path + '''")
import time
import json
from helper import load_text_to_speech

text = "''' + escaped_text + '''"
iterations = ''' + str(iterations) + '''

# Load model once
tts = load_text_to_speech("assets/onnx", use_gpu=False)

times = []
durations = []

for _ in range(iterations):
    start = time.perf_counter()
    audio, sr = tts.generate(text)
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    durations.append(len(audio) / sr)

if not times:
    print(json.dumps({"error": "No successful runs"}))
else:
    avg_time = sum(times) / len(times)
    avg_duration = sum(durations) / len(durations)
    rtf = avg_time / avg_duration if avg_duration > 0 else 0
    print(json.dumps({
        "generation_ms": round(avg_time * 1000),
        "audio_duration_s": round(avg_duration, 2),
        "rtf": round(rtf, 3),
        "sample_rate": 44100
    }))
'''

    try:
        result = subprocess.run(
            [f"{supertonic_path}/.venv/bin/python", "-c", bench_script],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=supertonic_path,
        )

        if result.returncode != 0:
            return {"error": result.stderr[:200]}

        # Parse JSON output
        import json
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 70)
    print("TTS Engine Comparison: Piper vs Supertonic on Raspberry Pi 5")
    print("=" * 70)
    print()

    for name, text in TEXTS.items():
        print(f"Test: {name} ({len(text)} chars)")
        print(f'Text: "{text[:50]}..."' if len(text) > 50 else f'Text: "{text}"')
        print("-" * 50)

        # Piper
        print("  Piper:     ", end="", flush=True)
        piper_result = benchmark_piper(text)
        if "error" in piper_result:
            print(f"ERROR - {piper_result['error']}")
        else:
            print(f"{piper_result['generation_ms']}ms, {piper_result['audio_duration_s']}s audio, RTF={piper_result['rtf']}")

        # Supertonic
        print("  Supertonic:", end="", flush=True)
        super_result = benchmark_supertonic(text)
        if "error" in super_result:
            print(f"ERROR - {super_result['error']}")
        else:
            print(f"{super_result['generation_ms']}ms, {super_result['audio_duration_s']}s audio, RTF={super_result['rtf']}")

        print()

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()
    print("| Engine     | Quality    | RTF Target | Pros                          |")
    print("|------------|------------|------------|-------------------------------|")
    print("| Piper      | 22050Hz    | ~0.13-0.26 | Fast, many voices, mature     |")
    print("| Supertonic | 44100Hz    | ~0.14      | Higher quality, modern ONNX   |")
    print()


if __name__ == "__main__":
    main()
