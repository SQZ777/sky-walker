"""Port implemented by the Windows GATT peripheral boundary."""

from __future__ import annotations

from typing import Protocol

from sky_walker.ble_lns.model import PeripheralStatus
from sky_walker.config import Coordinate


class BleLnsPeripheral(Protocol):
    def start(self) -> PeripheralStatus: ...

    def publish(self, coordinate: Coordinate) -> int: ...

    def stop(self) -> None: ...

    def status(self) -> PeripheralStatus: ...
