# Pi 5 + Hailo-10H PCIe x4 Fix

**Date:** 2026-04-19
**Status:** Resolved

## Problem

Pi 5 would hard-crash (power loss, no logs) after 5-10 consecutive voice assistant requests. No kernel panic, no graceful shutdown — just gone. `journalctl --list-boots` showed only 1 boot (previous boot records lost).

## Symptoms

- Pi reboots under sustained LLM + TTS load
- `uptime` shows `up 0 min` after each crash
- No previous boot journal entries (hard power loss)
- No under-voltage or thermal warnings in `dmesg`
- `vcgencmd get_throttled` = `0x0` (no throttling)
- 65W USB-C PSU confirmed (not a power supply issue)

## Root Cause

The Pi 5 `/boot/firmware/config.txt` had:

```
dtparam=pciex1
dtparam=pciex1_gen=3
```

This forced the Hailo-10H AI HAT+ to run on **PCIe x1** (single lane) instead of its designed **x4** (four lanes).

Evidence from `lspci -vv`:

```
LnkCap: Speed 8GT/s, Width x4            # Controller supports x4
LnkSta: Speed 8GT/s, Width x1 (downgraded)  # Only x1 active!
```

dmesg also showed:

```
pci 0001:01:00.0: 7.876 Gb/s available PCIe bandwidth, limited by
8.0 GT/s PCIe x1 link (capable of 31.504 Gb/s with 8.0 GT/s PCIe x4 link)
```

The Hailo-10H was bandwidth-starved at 7.8 Gb/s (x1) instead of 31.5 Gb/s (x4). Under sustained inference load, DMA transfers would overflow or timeout on the constrained bus, causing a hardware-level hang that locked the entire system.

## Fix

Changed `/boot/firmware/config.txt`:

```diff
- dtparam=pciex1
- dtparam=pciex1_gen=3
+ dtparam=pcie4
+ #dtparam=pciex1_gen=3
```

After reboot, `dmesg` confirmed:

```
brcm-pcie 1000120000.pcie: link up, 5.0 GT/s PCIe x4 (!SSC)
```

Note: Gen3 speed override is no longer needed — Gen2 x4 gives 20 Gb/s which is plenty for the Hailo-10H.

## Verification

Ran 10 consecutive E2E turns (STT -> LLM -> TTS) without crash:

```
Turn 1-10: ALL PASS (each ~5-6 seconds)
```

Previously, the Pi would crash around turn 5-10 every time.

## Files Changed

- `/boot/firmware/config.txt` on Pi 5 (line 9: `pciex1` -> `pcie4`)
- `/boot/firmware/config.txt` on Pi 5 (line 10: commented out `pciex1_gen=3`)

## Related

- Hailo-10H AI HAT+ requires PCIe x4 per hardware spec
- Pi 5 has two PCIe controllers: x1 (1000110000.pcie) and x4 (1000120000.pcie)
- The `pciex1` overlay was likely from an initial setup that didn't account for x4 HATs
