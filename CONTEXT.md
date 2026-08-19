# Sky Walker

A developer tool that connects to a physical iPhone over USB from a Windows host and overrides its GPS location, so an iOS app under development can be tested against arbitrary locations.

## Language

### Core concepts

**Location Override**:
A live, system-wide replacement of the iPhone's real GPS fix with a location supplied by the host. Affects every app on the device, not just the app under test, and lasts only while the session is held.
_Avoid_: spoof, fake GPS, mock location

**Accessory Feed**:
A stream of host-selected location samples that Core Location attributes to an external accessory. It is a separate capability from Location Override and has its own connection and failure semantics.
_Avoid_: Bluetooth override, accessory override

**Bluetooth Location Accessory**:
A Windows-hosted Bluetooth endpoint intended to supply an Accessory Feed directly to Core Location. Acceptance requires Accessory Attribution with USB disconnected and without using Location Override; visibility in iOS Bluetooth settings is desirable but optional.
_Avoid_: Bluetooth server, Bluetooth Location Emulation, Bluetooth GPS override

**Accessory Feed Session**:
The live relationship during which Sky Walker supplies accessory-attributed location samples to the iPhone. Ending it stops the feed but does not promise that iOS immediately returns to its internal location source.
_Avoid_: Session, Bluetooth session, override session

**Stop Feed**:
Ending an Accessory Feed without claiming to clear Core Location or force iOS back to its internal GPS.
_Avoid_: Clear, revert, restore

**MFi Simulation Bridge**:
An optional MFi-certified external GPS accessory that accepts host-supplied test locations and presents them to iOS as accessory-produced location data.
_Avoid_: Bluetooth emulator, GPS dongle

**Source Probe**:
A minimal iOS test app that records location updates exactly as Core Location delivers them, including missing source metadata. It never creates replacement locations of its own.
_Avoid_: GPS simulator, location injector

**Accessory Attribution**:
Core Location's assertion that a delivered location came from an external accessory, evidenced by `isProducedByAccessory == true` on a Source Probe callback.
_Avoid_: not simulated, Bluetooth location

**Source Test Session**:
One labeled capture of Core Location callbacks from exactly one intended location source under a recorded device and connection setup.
_Avoid_: test run, log file

**Probe Verdict**:
The evidence result for one Source Test Session: pass, fail, or inconclusive. Inconclusive means the evidence cannot support either conclusion, not that the tested source failed.
_Avoid_: test result, unknown failure

**Experiment Verdict**:
The bounded BLE LNS hypothesis result across preserved Probe Verdicts: confirmed after one strict pass, rejected after three distinct sessions without a pass, or inconclusive while more attempts remain.
_Avoid_: Probe Verdict, final test result

**Teleport**:
Setting the override to a single static coordinate and holding it there. The MVP capability.
_Avoid_: jump, set point

**Route Playback**:
Moving the override along an ordered path of Waypoints so the device appears to travel, rather than holding one point. Distinct from Teleport.
_Avoid_: simulate movement, drive, track

**Waypoint**:
One of the ordered points that define a Route Playback path. The path is traversed as a Round Trip.
_Avoid_: node, marker, stop

**Round Trip**:
One complete out-and-back traversal of the Waypoints, returning to the start (e.g. A→B→C→B→A). The unit that Route Playback's loop count counts.
_Avoid_: lap, cycle, loop (as the noun for a single pass), ping-pong

**Movement Speed**:
The ground speed at which the simulated position advances between Waypoints during Route Playback.
_Avoid_: velocity, pace, rate

**Saved Path**:
A named, persisted ordered set of Waypoints the user can reload for Route Playback.
_Avoid_: route, preset, favorite

**Joystick Mode**:
Driving the override live with the keyboard arrow keys: hold a key and the device walks in that compass direction (↑ north, ↓ south, ← west, → east) at the Movement Speed, releasing stops it. A third mode beside Teleport and Route Playback, and mutually exclusive with them.
_Avoid_: manual mode, drive mode, WASD

**Heading**:
The current Joystick direction, expressed as a (north, east) vector. A zero Heading holds position. Two keys combine into a diagonal Heading that still covers Movement Speed (not √2× it).
_Avoid_: bearing, course, angle

**Walker**:
The background driver of Joystick Mode: it advances the device each tick from the current Heading and Movement Speed. Analogous to Route Playback's player, but its direction is mutable mid-run rather than a fixed Waypoint stream.
_Avoid_: joystick driver, mover, walker thread

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

**USB Trust Pairing**:
The trusted USB relationship between host and device, established by accepting "Trust This Computer" on the iPhone. Required before the host can drive the device.
_Avoid_: Pairing, Bluetooth Pairing

**Bluetooth Pairing**:
The wireless trust relationship between the iPhone and an external GPS accessory. It is unrelated to USB Trust Pairing.
_Avoid_: Pairing, Trust This Computer

**Tunnel**:
The encrypted USB channel (CoreDeviceProxy / RemoteXPC) that iOS 17.4+ requires to reach developer services such as Location Override. On the supported iOS bands this is established in userspace with no administrator rights.
