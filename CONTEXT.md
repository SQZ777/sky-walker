# Sky Walker

A developer tool that connects to a physical iPhone over USB from a Windows host and overrides its GPS location, so an iOS app under development can be tested against arbitrary locations.

## Language

### Core concepts

**Location Override**:
A live, system-wide replacement of the iPhone's real GPS fix with a location supplied by the host. Affects every app on the device, not just the app under test, and lasts only while the session is held.
_Avoid_: spoof, fake GPS, mock location

**Teleport**:
Setting the override to a single static coordinate and holding it there. The MVP capability.
_Avoid_: jump, set point

**Route Playback**:
Feeding a sequence of coordinates (e.g. from a GPX file) so the device appears to move along a path. A later capability, distinct from Teleport.
_Avoid_: simulate movement, drive, track

**Session**:
The live connection during which a Location Override is in effect. When the Session ends (cleared, process exits, or device reboots) the device returns to its real GPS.

**Interactive Mode**:
The tool's primary and only mode of operation: a prompt that opens one Tunnel, teleports to the Default Location, then stays live — accepting new coordinates that re-teleport the device over the same connection, until the user clears or exits. Distinct from a one-shot command that must be re-run to move.
_Avoid_: REPL, console, shell

**Clear**:
Ending the override and returning the device to its real GPS fix.
_Avoid_: reset, stop, restore

**Default Location**:
The coordinate the tool pre-fills when prompting the user, so the common case is a single keystroke. Currently `25.073944586589487, 121.51104972333346`.
_Avoid_: home, preset

**Doctor**:
A preflight self-check that verifies every prerequisite for a Session (Apple USB driver present, device paired, Developer Mode on, device visible, tunnel establishable) and reports plain-language fixes for whatever is missing.
_Avoid_: check, healthcheck, diagnose

### Device prerequisites

**Developer Mode**:
The iOS setting (required since iOS 16) that must be enabled on the device before any developer service, including Location Override, will run.

**Pairing**:
The trusted USB relationship between host and device, established by accepting "Trust This Computer" on the iPhone. Required before the host can drive the device.

**Tunnel**:
The encrypted USB channel (CoreDeviceProxy / RemoteXPC) that iOS 17.4+ requires to reach developer services such as Location Override. On the supported iOS bands this is established in userspace with no administrator rights.
