# Test BLE LNS as a falsifiable location-accessory hypothesis

The first Bluetooth transport spike will publish the standard Location and Navigation Service from a Windows foreground process through PyWinRT. This is a deliberately falsifiable experiment: public Apple documentation does not promise that iOS consumes generic LNS as a Core Location source, so only physical Source Probe evidence with `isProducedByAccessory == true` counts as success.

## Consequences

- Adapter peripheral-role support is checked before service construction; unsupported hardware is replaced rather than silently changing protocols.
- The first stimulus is one static coordinate at 1 Hz, with no route playback or GUI integration.
- One strict pass completes the spike; three independent 120-second sessions without Accessory Attribution reject the LNS hypothesis and gate any third-party protocol investigation.
