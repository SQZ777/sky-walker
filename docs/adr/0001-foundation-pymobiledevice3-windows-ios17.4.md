# Build on pymobiledevice3, Windows-first, supporting only the iOS 17.4+ band

## Context

Sky Walker overrides a physical iPhone's GPS location over USB, from a Windows host, to test an iOS app. Apple exposes this through the `com.apple.dt.simulatelocation` developer service — no jailbreak and no paid developer account needed, only Developer Mode and a trusted USB pairing. The question was how to reach that service from Windows across current iOS versions.

## Decision

Drive the device through **pymobiledevice3 (10.7.x) imported as a Python library**, in-process. Target **Windows as the primary host**. Support **only iOS ≥ 17.4** (our device is an iPhone 15 Pro on iOS 26.4), and **explicitly exclude iOS 17.0–17.3.1**.

The iOS-version scope is the load-bearing part. iOS 17.4+ reaches developer services over an in-process userspace tunnel (CoreDeviceProxy, a pure-Python PyTCP stack) that needs **no administrator rights and no extra kernel driver** on Windows. iOS 17.0–17.3.1 predate CoreDeviceProxy and on Windows require a privileged `tunneld` daemon plus network drivers pymobiledevice3 does not ship — a fragile band not worth supporting.

## Considered Options

- **Mac + Xcode "Simulate Location"** — first-party and simplest, but macOS-only; rejected because the whole point is to run on Windows (a Mac is available only as a fallback).
- **libimobiledevice / `idevicesetlocation`** — solid on iOS < 17, but its iOS 17+ support is incomplete/flaky; rejected for the iOS 26 target.
- **pymobiledevice3 as a CLI subprocess** — stable, well-documented interface, but every `set` spawns its own session-holding process, which makes the interactive re-teleport model (see ADR-0002) require repeatedly killing and respawning. Rejected in favour of the library. See ADR-0002.

## Consequences

- The tool is written in **Python** even though the app under test is iOS — the foundation dictates the language.
- pymobiledevice3's **Python API is thinly documented**; expect to read its source.
- The user's Windows machine must have **Apple's USB stack** (iTunes / Apple Devices app) so usbmux sees the phone, plus **Developer Mode on** and a **trusted pairing**.
- iOS 26 support rests on the maintainer's tested confirmation, not a version-named support matrix — treat new iOS releases as "verify before trusting."
- A device that falls into **iOS 17.0–17.3.1** is out of scope; `doctor` should detect and refuse it rather than fail obscurely.
