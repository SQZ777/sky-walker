# Sky Walker

Test iPhone location behavior from a **Windows** host. The stable path uses a
USB developer Location Override; an experimental, strictly isolated BLE LNS path
tests whether iOS accepts Windows as an accessory-produced location source.

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

To run the experimental Windows Bluetooth peripheral, install the optional
PyWinRT dependencies:

```powershell
pip install -e ".[bluetooth]"
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

## Experimental Bluetooth Location Accessory spike

The Accessory Attribution spike is intentionally separate from Location Override.
It never imports or calls the USB/DVT backend. First verify the active Windows
adapter can advertise a BLE peripheral:

```powershell
sky-walker ble-spike doctor
```

Install the iOS Source Probe using the Mac instructions below. Then unplug every
Apple USB device and create one bounded Source Test Session:

```powershell
sky-walker probe new sky-walker-ble-lns `
  --ios-version 26.4 `
  --probe-build 1 `
  --bluetooth-adapter "TP-Link Bluetooth USB Adapter" `
  --confirm-usb-disconnected
```

In a second Windows terminal, use the printed session ID and manifest coordinate:

```powershell
sky-walker ble-spike run `
  --session-id <SESSION> `
  --latitude <LATITUDE> `
  --longitude <LONGITUDE> `
  --duration 120
```

While that foreground command is advertising, start the matching capture in
Source Probe. Stop the iPhone capture before the 120-second feed ends, export its
JSONL without USB, and validate all three artifacts:

```powershell
sky-walker probe validate `
  artifacts/probe-runs/<SESSION>.manifest.json `
  <exported-file>.jsonl `
  --ble-trace artifacts/probe-runs/<SESSION>.ble-trace.jsonl `
  --output artifacts/probe-runs/<SESSION>.verdict.json
```

The iOS project lives at `poc/ios-source-probe/` and requires a Mac with Xcode only
for build, signing, and installation. See
[`docs/probe/mac-build-and-smoke-test.md`](docs/probe/mac-build-and-smoke-test.md).

An iPhone may not list a generic BLE GATT service in Settings. Pairing visibility
is diagnostic only. The spike passes solely when Source Probe records 10
consecutive post-stabilization callbacks within 25 metres and Core Location sets
`isProducedByAccessory == true`, with continuous Windows evidence that USB stayed
absent. One pass confirms the hypothesis; three bounded sessions without a pass
reject it and gate the approved read-only vendor investigation.

Preserve each verdict with `--output`. A strict pass confirms the hypothesis
immediately; otherwise summarize up to three distinct attempts:

```powershell
sky-walker probe summarize `
  artifacts/probe-runs/<SESSION-1>.verdict.json `
  artifacts/probe-runs/<SESSION-2>.verdict.json `
  artifacts/probe-runs/<SESSION-3>.verdict.json
```

## Status

USB Location Override is implemented and validated against an iPhone 15 Pro on
iOS 26.4. The Windows BLE LNS peripheral, 1 Hz feed, continuous USB/transport
trace, Source Probe, and strict validator are implemented; physical iPhone
Accessory Attribution has not yet been established. See
[`docs/specs/bluetooth-location-accessory.md`](docs/specs/bluetooth-location-accessory.md)
for the acceptance boundary.
