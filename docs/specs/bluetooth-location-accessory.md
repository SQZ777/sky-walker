# [Spike + PoC] Windows BLE LNS Location Accessory

**Status:** implemented; physical acceptance open

## Problem Statement

Sky Walker can replace a USB-connected iPhone's system location through Apple's developer DVT service. That path cannot prove that iOS accepted a location from a Bluetooth accessory, and it does not satisfy the requirement for Windows to act as the paired location device.

The spike must determine, with reproducible physical-device evidence, whether a Windows BLE peripheral publishing the standard Location and Navigation Service (LNS) can supply system-wide iPhone locations that Core Location marks as produced by an accessory. A successful Bluetooth advertisement or notification is diagnostic evidence only; it is not acceptance.

## End-to-End Outcome

`sky-walker ble-spike run` keeps a foreground Windows BLE peripheral alive, advertises LNS, waits for a collector subscription, and publishes a caller-selected static coordinate at 1 Hz. The iPhone Source Probe independently observes Core Location without using Core Bluetooth, while Windows records transport state and continuous Apple USB absence. The Windows validator correlates these artifacts and returns pass, fail, inconclusive, or invalid.

The first release stops at the validated CLI. It does not integrate Bluetooth into the desktop GUI.

## User Stories

1. As a Windows tester, I can check whether the active Bluetooth adapter supports the LE peripheral role before starting an experiment.
2. As a Windows tester, I can create a BLE-LNS Source Test Session with a stable ID, coordinate, environment, and timing contract.
3. As an iPhone tester, I can capture unmodified Core Location callbacks in Source Probe and see their source flags without Source Probe connecting to Bluetooth.
4. As a Windows tester, I can advertise standard LNS and see whether an iPhone connects and subscribes.
5. As a Windows tester, I can publish one static coordinate at 1 Hz and stop safely when the foreground command exits.
6. As a researcher, I receive a strict verdict that cannot pass if USB appeared, Bluetooth disconnected, source metadata was missing, or attributed callbacks were not consecutive.
7. As a researcher, I can reject the LNS hypothesis after three bounded physical attempts instead of extending an inconclusive spike indefinitely.

## Decisions

- **Branch and platform:** Build from the latest desktop-GUI baseline. Windows remains the control plane; macOS is used only to build, sign, and install Source Probe.
- **Transport:** Publish Bluetooth SIG LNS as a Windows LE peripheral. Visibility in iOS Settings is desirable but not required; Accessory Attribution is required.
- **Implementation carrier:** Use foreground Python with PyWinRT packages behind an optional `bluetooth` dependency group. Keep the platform adapter behind a small start/publish/stop/status boundary so a later C# helper can replace it without changing the experiment.
- **Capability gate:** Refuse to run unless a real default adapter exists, Bluetooth LE is supported, and `IsPeripheralRoleSupported` is true. Unsupported hardware is replaced with a supported dongle or BLE development board; the spike does not switch to Bluetooth Classic.
- **Stimulus:** Publish the requested latitude and longitude at 1 Hz. Route Playback, altitude, speed, course, and GUI controls are deferred.
- **Foreground lifetime:** The command owns advertising and event handlers. Exit or Ctrl-C stops advertising. A Bluetooth disconnect during capture makes the session inconclusive rather than reconnecting inside the same session.
- **DVT isolation:** BLE code must not import or call the USB backend, `LocationOverride`, `pymobiledevice3`, or a pymobiledevice3 subprocess. The global USB `--udid` option is not part of the BLE command.
- **iPhone witness:** Source Probe uses Core Location only, preserves every callback and source flag, and never scans, connects to, or reads the BLE service.
- **Connection proof:** Windows records a timestamped Apple USB presence timeline for the entire capture. Any present, error, unknown, or uncovered interval prevents pass.
- **Attribution proof:** Ignore the first 10 seconds, then require at least 10 consecutive callbacks within 25 metres of the target, each with non-nil source information and `isProducedByAccessory == true`. Maps is a secondary visual check only.
- **Experiment bound:** Each Source Test Session lasts at most 120 seconds. One strict pass proves the hypothesis; three independent sessions without a pass reject it. Bluetooth disconnect produces an inconclusive session but still consumes an attempt when the experiment is summarized.
- **Post-failure research:** Only after the bounded LNS failure may the user provide an installed third-party locator for read-only signature, manifest, configuration, log, service, driver, HCI/ETW, GATT, and packet-behavior inspection. Binary decompilation and authentication bypass remain out of scope.

## Testing Seams

- **Command seam:** Exercise `ble-spike doctor` and `ble-spike run` through their argument surface and process status.
- **Peripheral seam:** Substitute the Windows Bluetooth boundary while testing advertised, connected, subscribed, feeding, disconnected, and stopped behavior.
- **Evidence seam:** Treat manifest, Source Probe JSONL, transport trace, and USB timeline as inputs; assert only the resulting Probe Verdict and operator summary.
- **Architecture seam:** Fail if BLE modules transitively import the DVT backend, Location Override, pymobiledevice3, or a subprocess path to it.
- **Codec seam:** Compare LNS bytes against fixed Bluetooth SIG examples or independently worked literal vectors.
- **Physical acceptance:** Unit tests cannot establish Accessory Attribution. Completion requires either one physical pass or three preserved, reproducible physical non-passes under the experiment bound.

## Out of Scope

- Bluetooth Classic, RFCOMM, SPP, iAP, MFi implementation, or custom kernel/HCI driver development.
- GUI integration, Route Playback, Joystick Mode, background service operation, or MSIX packaging.
- A companion iPhone app that connects to LNS or substitutes locations inside one app.
- DVT fallback, hidden USB injection, source-flag fabrication, or synthetic `CLLocation` acceptance evidence.
- Automatic reverse engineering of encrypted, authenticated, or proprietary third-party protocols.
