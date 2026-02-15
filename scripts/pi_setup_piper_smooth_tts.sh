#!/usr/bin/env bash
# Run on the Pi: install Piper standalone binary for smoother TTS (and voice models if needed).
# After this, use: TTS_ENGINE=piper python3 voice_assistant_pi.py
set -e
PIPER_DIR=~/piper
PIPER_MODELS=~/piper_models
mkdir -p "$PIPER_DIR" "$PIPER_MODELS"
cd /tmp
if [ ! -f piper_aarch64.tar.gz ]; then
  echo "Downloading Piper aarch64..."
  curl -sL -o piper_aarch64.tar.gz "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz"
fi
tar -xzf piper_aarch64.tar.gz
cp -a piper/* "$PIPER_DIR/"
echo "Piper binary at $PIPER_DIR/piper"
if [ ! -f "$PIPER_MODELS/en_US-amy-low.onnx" ]; then
  echo "Downloading voice en_US-amy-low..."
  (cd "$PIPER_MODELS" && python3 -m piper.download_voices en_US-amy-low 2>/dev/null) || true
fi
echo "Done. Use: export TTS_ENGINE=piper; export PIPER_BIN=$PIPER_DIR/piper; export PIPER_ESPEAK_DATA=$PIPER_DIR/espeak-ng-data; export PIPER_LD_LIBRARY_PATH=$PIPER_DIR"
echo "Or run: TTS_ENGINE=piper PIPER_BIN=$PIPER_DIR/piper PIPER_ESPEAK_DATA=$PIPER_DIR/espeak-ng-data PIPER_LD_LIBRARY_PATH=$PIPER_DIR python3 voice_assistant_pi.py --once 'Hello'"
