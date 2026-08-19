"""Command handlers for the experimental Accessory Probe surface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sky_walker.accessory_probe import SCENARIOS, scenario_definition
from sky_walker.accessory_probe.experiment import summarize_attempts
from sky_walker.accessory_probe.session import create_session
from sky_walker.accessory_probe.usb import AppleUsbEvidence, detect_apple_usb
from sky_walker.accessory_probe.validator import ProbeInputError, validate_files
from sky_walker.config import DEFAULT_LOCATION, parse_coordinate


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
    validate.add_argument(
        "--ble-trace",
        type=Path,
        help="Sky Walker BLE transport trace for a sky-walker-ble-lns session.",
    )
    validate.add_argument(
        "--output",
        type=Path,
        help="Preserve the machine-readable verdict without overwriting a file.",
    )
    summarize = actions.add_parser(
        "summarize",
        help="Summarize one to three preserved BLE LNS verdict JSON files.",
    )
    summarize.add_argument("verdicts", type=Path, nargs="+")


def run(args: argparse.Namespace) -> int:
    if args.probe_action == "new":
        scenario = scenario_definition(args.scenario)
        try:
            expected_location = parse_coordinate(f"{args.latitude}, {args.longitude}")
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 3
        missing = []
        if scenario.requires_location_product_version:
            if not args.location_product_version:
                missing.append("--location-product-version")
        if scenario.requires_usb_disconnection:
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
        if scenario.requires_usb_disconnection:
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
        print(scenario.operator_step)
        if scenario.requires_usb_disconnection:
            print("Keep every physical Apple USB cable unplugged for the entire capture.")
        print("Capture Core Location callbacks for up to 120 seconds, then export the JSONL file.")
        return 0
    if args.probe_action == "summarize":
        try:
            summary = summarize_attempts(args.verdicts)
        except ProbeInputError as exc:
            print(json.dumps({
                "schema_version": 1,
                "experiment_verdict": "invalid",
                "errors": [str(exc)],
            }))
            print(f"INVALID: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary.as_dict()))
        return {"confirmed": 0, "rejected": 1, "inconclusive": 2}[
            summary.experiment_verdict
        ]
    if args.probe_action == "validate":
        try:
            result = validate_files(
                args.manifest,
                args.jsonl,
                usb_detector=detect_apple_usb,
                ble_trace_path=args.ble_trace,
            )
        except ProbeInputError as exc:
            print(json.dumps({
                "schema_version": 1,
                "verdict": "invalid",
                "errors": [str(exc)],
            }))
            print(f"INVALID: {exc}", file=sys.stderr)
            return 3
        result_json = json.dumps(result.as_dict())
        if args.output is not None:
            try:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8", newline="\n") as file:
                    file.write(result_json + "\n")
            except OSError as exc:
                print(json.dumps({
                    "schema_version": 1,
                    "verdict": "invalid",
                    "errors": [f"cannot preserve verdict: {exc}"],
                }))
                print(f"INVALID: cannot preserve verdict: {exc}", file=sys.stderr)
                return 3
        print(result_json)
        print(
            f"{result.verdict.value.upper()}: "
            f"{result.eligible_callback_count} eligible callbacks; "
            f"{result.eligible_location_records} eligible of "
            f"{result.total_location_records} location records",
            file=sys.stderr,
        )
        return {"pass": 0, "fail": 1, "inconclusive": 2}[
            result.verdict.value
        ]
    raise AssertionError("unhandled probe command")
