"""Public command-surface tests for the BLE LNS spike."""

from __future__ import annotations

import json

import pytest

from sky_walker.cli import main


def test_ble_spike_doctor_reports_supported_adapter(capsys, monkeypatch):
    from sky_walker.ble_lns import cli as ble_cli
    from sky_walker.ble_lns.model import AdapterCapabilities

    monkeypatch.setattr(
        ble_cli,
        "detect_capabilities",
        lambda: AdapterCapabilities(
            adapter_name="TP-Link Bluetooth 5.4 USB Adapter",
            low_energy_supported=True,
            peripheral_role_supported=True,
        ),
    )

    exit_code = main(["ble-spike", "doctor"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "TP-Link Bluetooth 5.4 USB Adapter" in output
    assert "Bluetooth LE: supported" in output
    assert "Peripheral role: supported" in output


def test_ble_spike_doctor_rejects_adapter_without_peripheral_role(
    capsys, monkeypatch
):
    from sky_walker.ble_lns import cli as ble_cli
    from sky_walker.ble_lns.model import AdapterCapabilities

    monkeypatch.setattr(
        ble_cli,
        "detect_capabilities",
        lambda: AdapterCapabilities(
            adapter_name="Central-only adapter",
            low_energy_supported=True,
            peripheral_role_supported=False,
        ),
    )

    exit_code = main(["ble-spike", "doctor"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "Peripheral role: unsupported" in output
    assert "replace the Bluetooth adapter" in output


def test_ble_spike_run_publishes_static_location_and_transport_trace(
    tmp_path, capsys, monkeypatch
):
    from sky_walker.accessory_probe.usb import AppleUsbEvidence
    from sky_walker.ble_lns import cli as ble_cli
    from sky_walker.ble_lns.model import PeripheralStatus

    class FakePeripheral:
        def __init__(self):
            self.published = []
            self.stopped = False

        def start(self):
            return PeripheralStatus.ADVERTISING

        def publish(self, coordinate):
            self.published.append(coordinate)
            return 1

        def stop(self):
            self.stopped = True

        def status(self):
            return PeripheralStatus.SUBSCRIBED

    class FakeClock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    peripheral = FakePeripheral()
    clock = FakeClock()
    monkeypatch.setattr(ble_cli, "create_peripheral", lambda: peripheral)
    monkeypatch.setattr(
        ble_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )
    monkeypatch.setattr(ble_cli, "monotonic", clock.monotonic)
    monkeypatch.setattr(ble_cli, "sleep", clock.sleep)

    exit_code = main([
        "ble-spike",
        "run",
        "--session-id",
        "ABCD2345",
        "--latitude",
        "1",
        "--longitude",
        "-1",
        "--duration",
        "2",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 0
    assert peripheral.stopped is True
    assert [(item.latitude, item.longitude) for item in peripheral.published] == [
        (1.0, -1.0),
        (1.0, -1.0),
    ]
    trace_path = tmp_path / "ABCD2345.ble-trace.jsonl"
    records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        record["record_type"] == "peripheral"
        and record["status"] == "subscribed"
        for record in records
    )
    assert sum(record["record_type"] == "sample" for record in records) == 2
    usb_records = [record for record in records if record["record_type"] == "usb"]
    assert usb_records
    assert {record["status"] for record in usb_records} == {"absent"}
    output = capsys.readouterr().out
    assert "Advertising" in output
    assert "subscribed" in output
    assert "Trace:" in output


def test_ble_spike_disconnect_makes_session_inconclusive(
    tmp_path, capsys, monkeypatch
):
    from sky_walker.accessory_probe.usb import AppleUsbEvidence
    from sky_walker.ble_lns import cli as ble_cli
    from sky_walker.ble_lns.model import PeripheralStatus

    class FakePeripheral:
        status_calls = 0

        def start(self):
            return PeripheralStatus.ADVERTISING

        def publish(self, coordinate):
            return 1

        def stop(self):
            pass

        def status(self):
            self.status_calls += 1
            if self.status_calls == 1:
                return PeripheralStatus.SUBSCRIBED
            return PeripheralStatus.DISCONNECTED

    class FakeClock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = FakeClock()
    monkeypatch.setattr(ble_cli, "create_peripheral", FakePeripheral)
    monkeypatch.setattr(
        ble_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )
    monkeypatch.setattr(ble_cli, "monotonic", clock.monotonic)
    monkeypatch.setattr(ble_cli, "sleep", clock.sleep)

    exit_code = main([
        "ble-spike",
        "run",
        "--session-id",
        "ABCD2345",
        "--latitude",
        "1",
        "--longitude",
        "-1",
        "--duration",
        "2",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 2
    assert "inconclusive" in capsys.readouterr().out


def test_ble_spike_interrupt_stops_feed_without_claiming_location_revert(
    tmp_path, capsys, monkeypatch
):
    from sky_walker.accessory_probe.usb import AppleUsbEvidence
    from sky_walker.ble_lns import cli as ble_cli
    from sky_walker.ble_lns.model import PeripheralStatus

    class FakePeripheral:
        stopped = False

        def start(self):
            return PeripheralStatus.ADVERTISING

        def publish(self, coordinate):
            return 1

        def stop(self):
            self.stopped = True

        def status(self):
            return PeripheralStatus.SUBSCRIBED

    peripheral = FakePeripheral()
    monkeypatch.setattr(ble_cli, "create_peripheral", lambda: peripheral)
    monkeypatch.setattr(
        ble_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )
    monkeypatch.setattr(ble_cli, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        ble_cli,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    exit_code = main([
        "ble-spike",
        "run",
        "--session-id",
        "ABCD2345",
        "--latitude",
        "1",
        "--longitude",
        "-1",
        "--duration",
        "2",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 130
    assert peripheral.stopped is True
    output = capsys.readouterr().out
    assert "Accessory Feed stopped" in output
    assert "real GPS" not in output


def test_ble_spike_does_not_overwrite_existing_session_trace(
    tmp_path, capsys
):
    trace_path = tmp_path / "ABCD2345.ble-trace.jsonl"
    trace_path.write_text("preserve-me\n", encoding="utf-8")

    exit_code = main([
        "ble-spike",
        "run",
        "--session-id",
        "ABCD2345",
        "--latitude",
        "1",
        "--longitude",
        "-1",
        "--duration",
        "2",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 3
    assert trace_path.read_text(encoding="utf-8") == "preserve-me\n"
    assert "already exists" in capsys.readouterr().out


def test_ble_spike_late_subscription_does_not_burst_missed_samples(
    tmp_path, monkeypatch
):
    from sky_walker.accessory_probe.usb import AppleUsbEvidence
    from sky_walker.ble_lns import cli as ble_cli
    from sky_walker.ble_lns.model import PeripheralStatus

    class FakeClock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = FakeClock()

    class FakePeripheral:
        published_at = []

        def start(self):
            return PeripheralStatus.ADVERTISING

        def publish(self, coordinate):
            self.published_at.append(clock.now)
            return 1

        def stop(self):
            pass

        def status(self):
            if clock.now < 2.0:
                return PeripheralStatus.ADVERTISING
            return PeripheralStatus.SUBSCRIBED

    peripheral = FakePeripheral()
    monkeypatch.setattr(ble_cli, "create_peripheral", lambda: peripheral)
    monkeypatch.setattr(
        ble_cli,
        "detect_apple_usb",
        lambda: AppleUsbEvidence(status="absent", device_count=0),
    )
    monkeypatch.setattr(ble_cli, "monotonic", clock.monotonic)
    monkeypatch.setattr(ble_cli, "sleep", clock.sleep)

    exit_code = main([
        "ble-spike",
        "run",
        "--session-id",
        "ABCD2345",
        "--latitude",
        "1",
        "--longitude",
        "-1",
        "--duration",
        "4.5",
        "--output-dir",
        str(tmp_path),
    ])

    assert exit_code == 0
    assert len(peripheral.published_at) == 3
    assert all(
        right - left >= 1.0
        for left, right in zip(
            peripheral.published_at, peripheral.published_at[1:]
        )
    )


def test_windows_peripheral_disconnect_is_terminal_for_one_session():
    from sky_walker.ble_lns.model import PeripheralStatus
    from sky_walker.ble_lns.windows import WindowsLnsPeripheral

    class Sender:
        subscribed_clients = [object()]

    sender = Sender()
    peripheral = WindowsLnsPeripheral()
    peripheral._on_subscribed_clients_changed(sender, None)
    assert peripheral.status() is PeripheralStatus.SUBSCRIBED

    sender.subscribed_clients = []
    peripheral._on_subscribed_clients_changed(sender, None)
    assert peripheral.status() is PeripheralStatus.DISCONNECTED

    sender.subscribed_clients = [object()]
    peripheral._on_subscribed_clients_changed(sender, None)
    assert peripheral.status() is PeripheralStatus.DISCONNECTED


def test_windows_peripheral_notification_failure_is_terminal(monkeypatch):
    from sky_walker.ble_lns import windows
    from sky_walker.ble_lns.model import PeripheralStatus
    from sky_walker.ble_lns.windows import BleUnavailableError, WindowsLnsPeripheral
    from sky_walker.config import Coordinate

    class Status:
        name = "UNREACHABLE"

    class Result:
        status = Status()

    class Runner:
        def run(self, operation, timeout=10.0):
            return [Result()]

    class Characteristic:
        def notify_value_async(self, payload):
            return object()

    peripheral = WindowsLnsPeripheral()
    peripheral._runner = Runner()
    peripheral._location_characteristic = Characteristic()
    monkeypatch.setattr(windows, "_buffer_from_bytes", lambda value: value)

    with pytest.raises(BleUnavailableError, match="notification failed"):
        peripheral.publish(Coordinate(latitude=1.0, longitude=2.0))

    assert peripheral.status() is PeripheralStatus.ERROR
