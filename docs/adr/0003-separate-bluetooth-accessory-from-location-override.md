# Keep Bluetooth Accessory Feed separate from USB Location Override

Sky Walker will treat Bluetooth Accessory Feed as a capability and lifecycle separate from USB Location Override. The experimental BLE path must not import or invoke `pymobiledevice3`, the DVT backend, or `LocationOverride`; it stops a feed rather than clearing an override, and physical-device acceptance requires USB to remain disconnected for the entire Source Test Session.

## Consequences

- The existing USB and GUI behavior remains available and unchanged.
- BLE starts as an experimental foreground CLI instead of sharing the USB-bound GUI bridge.
- Automated architecture checks and continuous USB evidence guard against a false pass through DVT.
