"""Domain values shared by the BLE command and Windows adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class AdapterCapabilities:
    adapter_name: str
    low_energy_supported: bool
    peripheral_role_supported: bool

    @property
    def supported(self) -> bool:
        return self.low_energy_supported and self.peripheral_role_supported


class PeripheralStatus(str, Enum):
    STOPPED = "stopped"
    ADVERTISING = "advertising"
    SUBSCRIBED = "subscribed"
    DISCONNECTED = "disconnected"
    ERROR = "error"
