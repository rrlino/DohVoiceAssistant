# Hardware Setup Guide

## Required Components

### Core

| Component | Specification | Approx. Cost | Notes |
|-----------|---------------|--------------|-------|
| Raspberry Pi 5 | 16GB RAM | ~£120 | 8GB may work, 16GB recommended |
| Hailo AI HAT+ | Hailo-10H | ~£140 | AI accelerator |
| Power Supply | 5V/5A USB-C | ~£15 | Official Pi 5 PSU recommended |
| Storage | 64GB+ SD Card or NVMe | ~£20 | NVMe faster for LLM inference |

### Audio (Choose One)

| Option | Components | Cost | Notes |
|--------|------------|------|-------|
| **Option A** | ReSpeaker Lite + Mono Speaker + Case | ~£36 | All-in-one USB solution |
| **Option B** | USB Mic + Bluetooth Speaker | ~£30-50 | Separate input/output |
| **Option C** | USB Headset | ~£20-40 | Simplest setup |

### Option A: ReSpeaker Lite (Recommended)

| Item | Source | Price |
|------|--------|-------|
| ReSpeaker Lite with XIAO ESP32S3 | The Pi Hut | £28.80 |
| Mono Enclosed Speaker (4Ω, 5W) | The Pi Hut | £2.40 |
| Black DIY Case | The Pi Hut | £4.80 |
| **Total** | | **£36** |

## Assembly

### 1. Install Hailo AI HAT+

1. Power off the Pi 5
2. Remove the Pi 5 from power
3. Align the Hailo HAT+ with the PCIe connector
4. Gently press down until seated
5. Secure with provided screws
6. Reconnect power

### 2. Verify Hailo Installation

```bash
# Check Hailo is detected
hailortcli fw-control identify

# Expected output:
# Hailo AI HAT+ identified
# Device: HAILO10H
# FW Version: 5.1.1
```

### 3. Connect Audio

**ReSpeaker Lite:**
```bash
# Connect via USB
# Check detection
arecord -l  # List input devices
aplay -l    # List output devices
```

**Bluetooth Speaker (Lenrue A12):**
```bash
# Pair via bluetoothctl
bluetoothctl
[bluetoothctl] scan on
[bluetoothctl] pair 0B:B1:E3:49:9B:D9
[bluetoothctl] connect 0B:B1:E3:49:9B:D9
[bluetoothctl] trust 0B:B1:E3:49:9B:D9
[bluetoothctl] exit

# Set as default sink
pactl set-default-sink bluez_sink.0B_B1_E3_49_9B_D9.a2dp_sink
```

## Software Setup

### 1. Install Hailo Software

```bash
# Install Hailo repository
wget https://hailo.ai/debian/hailo.deb
sudo dpkg -i hailo.deb
sudo apt update
sudo apt install hailo-all
```

### 2. Install hailo-ollama

```bash
sudo apt install hailo-ollama
```

### 3. Install hailo-apps

```bash
git clone https://github.com/hailo-ai/hailo-apps.git
cd hailo-apps
sudo ./install.sh
source setup_env.sh
```

### 4. Install Piper TTS

```bash
cd ~/hailo-apps/local_resources/piper_models
python3 -m piper.download_voices en_US-joe-medium
```

## Verification

### Test Hailo

```bash
hailortcli fw-control identify
```

### Test LLM

```bash
# Start hailo-ollama
nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &

# Test API
curl -s http://127.0.0.1:8000/api/tags
```

### Test Audio

```bash
# Test speaker
speaker-test -t wav -c 2 -l 1

# Test TTS
python3 -c "import pyttsx3; e = pyttsx3.init(); e.say('Hello from Raspberry Pi'); e.runAndWait()"
```

## Troubleshooting

### Hailo Not Detected

1. Check HAT is seated properly
2. Verify power supply is 5V/5A
3. Check `dmesg | grep hailo`

### No Audio

1. Check device is selected: `pactl list sinks short`
2. Test with `speaker-test`
3. Check PulseAudio is running: `pulseaudio --check`

### Bluetooth Won't Connect

1. Remove and re-pair:
   ```bash
   bluetoothctl remove 0B:B1:E3:49:9B:D9
   bluetoothctl scan on
   # ... pair again
   ```
2. Ensure PulseAudio Bluetooth module is installed:
   ```bash
   sudo apt install pulseaudio-module-bluetooth
   ```

## Total Cost Breakdown

| Category | Cost |
|----------|------|
| Raspberry Pi 5 (16GB) | £120 |
| Hailo AI HAT+ | £140 |
| Power Supply | £15 |
| Storage (64GB SD) | £15 |
| ReSpeaker Lite Kit | £36 |
| **Total** | **~£326** |

Compare to: Amazon Echo (£50) + Prime subscription (£95/year) + Privacy concerns = Priceless
