# Establish source-attribution evidence before building accessory transport

Sky Walker will first measure `CLLocationManager` callbacks with a Windows-controlled Source Test Session and a minimal iOS Source Probe, while keeping this flow separate from USB Location Override. A Windows Bluetooth server or MFi Simulation Bridge will be considered only after physical-device evidence shows whether the iAnyGo Bluetooth benchmark produces Accessory Attribution; this avoids committing to an unpublished protocol or purchasing hardware before the required Core Location behavior is known.

## Consequences

- Windows remains the experiment control plane; macOS is only a Build Station for signing and installing Source Probe.
- Stopping a Source Probe capture is not Clear or Stop Feed and does not change the iPhone location source.
- A generic Bluetooth transport that only reaches an app is not success; evidence must come from system-delivered Core Location callbacks.
- The first slice can be code-complete on Windows but is not evidence-complete until the real-GPS round trip and vendor benchmark are run on a physical iPhone.
