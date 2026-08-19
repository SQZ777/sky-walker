# Source Probe: Mac build and physical-iPhone smoke test

Source Probe is authored in this Windows-first repository, but Apple requires Xcode on macOS to build, sign, and install it. The Mac is only a Build Station; session creation and evidence validation stay on Windows.

## One-time Xcode setup

1. On the Mac, check out the same branch and open `poc/ios-source-probe/SourceProbe.xcodeproj` in Xcode 16 or newer.
2. Select the `SourceProbe` target, open **Signing & Capabilities**, choose your Personal Team, and change `com.example.skywalker.SourceProbe` to a bundle identifier unique to your Apple Account.
3. Connect the test iPhone, accept **Trust This Computer**, enable Developer Mode if Xcode requests it, and select that iPhone as the run destination.
4. Run **Product → Test**. `ProbeSerializationTests` must pass before using exported evidence.
5. Run the app on the iPhone and grant only **While Using the App** location permission.

A free Personal Team is sufficient, but its provisioning expires after seven days. Reopen the project, rebuild, and reinstall when iOS reports that the app is no longer available.

## First real-GPS round trip

The real-GPS run proves the capture/export/Windows-validation pipeline; it is not expected to prove Accessory Attribution. Use a known physical coordinate near the phone rather than assuming the project Default Location is where the phone currently is.

On Windows:

```powershell
sky-walker probe new real-gps `
  --ios-version 26.4 `
  --probe-build 1 `
  --latitude <known-latitude> `
  --longitude <known-longitude>
```

Then:

1. Disable Sky Walker and iAnyGo. Keep Source Probe in the foreground and move to a place with a usable real GPS fix.
2. Enter the eight-character Session ID and select **Real GPS**.
3. Tap **Start**. The app records every `CLLocation` in every callback and automatically stops after 120 seconds; tap **Stop** earlier once at least 10 post-stabilization callbacks are visible.
4. Tap **Export JSONL** and save or share the file manually. Do not edit it.
5. Transfer the JSONL to Windows and validate it:

```powershell
sky-walker probe validate `
  artifacts/probe-runs/<SESSION>.manifest.json `
  <exported-file>.jsonl
```

For real GPS, a complete run will normally return `fail` (exit 1) because accessory attribution was not observed, or `inconclusive` (exit 2) if source information is nil or the evidence is insufficient. Either result is acceptable for this smoke test if the JSONL is structurally valid and the reason matches the observed data.

## Benchmark order

After the real-GPS round trip succeeds, repeat on the same iPhone in this order:

1. `sky-walker-usb`
2. `ianygo-general`
3. `ianygo-bluetooth`

Use the same manifest coordinate and fallback route for the three controllable scenarios. For iAnyGo Bluetooth, create the session with its product version, Bluetooth adapter name, and explicit USB confirmation:

```powershell
sky-walker probe new ianygo-bluetooth `
  --ios-version 26.4 `
  --probe-build 1 `
  --location-product-version <version> `
  --bluetooth-adapter <adapter-name> `
  --confirm-usb-disconnected
```

The Windows manifest independently records whether an Apple USB device is present. Any present, unknown, or unconfirmed USB state prevents a Bluetooth pass.

## Sky Walker BLE LNS attempt

After the real-GPS round trip proves the witness pipeline, run the bounded LNS
experiment described in the repository README. Source Probe must remain a Core
Location-only witness; do not add Core Bluetooth discovery or a GATT client to
make the service connect.

Keep the iPhone and Windows clocks synchronized automatically. Start the
foreground `ble-spike run` command before tapping **Start** in Source Probe, and
tap **Stop** before the feed's 120-second deadline. Transfer the exported JSONL
back without reconnecting Apple USB during capture. Validation requires the BLE
trace explicitly:

```powershell
sky-walker probe validate `
  artifacts/probe-runs/<SESSION>.manifest.json `
  <exported-file>.jsonl `
  --ble-trace artifacts/probe-runs/<SESSION>.ble-trace.jsonl `
  --output artifacts/probe-runs/<SESSION>.verdict.json
```

The trace must cover the entire iPhone capture, show an LNS subscriber by the end
of the 10-second stabilization window, retain a continuous 1 Hz sample stream,
and show Apple USB absent throughout. A disconnect, USB observation error, or
uncovered interval makes the session inconclusive. Preserve three independent
attempts before rejecting LNS and moving to the approved vendor-behavior study.
Use `sky-walker probe summarize <verdict...>` after each attempt. One strict pass
confirms the hypothesis; one or two non-passes remain inconclusive; exactly three
distinct non-passes reject it. A disconnect remains inconclusive for that Probe
Verdict but still counts as one preserved attempt.

## Evidence rules

- Only locations delivered by `CLLocationManager` count. Do not use a synthetic `CLLocation` as physical evidence.
- Keep Source Probe foregrounded; it requests no background permission.
- Do not merge logs from separate Source Test Sessions.
- Keep raw artifacts under `artifacts/probe-runs/`, which Git ignores. Commit only manually de-identified fixtures.
- Do not intercept iAnyGo traffic, inspect private payloads, or attempt to reproduce unpublished protocols.
- For Sky Walker BLE LNS, the timestamped BLE trace is the authoritative
  continuous USB evidence; validation-time cable state does not rewrite history.
