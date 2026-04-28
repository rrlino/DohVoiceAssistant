# HailoRT 5.1.1 → 5.2.0 Upgrade

**Date:** 2026-04-28
**Status:** Resolved
**Related:** `PI5-PCIE-FIX.md` (which solved a different power/PCIe-lane issue earlier)

## Symptom

After the PCIe x4 fix made the Pi stable for short demos, sustained voice-assistant use kept hanging the Pi after one or two turns. Pattern:

- LLM inference completed (or partly completed)
- `eth0` networking stack started failing (`NetworkManager: ip-config -> failed`)
- ~2 minute silent gap in journal
- Hardware watchdog (`bcm2835-wdt`, 60s timeout) hard-reset the SoC
- Pi rebooted; no kernel oops, panic, hung_task, or undervoltage in the journal

This was distinct from the earlier x1/x4 PCIe issue: the kernel left no software fault signature, and power was confirmed clean (`EXT5V_V` ≥ 4.97 V, `vcgencmd get_throttled` = `0x0`).

## Root cause

A known runtime-level bug in **HailoRT 5.1.1** on Hailo-10H (AI HAT+ 2) under sustained inference. Documented across multiple Hailo Community threads:

- *Hailo-10H on Raspberry Pi AI HAT+ 2 times out during inference, including direct hailortcli run2*
- *Hailo-10H COMMUNICATION_CLOSED after ~5000 frames of continuous inference (AI HAT+ 2, Pi 5)*
- *Raspberry Pi 5 and AI Hat+2 5.2 Driver Issues 5.1.1*

A kernel-level companion fix was already in our installed kernel (`6.12.62+rpt-rpi-2712` ≥ `6.12.34`), but the runtime side was still on 5.1.1.

## Fix path

Three runtime packages upgrade cleanly via the official Raspberry Pi apt repo:

```bash
sudo apt update
sudo apt install --only-upgrade \
    h10-hailort \
    h10-hailort-pcie-driver \
    python3-h10-hailort
sudo reboot
```

Reboot is required for the new PCIe kernel module. The on-board firmware re-flashes automatically on first boot with the new driver. Verify:

```bash
hailortcli fw-control identify
# Firmware Version: 5.2.0 (release,app)
```

### Two gotchas during the upgrade

**Gotcha 1 — `hailo-gen-ai-model-zoo` 5.2.0 has a packaging bug.** It declares a dependency on `hailort` (the Hailo-8 runtime) instead of `h10-hailort`, so apt refuses to upgrade it. Skip it; the model files inside are LLM HEFs that are tracked by manifest hash, and we'll fetch the new HEF separately.

**Gotcha 2 — `hailo-ollama` (binary shipped inside `hailo-gen-ai-model-zoo`) is dynamically linked to `libhailort.so.5.1.1`.** Upgrading the runtime removes the 5.1.1 soname. Until the model-zoo package gets a clean Hailo-10H rebuild, work around with a compatibility symlink (the 5.1.1 → 5.2.0 ABI is compatible):

```bash
sudo ln -sf /usr/lib/libhailort.so.5.2.0 /usr/lib/libhailort.so.5.1.1
sudo ldconfig
```

## HEF compatibility (the second bug)

After the runtime upgrade, the existing Qwen2 HEF errored with:

```
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_HEF(26) - Failed to create LLM
```

HEFs (Hailo Executable Format) are runtime-version-specific. The 5.1.1-compiled Qwen2 HEF is incompatible with the 5.2.0 runtime; we need the 5.2.0 build.

The 5.2.0 model-zoo `.deb` package ships only manifests (the HEF blobs are pulled lazily). Each manifest holds a SHA256 hash of the HEF; the `hailo-ollama` daemon fetches the matching blob from `dev-public.hailo.ai`.

Steps:

```bash
# 1) Get the 5.2.0 manifests without installing the conflicting package
cd /tmp
apt download hailo-gen-ai-model-zoo
mkdir mz-extract
dpkg-deb -x hailo-gen-ai-model-zoo_5.2.0_arm64.deb mz-extract/

# 2) Replace the qwen2 manifest with the 5.2.0 version
sudo cp mz-extract/usr/share/hailo-ollama/models/manifests/qwen2/1.5b/manifest.json \
        /usr/share/hailo-ollama/models/manifests/qwen2/1.5b/manifest.json

# 3) Restart hailo-ollama so it sees the new manifest
systemctl --user restart hailo-ollama

# 4) Pull the new HEF (~1.7 GB)
curl -X POST -H "Content-Type: application/json" \
     http://127.0.0.1:8000/api/pull \
     -d '{"model":"qwen2:1.5b"}'
```

The pull endpoint streams progress; keep the connection open until you see `{"status":"success"}` (about 80s on a fast link). The new blob lands at:

```
/usr/share/hailo-ollama/models/blob/sha256_<new-hash>
```

The old 5.1.1 blob can be deleted to recover ~1.7 GB after the new one is verified working.

Repeat the same manifest-replace + pull for any other HEF model you use (deepseek, llama3.2, qwen2.5, etc.).

## Validation

Five consecutive `--once` turns from `voice_assistant_pi.py --tts sherpa --max-tokens 30`:

```
Turn 1: "Hello, Homer."
Turn 2: "You'll never guess, but I'm Homer."
Turn 3: "Red."
Turn 4: "D'oh!"
Turn 5: "Goodbye, Homer Simpson!"

throttled=0x0 throughout, EXT5V ≈ 5.00 V steady, no watchdog reset.
```

Pre-fix: hung within 2-3 turns every time. Post-fix: clean.

## Sources

- Hailo Community: [Kernel Bug Fix - Update Available](https://community.hailo.ai/t/kernel-bug-fix-update-available/16028)
- Hailo Community: [Hailo-10H times out during inference](https://community.hailo.ai/t/hailo-10h-on-raspberry-pi-ai-hat-2-times-out-during-inference-including-direct-hailortcli-run2/18868)
- Hailo Community: [Hailo-10H COMMUNICATION_CLOSED after ~5000 frames](https://community.hailo.ai/t/hailo-10h-communication-closed-after-5000-frames-of-continuous-inference-ai-hat-2-pi-5/19012)
- Hailo Community: [Upgrading to HailoRT 5.2.0 - step by step](https://community.hailo.ai/t/upgrading-to-hailort-5-2-0-step-by-step-raspberry-pi-hailo-apps/19006)
- Hailo Community: [Pi 5 and AI Hat+2 5.2 Driver Issues 5.1.1](https://community.hailo.ai/t/raspberry-pi-5-and-ai-hat-2-5-2-driver-issues-5-1-1/18694)
- raspberrypi/linux: [Issue #7184 — Pi 5 system freeze + USB/UART buffer exhaustion](https://github.com/raspberrypi/linux/issues/7184)
