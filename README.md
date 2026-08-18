# Sky Walker

Override a USB-connected iPhone's GPS location from a **Windows** host, so you can
test an iOS app against arbitrary coordinates.

- No jailbreak, no paid Apple Developer account.
- Uses Apple's own developer service via [`pymobiledevice3`](https://github.com/doronz88/pymobiledevice3).
- Scoped to **iOS 17.4+** (e.g. iPhone 15 Pro on iOS 26.x) — the no-admin,
  no-extra-driver userspace-tunnel path. See [docs/adr/0001](docs/adr/0001-foundation-pymobiledevice3-windows-ios17.4.md).

See [`CONTEXT.md`](CONTEXT.md) for the vocabulary and [`docs/adr/`](docs/adr) for
the design decisions.

## Requirements on the iPhone

1. **Developer Mode** on — Settings → Privacy & Security → Developer Mode, then reboot.
2. **Trust This Computer** accepted over USB (pairing).

## Requirements on Windows

- **Apple's USB driver** — install iTunes or the Apple Devices app so `usbmux` sees the phone.
- **Python ≥ 3.9**.

## Install

```bash
pip install -e .
```

## Use

Check everything is wired up:

```bash
sky-walker doctor
```

Start Interactive Mode (opens the tunnel, teleports to the Default Location, and
holds the override in the foreground):

```bash
sky-walker
```

Inside the prompt:

```
coordinate [25.073944586589487, 121.51104972333346]:      # Enter accepts the default
sky-walker> 37.7749, -122.4194                            # move to San Francisco
sky-walker> clear                                         # back to real GPS
sky-walker> exit                                          # leave (also reverts)
```

Leaving the process — `exit`, Ctrl-C, or a crash — reverts the device to its real
GPS (see [docs/adr/0002](docs/adr/0002-foreground-interactive-session-model.md)).

## Experimental Core Location source probe

The Accessory Attribution Spike is intentionally separate from Location Override.
Windows creates a Source Test Session and validates JSONL exported by the minimal
iOS Source Probe:

```bash
sky-walker probe new real-gps --ios-version 26.4 --probe-build 1
sky-walker probe validate artifacts/probe-runs/SESSION.manifest.json capture.jsonl
```

The iOS project lives at `poc/ios-source-probe/` and requires a Mac with Xcode only
for build, signing, and installation. See
[`docs/probe/mac-build-and-smoke-test.md`](docs/probe/mac-build-and-smoke-test.md).
This phase does not implement a Windows Bluetooth GPS server and does not assume
that iAnyGo or a generic Bluetooth profile produces accessory-attributed locations.

## Status

Design and skeleton, validated against an iPhone 15 Pro on iOS 26.4: device
detection, the userspace tunnel, and the DVT location service all reached. On
iOS 17+ location must go through the instruments DVT hub (`DvtProvider` +
`LocationSimulation`) — the bare `com.apple.dt.simulatelocation` service is no
longer published; see the note in `backend.py`.
