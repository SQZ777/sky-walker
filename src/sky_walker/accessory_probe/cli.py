"""Command handlers for the experimental Accessory Probe surface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sky_walker.accessory_probe import SCENARIOS
from sky_walker.accessory_probe.session import create_session
from sky_walker.accessory_probe.usb import AppleUsbEvidence, detect_apple_usb
from sky_walker.accessory_probe.validator import ProbeInputError, validate_files
from sky_walker.config import DEFAULT_LOCATION, parse_coordinate


_SCENARIO_STEPS = {
    "real-gps": "Disable Sky Walker and iAnyGo; use the iPhone's internal location source.",
    "sky-walker-usb": "Connect USB and start a Sky Walker Location Override at the manifest coordinate.",
    "ianygo-general": "Start iAnyGo General Mode at the manifest coordinate using its documented workflow.",
    "ianygo-bluetooth": "Pair iPhone with this PC, start iAnyGo Bluetooth Game Mode, and keep USB unplugged.",
}


def add_probe_parser(subparsers: argparse._SubParsersAction) -> None:
    probe = subparsers.add_parser(
        "probe",
        help="Create and validate experimental Core Location source evidence.",
    )
    actions = probe.add_subparsers(dest="probe_action", required=True)
    new = actions.add_parser("new", help="Create a Source Test Session manifest.")
    new.add_argument("scenario", choices=SCENARIOS)
    new.add_argument("--ios-version", required=True)
    new.add_argument("--probe-build", required=True)
    new.add_argument("--location-product-version")
    new.add_argument("--bluetooth-adapter")
    new.add_argument("--confirm-usb-disconnected", action="store_true")
    new.add_argument("--latitude", type=float, default=DEFAULT_LOCATION.latitude)
    new.add_argument("--longitude", type=float, default=DEFAULT_LOCATION.longitude)
    new.add_argument("--output-dir", type=Path, default=Path("artifacts/probe-runs"))
    validate = actions.add_parser("validate", help="Validate a manifest and Source Probe JSONL.")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("jsonl", type=Path)


def run(args: argparse.Namespace) -> int:
    if args.probe_action == "new":
        try:
            expected_location = parse_coordinate(f"{args.latitude}, {args.longitude}")
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3
        missing = []
        if args.scenario in ("ianygo-general", "ianygo-bluetooth"):
            if not args.location_product_version:
                missing.append("--location-product-version")
        if args.scenario == "ianygo-bluetooth":
            if not args.bluetooth_adapter:
                missing.append("--bluetooth-adapter")
            if not args.confirm_usb_disconnected:
                missing.append("--confirm-usb-disconnected")
        if missing:
            print(
                "Error: this scenario requires " + ", ".join(missing),
                file=sys.stderr,
            )
            return 3
        usb_evidence = AppleUsbEvidence(status="not-required", device_count=0)
        user_confirmation = None
        if args.scenario == "ianygo-bluetooth":
            usb_evidence = detect_apple_usb()
            user_confirmation = args.confirm_usb_disconnected
        path, manifest = create_session(
            scenario=args.scenario,
            ios_version=args.ios_version,
            source_probe_build=args.probe_build,
            output_dir=args.output_dir,
            expected_location=expected_location,
            location_product_version=args.location_product_version,
            bluetooth_adapter=args.bluetooth_adapter,
            user_confirmed_usb_disconnected=user_confirmation,
            windows_apple_usb_status=usb_evidence.status,
            windows_apple_usb_device_count=usb_evidence.device_count,
        )
        print(f"Source Test Session: {manifest['session_id']}")
        print(f"Manifest: {path}")
        print("On the iPhone, open Source Probe and enter this Session ID.")
        print(_SCENARIO_STEPS[args.scenario])
        if args.scenario == "ianygo-bluetooth":
            print("Keep every physical Apple USB cable unplugged for the entire capture.")
        print("Capture Core Location callbacks for up to 120 seconds, then export the JSONL file.")
        return 0
    if args.probe_action == "validate":
        try:
            result = validate_files(args.manifest, args.jsonl)
        except ProbeInputError as exc:
            print(json.dumps({
                "schema_version": 1,
                "verdict": "invalid",
                "errors": [str(exc)],
            }))
            print(f"INVALID: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(result.as_dict()))
        print(
            f"{result.verdict.upper()}: {result.eligible_location_records} eligible "
            f"of {result.total_location_records} location records",
            file=sys.stderr,
        )
        return {"pass": 0, "fail": 1, "inconclusive": 2}[result.verdict]
    raise AssertionError("unhandled probe command")
