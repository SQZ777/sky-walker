"""Command-line surface (see docs/adr/0002 and CONTEXT.md).

    sky-walker              -> Interactive Mode (the main use)
    sky-walker doctor       -> environment self-check
    sky-walker clear        -> emergency one-shot revert to real GPS

--udid is global and selects a device when more than one is connected.
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from sky_walker import __version__
from sky_walker.errors import SkyWalkerError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sky-walker",
        description="Override a USB-connected iPhone's GPS location for app testing.",
    )
    parser.add_argument("--version", action="version", version=f"sky-walker {__version__}")
    parser.add_argument("--udid", help="Target device UDID (needed only if several are connected).")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="Check that every prerequisite for a session is met.")
    sub.add_parser("clear", help="Release any active override and return to real GPS.")
    # No subcommand => interactive mode (handled in main()).
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "doctor":
            from sky_walker import doctor
            return doctor.run(args.udid)
        if args.command == "clear":
            from sky_walker.location import clear_once
            clear_once(args.udid)
            print("Override cleared — device is back on its real GPS.")
            return 0
        # Default: interactive mode.
        from sky_walker.interactive import run_interactive
        return run_interactive(args.udid)
    except SkyWalkerError as exc:
        print(f"Error: {exc}")
        if exc.hint:
            print(f"  -> {exc.hint}")
        return 1
    except KeyboardInterrupt:
        # ADR-0002: leaving the process reverts the device. Nothing else to do.
        print("\nInterrupted; device reverted to its real GPS.")
        return 130
