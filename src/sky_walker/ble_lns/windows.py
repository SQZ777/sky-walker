"""Lazy PyWinRT boundary for the active Windows Bluetooth adapter.

The module deliberately contains the entire PyWinRT surface used by the spike.
Nothing in this package imports the USB/DVT location backend.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Coroutine, Optional, TypeVar

from sky_walker.ble_lns.codec import encode_location_and_speed
from sky_walker.ble_lns.model import AdapterCapabilities, PeripheralStatus
from sky_walker.config import Coordinate


_T = TypeVar("_T")
_LN_FEATURE = (1 << 2) | (1 << 20)


class BleUnavailableError(RuntimeError):
    """Windows cannot provide the BLE capability required by the spike."""


class _AsyncRunner:
    """Keep one event loop alive for the lifetime of a local GATT service."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            name="sky-walker-ble",
            daemon=True,
        )
        self._thread.start()

    def run(self, coroutine: Coroutine[Any, Any, _T], timeout: float = 10.0) -> _T:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise BleUnavailableError("Windows Bluetooth operation timed out") from exc

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)


def _buffer_from_bytes(value: bytes):
    try:
        from winrt.windows.storage.streams import DataWriter
    except ImportError as exc:
        raise BleUnavailableError(
            "PyWinRT Bluetooth support is not installed; "
            "run 'pip install -e .[bluetooth]'"
        ) from exc

    writer = DataWriter()
    writer.write_bytes(value)
    return writer.detach_buffer()


def detect_capabilities() -> AdapterCapabilities:
    return asyncio.run(_detect_capabilities())


async def _detect_capabilities() -> AdapterCapabilities:
    try:
        from winrt.windows.devices.bluetooth import BluetoothAdapter
        from winrt.windows.devices.enumeration import DeviceInformation
    except ImportError as exc:
        raise BleUnavailableError(
            "PyWinRT Bluetooth support is not installed; "
            "run 'pip install -e .[bluetooth]'"
        ) from exc

    adapter = await BluetoothAdapter.get_default_async()
    if adapter is None:
        raise BleUnavailableError("Windows has no default Bluetooth adapter")
    information = await DeviceInformation.create_from_id_async(adapter.device_id)
    return AdapterCapabilities(
        adapter_name=information.name or adapter.device_id,
        low_energy_supported=bool(adapter.is_low_energy_supported),
        peripheral_role_supported=bool(adapter.is_peripheral_role_supported),
    )


class WindowsLnsPeripheral:
    """Publish the Bluetooth SIG Location and Navigation Service on Windows."""

    def __init__(self) -> None:
        self._runner: Optional[_AsyncRunner] = None
        self._provider: Any = None
        self._location_characteristic: Any = None
        self._subscription_token: Any = None
        self._advertisement_token: Any = None
        self._status = PeripheralStatus.STOPPED
        self._status_lock = threading.Lock()
        self._ever_subscribed = False
        self._advertisement_error: Optional[str] = None

    def start(self) -> PeripheralStatus:
        if self.status() is not PeripheralStatus.STOPPED:
            raise BleUnavailableError("BLE LNS peripheral is already running")
        capabilities = detect_capabilities()
        if not capabilities.supported:
            raise BleUnavailableError(
                "active Bluetooth adapter does not support the BLE peripheral role"
            )
        self._ever_subscribed = False
        self._advertisement_error = None
        self._runner = _AsyncRunner()
        try:
            self._runner.run(self._create_and_advertise())
        except Exception:
            self.stop()
            raise
        return self.status()

    def publish(self, coordinate: Coordinate) -> int:
        if self._runner is None or self._location_characteristic is None:
            raise BleUnavailableError("BLE LNS peripheral is not running")
        payload = _buffer_from_bytes(encode_location_and_speed(coordinate))
        results = self._runner.run(
            self._location_characteristic.notify_value_async(payload),
            timeout=5.0,
        )
        failures = [
            result
            for result in results
            if getattr(result.status, "name", None) != "SUCCESS"
        ]
        if failures:
            self._set_status(PeripheralStatus.ERROR)
            statuses = ", ".join(result.status.name for result in failures)
            raise BleUnavailableError(f"LNS notification failed: {statuses}")
        if not results:
            self._set_status(PeripheralStatus.DISCONNECTED)
            raise BleUnavailableError("LNS notification reached no subscribers")
        return len(results)

    def stop(self) -> None:
        runner = self._runner
        provider = self._provider
        characteristic = self._location_characteristic
        if characteristic is not None and self._subscription_token is not None:
            characteristic.remove_subscribed_clients_changed(
                self._subscription_token
            )
        if provider is not None and self._advertisement_token is not None:
            provider.remove_advertisement_status_changed(self._advertisement_token)
        if provider is not None:
            provider.stop_advertising()
        self._subscription_token = None
        self._advertisement_token = None
        self._location_characteristic = None
        self._provider = None
        self._runner = None
        if runner is not None:
            runner.close()
        self._set_status(PeripheralStatus.STOPPED)

    def status(self) -> PeripheralStatus:
        with self._status_lock:
            return self._status

    async def _create_and_advertise(self) -> None:
        try:
            from winrt.windows.devices.bluetooth import BluetoothError
            from winrt.windows.devices.bluetooth.genericattributeprofile import (
                GattCharacteristicProperties,
                GattCharacteristicUuids,
                GattLocalCharacteristicParameters,
                GattProtectionLevel,
                GattServiceProvider,
                GattServiceProviderAdvertisementStatus,
                GattServiceProviderAdvertisingParameters,
                GattServiceUuids,
            )
        except ImportError as exc:
            raise BleUnavailableError(
                "PyWinRT Bluetooth support is not installed; "
                "run 'pip install -e .[bluetooth]'"
            ) from exc

        provider_result = await GattServiceProvider.create_async(
            GattServiceUuids.location_and_navigation
        )
        if provider_result.error != BluetoothError.SUCCESS:
            raise BleUnavailableError(
                f"could not create LNS service: {provider_result.error.name}"
            )
        provider = provider_result.service_provider

        feature_parameters = GattLocalCharacteristicParameters()
        feature_parameters.characteristic_properties = (
            GattCharacteristicProperties.READ
        )
        feature_parameters.read_protection_level = GattProtectionLevel.PLAIN
        feature_parameters.static_value = _buffer_from_bytes(
            _LN_FEATURE.to_bytes(4, "little")
        )
        feature_result = await provider.service.create_characteristic_async(
            GattCharacteristicUuids.ln_feature,
            feature_parameters,
        )
        if feature_result.error != BluetoothError.SUCCESS:
            raise BleUnavailableError(
                f"could not create LN Feature characteristic: "
                f"{feature_result.error.name}"
            )

        location_parameters = GattLocalCharacteristicParameters()
        location_parameters.characteristic_properties = (
            GattCharacteristicProperties.NOTIFY
        )
        location_result = await provider.service.create_characteristic_async(
            GattCharacteristicUuids.location_and_speed,
            location_parameters,
        )
        if location_result.error != BluetoothError.SUCCESS:
            raise BleUnavailableError(
                f"could not create Location and Speed characteristic: "
                f"{location_result.error.name}"
            )

        self._provider = provider
        self._location_characteristic = location_result.characteristic
        self._subscription_token = (
            self._location_characteristic.add_subscribed_clients_changed(
                self._on_subscribed_clients_changed
            )
        )
        self._advertisement_token = provider.add_advertisement_status_changed(
            self._on_advertisement_status_changed
        )
        advertising = GattServiceProviderAdvertisingParameters()
        advertising.is_connectable = True
        advertising.is_discoverable = True
        provider.start_advertising_with_parameters(advertising)
        started_statuses = (
            GattServiceProviderAdvertisementStatus.STARTED,
            GattServiceProviderAdvertisementStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA,
        )
        for _ in range(30):
            if provider.advertisement_status in started_statuses:
                break
            await asyncio.sleep(0.1)
        if provider.advertisement_status not in started_statuses:
            raise BleUnavailableError(
                f"LNS advertising did not start: "
                f"{provider.advertisement_status.name}"
                + (
                    f" ({self._advertisement_error})"
                    if self._advertisement_error is not None
                    else ""
                )
            )
        self._set_status(PeripheralStatus.ADVERTISING)

    def _on_subscribed_clients_changed(self, sender: Any, _args: Any) -> None:
        if len(sender.subscribed_clients) > 0:
            self._ever_subscribed = True
            self._set_status(PeripheralStatus.SUBSCRIBED)
        elif self._ever_subscribed:
            self._set_status(PeripheralStatus.DISCONNECTED)
        else:
            self._set_status(PeripheralStatus.ADVERTISING)

    def _on_advertisement_status_changed(self, _sender: Any, args: Any) -> None:
        try:
            from winrt.windows.devices.bluetooth import BluetoothError
            from winrt.windows.devices.bluetooth.genericattributeprofile import (
                GattServiceProviderAdvertisementStatus,
            )
        except ImportError:
            self._set_status(PeripheralStatus.ERROR)
            return
        if args.error is not BluetoothError.SUCCESS:
            self._advertisement_error = args.error.name
            self._set_status(PeripheralStatus.ERROR)
        elif args.status in (
            GattServiceProviderAdvertisementStatus.STARTED,
            GattServiceProviderAdvertisementStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA,
        ) and self.status() is not PeripheralStatus.SUBSCRIBED:
            self._set_status(PeripheralStatus.ADVERTISING)
        elif args.status is GattServiceProviderAdvertisementStatus.ABORTED:
            # Windows can transiently report ABORTED/SUCCESS before STARTED;
            # _create_and_advertise applies the bounded terminal check.
            self._advertisement_error = args.error.name

    def _set_status(self, status: PeripheralStatus) -> None:
        with self._status_lock:
            if (
                self._status
                in {PeripheralStatus.DISCONNECTED, PeripheralStatus.ERROR}
                and status is not PeripheralStatus.STOPPED
            ):
                return
            self._status = status
