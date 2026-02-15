#!/usr/bin/env python3
"""
Test Qwen model on Pi (hailo-ollama) from this machine.
Pi: hailo-ollama on port 8000 (not 11434 — that's standard ollama on Pi).
"""
import argparse
import json
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_HOST = "http://pi5.local:8000"
MODEL = "qwen2:1.5b"


def list_models(host: str) -> list:
    r = requests.get(f"{host}/api/tags", timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("models", [])


def generate(host: str, prompt: str, stream: bool = False) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": stream,
    }
    r = requests.post(
        f"{host}/api/generate",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120,
        stream=stream,
    )
    r.raise_for_status()
    if stream:
        out = []
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line)
                if chunk.get("response"):
                    out.append(chunk["response"])
                if chunk.get("done"):
                    break
        return "".join(out)
    return r.json().get("response", "")


def chat(host: str, messages: list[dict], stream: bool = False) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
    }
    r = requests.post(
        f"{host}/api/chat",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120,
        stream=stream,
    )
    r.raise_for_status()
    if stream:
        out = []
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line)
                if chunk.get("message", {}).get("content"):
                    out.append(chunk["message"]["content"])
                if chunk.get("done"):
                    break
        return "".join(out)
    return r.json().get("message", {}).get("content", "")


def main():
    p = argparse.ArgumentParser(description="Test Qwen on Pi (hailo-ollama)")
    p.add_argument("--host", default=DEFAULT_HOST, help=f"hailo-ollama base URL (default: {DEFAULT_HOST})")
    p.add_argument("--list", action="store_true", help="List available models")
    p.add_argument("--prompt", "-p", default="Say hello in one short sentence.", help="Prompt for /api/generate")
    p.add_argument("--chat", action="store_true", help="Use /api/chat with a single user message")
    p.add_argument("--stream", action="store_true", help="Stream response")
    args = p.parse_args()

    host = args.host.rstrip("/")

    if args.list:
        models = list_models(host)
        print("Models on Pi (hailo-ollama):")
        for m in models:
            print(f"  - {m.get('name', m)}")
        return

    try:
        if args.chat:
            text = chat(host, [{"role": "user", "content": args.prompt}], stream=args.stream)
        else:
            text = generate(host, args.prompt, stream=args.stream)
        print(text)
    except requests.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        if hasattr(e, "response") and e.response is not None:
            print(e.response.text[:500], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
