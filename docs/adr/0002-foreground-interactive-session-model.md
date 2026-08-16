# Hold the override in a single foreground process with an interactive re-teleport loop

## Context

A Location Override is live only while its connection is held: pymobiledevice3's `simulate-location set` deliberately does not self-exit — it holds the session open and reverts the device the moment the process ends or is Ctrl-C'd. So "keep the phone teleported" is not a one-shot write; something has to stay alive. We also want to change the location repeatedly while testing (set a point, watch the app, move, watch again).

## Decision

Run Sky Walker as a **single foreground process** that opens one Tunnel, teleports to the Default Location, and then stays live as an **Interactive Mode** prompt: the user types new coordinates and the device re-teleports **over the same tunnel**, until they `clear` or `exit`. Ending the process (exit, `clear`, Ctrl-C, or a crash) returns the device to its real GPS.

## Considered Options

- **Background daemon** (`set` returns immediately, a separate `clear` stops it) — better for CI, but adds process-lifecycle management, orphaned sessions, and "I thought it was cleared but it's still overriding" ghost states. Deferred until a real CI need exists.
- **One-shot command, re-run to move** — simplest to build, but every move means tearing down and re-establishing the tunnel, which is slow and clumsy for interactive testing.

## Consequences

- The held-session-equals-persistence behaviour becomes a **feature**: a crash or unplugged cable auto-reverts the device, so tests can't leave a phone stuck on a fake location.
- Re-teleporting on one live tunnel is only clean because we drive pymobiledevice3 **as a library** (ADR-0001); a CLI-subprocess foundation would fight this model.
- Not suited to unattended/automated runs as-is; the background-daemon option is the documented upgrade path when CI is on the table.
