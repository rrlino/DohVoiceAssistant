#!/usr/bin/env python3
"""
Latency benchmark for voice assistant pipeline.
Measures LLM and TTS performance against roadmap targets.

Usage:
    python3 src/benchmark_latency.py                    # Run default benchmark
    python3 src/benchmark_latency.py --iterations 10    # More iterations
    python3 src/benchmark_latency.py --prompts short    # Only short prompts
    python3 src/benchmark_latency.py --model qwen2.5-instruct:1.5b
    python3 src/benchmark_latency.py --json             # Output as JSON
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time

# Configuration (reuse from voice_assistant_pi.py)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:8000")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2:1.5b")

# TTS configuration
PIPER_MODEL_DIR = os.environ.get("PIPER_MODEL_DIR", os.path.expanduser("~/piper_models"))
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-amy-medium")
PIPER_BIN = os.environ.get("PIPER_BIN", os.path.expanduser("~/piper/piper"))
PIPER_ESPEAK_DATA = os.environ.get("PIPER_ESPEAK_DATA", os.path.expanduser("~/piper/espeak-ng-data"))
PIPER_LD_LIBRARY_PATH = os.environ.get("PIPER_LD_LIBRARY_PATH", os.path.expanduser("~/piper"))

# Test prompts of varying complexity
PROMPTS = {
    "short": "What is 2 plus 2?",
    "medium": "What are the three states of matter? List them briefly.",
    "long": "Explain how a computer works in simple terms. Cover the CPU, memory, and storage.",
}

# Roadmap targets (in milliseconds)
TARGETS = {
    "llm_ttft": 500,      # Time to first token
    "full_turn": 1500,    # Full turn latency (short prompt)
}


def benchmark_llm(prompt: str, host: str, model: str) -> dict:
    """
    Measure LLM latency metrics.

    Returns:
        dict with: ttft_ms, total_ms, token_count, tokens_per_sec, response_text
    """
    try:
        import requests
    except ImportError:
        sys.exit("pip install requests")

    payload = {"model": model, "prompt": prompt, "stream": True}

    start_time = time.perf_counter()
    ttft = None
    token_count = 0
    response_text = ""

    try:
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
                    if ttft is None:
                        ttft = time.perf_counter() - start_time
                    token_count += 1
                    response_text += chunk
                if obj.get("done"):
                    break
            except json.JSONDecodeError:
                continue

        total_time = time.perf_counter() - start_time

        # Estimate tokens (Ollama doesn't always report eval_count accurately in stream mode)
        # Use word count as approximation: ~1.3 tokens per word
        if token_count == 0 and response_text:
            token_count = int(len(response_text.split()) * 1.3)

        tokens_per_sec = token_count / total_time if total_time > 0 else 0

        return {
            "ttft_ms": round(ttft * 1000) if ttft else 0,
            "total_ms": round(total_time * 1000),
            "token_count": token_count,
            "tokens_per_sec": round(tokens_per_sec, 1),
            "response_text": response_text,
        }
    except Exception as e:
        return {
            "ttft_ms": 0,
            "total_ms": 0,
            "token_count": 0,
            "tokens_per_sec": 0,
            "response_text": "",
            "error": str(e),
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
                    # Sample rate at offset 4, bits per sample at offset 14, channels at offset 2
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


def benchmark_tts(text: str) -> dict:
    """
    Measure TTS latency metrics.

    Returns:
        dict with: generation_ms, audio_duration_s, rtf
    """
    if not text:
        return {"generation_ms": 0, "audio_duration_s": 0, "rtf": 0}

    model_path = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx")
    config_path = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx.json")

    if not os.path.isfile(model_path) or not os.path.isfile(PIPER_BIN):
        return {"generation_ms": 0, "audio_duration_s": 0, "rtf": 0, "error": "Piper not found"}

    # Create temp file for WAV output
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

        start_time = time.perf_counter()

        proc = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            capture_output=True,
            env=env,
            cwd=os.path.dirname(PIPER_BIN),
            timeout=60,
        )

        generation_time = time.perf_counter() - start_time

        if proc.returncode != 0:
            return {
                "generation_ms": 0,
                "audio_duration_s": 0,
                "rtf": 0,
                "error": proc.stderr.decode("utf-8", errors="replace"),
            }

        audio_duration = get_wav_duration(wav_path)
        rtf = generation_time / audio_duration if audio_duration > 0 else 0

        return {
            "generation_ms": round(generation_time * 1000),
            "audio_duration_s": round(audio_duration, 2),
            "rtf": round(rtf, 3),
        }
    except Exception as e:
        return {"generation_ms": 0, "audio_duration_s": 0, "rtf": 0, "error": str(e)}
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def run_benchmark(prompts_to_test: list, iterations: int, model: str, host: str) -> dict:
    """Run full benchmark suite."""
    results = {}

    for prompt_name in prompts_to_test:
        if prompt_name not in PROMPTS:
            print(f"Warning: Unknown prompt '{prompt_name}', skipping")
            continue

        prompt = PROMPTS[prompt_name]
        prompt_results = {
            "prompt": prompt,
            "iterations": [],
        }

        llm_ttfts = []
        llm_totals = []
        llm_tps = []
        tts_times = []
        tts_rtfs = []
        full_turns = []

        for i in range(iterations):
            print(f"  Iteration {i+1}/{iterations}...", end="\r", flush=True)

            # Benchmark LLM
            llm_result = benchmark_llm(prompt, host, model)

            if "error" in llm_result:
                print(f"\n  LLM error: {llm_result['error']}")
                continue

            llm_ttfts.append(llm_result["ttft_ms"])
            llm_totals.append(llm_result["total_ms"])
            llm_tps.append(llm_result["tokens_per_sec"])

            # Benchmark TTS with the response
            tts_result = benchmark_tts(llm_result["response_text"])

            if "error" in tts_result and tts_result.get("generation_ms", 0) == 0:
                print(f"\n  TTS error: {tts_result.get('error', 'Unknown')}")
                tts_times.append(0)
                tts_rtfs.append(0)
            else:
                tts_times.append(tts_result["generation_ms"])
                tts_rtfs.append(tts_result["rtf"])

            # Full turn = LLM total + TTS generation
            full_turn = llm_result["total_ms"] + tts_result.get("generation_ms", 0)
            full_turns.append(full_turn)

            prompt_results["iterations"].append({
                "llm": llm_result,
                "tts": tts_result,
                "full_turn_ms": full_turn,
            })

        # Calculate statistics
        def stats(values):
            if not values:
                return {"mean": 0, "min": 0, "max": 0, "stdev": 0}
            return {
                "mean": round(statistics.mean(values)),
                "min": round(min(values)),
                "max": round(max(values)),
                "stdev": round(statistics.stdev(values), 1) if len(values) > 1 else 0,
            }

        prompt_results["stats"] = {
            "llm_ttft_ms": stats(llm_ttfts),
            "llm_total_ms": stats(llm_totals),
            "llm_tokens_per_sec": stats(llm_tps),
            "tts_generation_ms": stats(tts_times),
            "tts_rtf": {
                "mean": round(statistics.mean(tts_rtfs), 3) if tts_rtfs else 0,
                "min": round(min(tts_rtfs), 3) if tts_rtfs else 0,
                "max": round(max(tts_rtfs), 3) if tts_rtfs else 0,
            },
            "full_turn_ms": stats(full_turns),
        }

        results[prompt_name] = prompt_results

    return results


def print_results(results: dict, model: str, iterations: int):
    """Print formatted results table."""
    print()
    print("=" * 60)
    print("       Voice Assistant Latency Benchmark")
    print("=" * 60)
    print(f"Model: {model} | Iterations: {iterations}")
    print()

    for prompt_name, data in results.items():
        prompt = data["prompt"]
        stats = data["stats"]

        # Truncate long prompts for display
        display_prompt = prompt if len(prompt) <= 50 else prompt[:47] + "..."

        print(f"Prompt: \"{display_prompt}\"")
        print("+" + "-" * 21 + "+" + "-" * 11 + "+" + "-" * 11 + "+" + "-" * 11 + "+")
        print("| {:<19} | {:>9} | {:>9} | {:>9} |".format("Metric", "Mean", "Min", "Max"))
        print("+" + "-" * 21 + "+" + "-" * 11 + "+" + "-" * 11 + "+" + "-" * 11 + "+")

        # LLM metrics
        print("| {:<19} | {:>7}ms | {:>7}ms | {:>7}ms |".format(
            "LLM TTFT",
            stats["llm_ttft_ms"]["mean"],
            stats["llm_ttft_ms"]["min"],
            stats["llm_ttft_ms"]["max"],
        ))
        print("| {:<19} | {:>7}ms | {:>7}ms | {:>7}ms |".format(
            "LLM Total",
            stats["llm_total_ms"]["mean"],
            stats["llm_total_ms"]["min"],
            stats["llm_total_ms"]["max"],
        ))
        print("| {:<19} | {:>9} | {:>9} | {:>9} |".format(
            "LLM Tokens/sec",
            stats["llm_tokens_per_sec"]["mean"],
            stats["llm_tokens_per_sec"]["min"],
            stats["llm_tokens_per_sec"]["max"],
        ))

        # TTS metrics
        print("| {:<19} | {:>7}ms | {:>7}ms | {:>7}ms |".format(
            "TTS Generation",
            stats["tts_generation_ms"]["mean"],
            stats["tts_generation_ms"]["min"],
            stats["tts_generation_ms"]["max"],
        ))
        print("| {:<19} | {:>9} | {:>9} | {:>9} |".format(
            "TTS RTF",
            stats["tts_rtf"]["mean"],
            stats["tts_rtf"]["min"],
            stats["tts_rtf"]["max"],
        ))

        # Full turn
        print("| {:<19} | {:>7}ms | {:>7}ms | {:>7}ms |".format(
            "Full Turn",
            stats["full_turn_ms"]["mean"],
            stats["full_turn_ms"]["min"],
            stats["full_turn_ms"]["max"],
        ))

        print("+" + "-" * 21 + "+" + "-" * 11 + "+" + "-" * 11 + "+" + "-" * 11 + "+")

        # Check against targets
        full_turn_mean = stats["full_turn_ms"]["mean"]
        llm_ttft_mean = stats["llm_ttft_ms"]["mean"]

        ttft_status = "PASS" if llm_ttft_mean <= TARGETS["llm_ttft"] else "FAIL"
        turn_status = "PASS" if full_turn_mean <= TARGETS["full_turn"] else "FAIL"

        print(f"Targets: TTFT <= {TARGETS['llm_ttft']}ms [{ttft_status}] | Full turn <= {TARGETS['full_turn']}ms [{turn_status}]")
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    # Find best/worst full turn times
    all_turns = [(name, data["stats"]["full_turn_ms"]["mean"]) for name, data in results.items()]
    if all_turns:
        best = min(all_turns, key=lambda x: x[1])
        worst = max(all_turns, key=lambda x: x[1])
        print(f"Best full turn:  {best[0]} prompt - {best[1]}ms")
        print(f"Worst full turn: {worst[0]} prompt - {worst[1]}ms")
        print()

        # Overall verdict
        if all(t[1] <= TARGETS["full_turn"] for t in all_turns):
            print("All prompts meet the target latency!")
        else:
            failed = [t for t in all_turns if t[1] > TARGETS["full_turn"]]
            print(f"Prompts exceeding target: {', '.join(f[0] for f in failed)}")


def main():
    ap = argparse.ArgumentParser(
        description="Benchmark voice assistant latency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 src/benchmark_latency.py
    python3 src/benchmark_latency.py --iterations 10
    python3 src/benchmark_latency.py --prompts short medium
    python3 src/benchmark_latency.py --json > results.json
        """,
    )
    ap.add_argument("--host", default=OLLAMA_HOST, help="Ollama API endpoint")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Model to benchmark")
    ap.add_argument("--iterations", "-n", type=int, default=5, help="Iterations per prompt")
    ap.add_argument(
        "--prompts",
        nargs="+",
        choices=list(PROMPTS.keys()),
        default=list(PROMPTS.keys()),
        help="Prompts to test",
    )
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    ap.add_argument("--list-prompts", action="store_true", help="List available prompts")
    args = ap.parse_args()

    if args.list_prompts:
        print("Available prompts:")
        for name, prompt in PROMPTS.items():
            print(f"  {name}: \"{prompt}\"")
        return

    print(f"Running benchmark with {args.iterations} iterations...")
    print(f"Model: {args.model}")
    print(f"Prompts: {', '.join(args.prompts)}")
    print()

    results = run_benchmark(args.prompts, args.iterations, args.model, args.host)

    if args.json:
        output = {
            "model": args.model,
            "iterations": args.iterations,
            "targets": TARGETS,
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        print_results(results, args.model, args.iterations)


if __name__ == "__main__":
    main()
