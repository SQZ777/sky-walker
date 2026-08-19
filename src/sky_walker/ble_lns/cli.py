"""Experimental BLE LNS command surface."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Optional

from sky_walker.accessory_probe.usb import AppleUsbEvidence
from sky_walker.accessory_probe.ble_trace import TraceRecordType
from sky_walker.ble_lns.model import AdapterCapabilities, PeripheralStatus
from sky_walker.ble_lns.peripheral import BleLnsPeripheral
from sky_walker.ble_lns.trace import BleTraceWriter
from sky_walker.config import Coordinate, parse_coordinate
from sky_walker.ble_lns.windows import BleUnavailableError


def add_ble_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "ble-spike",
        help="Run the experimental Windows BLE LNS feasibility spike.",
    )
    actions = parser.add_subparsers(dest="ble_action", required=True)
    actions.add_parser(
        "doctor",
        help="Check whether the active adapter can publish a BLE peripheral.",
    )
    run_parser = actions.add_parser(
        "run",
        help="Advertise LNS and publish one static coordinate at 1 Hz.",
    )
    run_parser.add_argument("--session-id", required=True)
    run_parser.add_argument("--latitude", type=float, required=True)
    run_parser.add_argument("--longitude", type=float, required=True)
    run_parser.add_argument("--duration", type=float, default=120.0)
    run_parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/probe-runs")
    )


def detect_capabilities() -> AdapterCapabilities:
    from sky_walker.ble_lns.windows import detect_capabilities as detect

    return detect()


def create_peripheral() -> BleLnsPeripheral:
    from sky_walker.ble_lns.windows import WindowsLnsPeripheral

    return WindowsLnsPeripheral()


def detect_apple_usb() -> AppleUsbEvidence:
    from sky_walker.accessory_probe.usb import detect_apple_usb as detect

    return detect()


def monotonic() -> float:
    return time.monotonic()


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def run(args: argparse.Namespace) -> int:
    if args.ble_action == "run":
        return _run_feed(args)
    if args.ble_action != "doctor":
        raise AssertionError("unhandled BLE spike command")
    try:
        capabilities = detect_capabilities()
    except BleUnavailableError as exc:
        print(f"Bluetooth unavailable: {exc}")
        return 1

    print(f"Adapter: {capabilities.adapter_name}")
    print(
        "Bluetooth LE: "
        + ("supported" if capabilities.low_energy_supported else "unsupported")
    )
    print(
        "Peripheral role: "
        + ("supported" if capabilities.peripheral_role_supported else "unsupported")
    )
    if not capabilities.supported:
        print("Cannot run the LNS spike; replace the Bluetooth adapter and retry.")
        return 1
    return 0


def _run_feed(args: argparse.Namespace) -> int:
    if args.udid is not None:
        print("BLE spike does not accept --udid; USB Location Override is separate.")
        return 3
    session_id = args.session_id.strip().upper()
    if re.fullmatch(r"[A-Z2-9]{8}", session_id) is None:
        print("Session ID must be eight characters from A-Z or 2-9.")
        return 3
    if not 0 < args.duration <= 120:
        print("Duration must be greater than zero and no more than 120 seconds.")
        return 3
    try:
        coordinate = parse_coordinate(f"{args.latitude}, {args.longitude}")
    except ValueError as exc:
        print(f"Invalid coordinate: {exc}")
        return 3

    try:
        trace = BleTraceWriter(
            args.output_dir / f"{session_id}.ble-trace.jsonl", session_id
        )
    except FileExistsError:
        print(
            f"Trace already exists for session {session_id}; "
            "use a new Source Test Session."
        )
        return 3
    peripheral = create_peripheral()
    last_status: PeripheralStatus | None = None
    published = 0
    exit_code = 0
    try:
        last_status = peripheral.start()
        trace.write(TraceRecordType.PERIPHERAL, status=last_status.value)
        print("Advertising BLE LNS; waiting for an iPhone collector subscription.")
        started = monotonic()
        deadline = started + args.duration
        next_publish: Optional[float] = None
        next_usb_sample = started
        while monotonic() < deadline:
            now = monotonic()
            if now >= next_usb_sample:
                usb = detect_apple_usb()
                trace.write(
                    TraceRecordType.USB,
                    status=usb.status,
                    device_count=usb.device_count,
                )
                next_usb_sample += 1.0
                if usb.status != "absent":
                    print(f"USB guard stopped the feed: Apple USB status is {usb.status}.")
                    exit_code = 2
                    break

            status = peripheral.status()
            if status != last_status:
                trace.write(TraceRecordType.PERIPHERAL, status=status.value)
                last_status = status
                print(f"BLE peripheral status: {status.value}")
            if status in (PeripheralStatus.DISCONNECTED, PeripheralStatus.ERROR):
                print(f"BLE feed became {status.value}; this session is inconclusive.")
                exit_code = 2
                break
            if status is PeripheralStatus.SUBSCRIBED:
                if next_publish is None:
                    next_publish = now
                if now >= next_publish:
                    subscribers = peripheral.publish(coordinate)
                    published += 1
                    trace.write(
                        TraceRecordType.SAMPLE,
                        latitude=coordinate.latitude,
                        longitude=coordinate.longitude,
                        subscribed_clients=subscribers,
                    )
                    next_publish = now + 1.0
            else:
                next_publish = None
            sleep(min(0.1, max(0.0, deadline - monotonic())))
        if exit_code == 0 and published == 0:
            print("No LNS collector subscribed before the session ended.")
            exit_code = 1
    except KeyboardInterrupt:
        trace.write(TraceRecordType.INTERRUPTED)
        print("Interrupted; Bluetooth Accessory Feed stopped.")
        exit_code = 130
    except BleUnavailableError as exc:
        trace.write(TraceRecordType.ERROR, message=str(exc))
        print(f"Bluetooth unavailable: {exc}")
        exit_code = 1
    finally:
        peripheral.stop()
        trace.write(
            TraceRecordType.PERIPHERAL,
            status=PeripheralStatus.STOPPED.value,
        )
        trace.close()

    print(f"Trace: {trace.path}")
    return exit_code
