"""Interactive Mode — the tool's primary and only mode of operation.

See docs/adr/0002. One foreground process opens a single Tunnel, teleports to
the Default Location, then stays live: the user types new coordinates and the
device re-teleports over the same connection until they `clear` or `exit`.
Leaving (any way, including a crash) reverts the device to its real GPS.
"""

from __future__ import annotations

from sky_walker.config import DEFAULT_LOCATION, parse_coordinate
from sky_walker.device import Device, select_device
from sky_walker.location import LocationOverride

_HELP = """\
Commands:
  <lat>, <lng>   teleport the device to a coordinate (e.g. 25.03, 121.56)
  clear          release the override; device returns to its real GPS
  help           show this help
  exit / quit    clear and leave
"""


def run_interactive(udid: str | None = None) -> int:
    """Entry point for the default (no-subcommand) invocation."""
    device: Device = select_device(udid)
    supported, reason = device.check_supported()
    if not supported:
        print(f"Device not supported: {reason}")
        return 1

    print(f"Connected: {device.udid}  (iOS {device.ios_version})")
    print("Opening tunnel and holding the override in the foreground.")
    print("Type 'help' for commands, 'exit' to leave (device reverts on exit).\n")

    # The context manager owns the Session: it clears and tears down on exit,
    # so Ctrl-C / crash / quit all revert the phone. (ADR-0002)
    with LocationOverride(device) as override:
        # Prime the Default Location — one Enter accepts it.
        prompt = f"coordinate [{DEFAULT_LOCATION}]: "
        _teleport_from(override, input(prompt).strip() or str(DEFAULT_LOCATION))

        while True:
            try:
                line = input("sky-walker> ").strip()
            except EOFError:
                print()
                break

            if not line:
                continue
            low = line.lower()
            if low in ("exit", "quit"):
                break
            if low == "help":
                print(_HELP)
                continue
            if low == "clear":
                override.clear()
                print("Override cleared — device is back on its real GPS.")
                continue
            _teleport_from(override, line)

    print("Left interactive mode; device reverted to its real GPS.")
    return 0


def _teleport_from(override: LocationOverride, text: str) -> None:
    try:
        coord = parse_coordinate(text)
    except ValueError as exc:
        print(f"  ! {exc}")
        return
    override.teleport(coord)
    print(f"  -> teleported to {coord}")
