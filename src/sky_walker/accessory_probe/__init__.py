"""Experimental evidence tooling for Core Location source attribution."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Union


SCHEMA_VERSION = 1


class Scenario(str, Enum):
    REAL_GPS = "real-gps"
    SKY_WALKER_USB = "sky-walker-usb"
    SKY_WALKER_BLE_LNS = "sky-walker-ble-lns"
    IANYGO_GENERAL = "ianygo-general"
    IANYGO_BLUETOOTH = "ianygo-bluetooth"


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario: Scenario
    operator_step: str
    requires_location_product_version: bool = False
    requires_usb_disconnection: bool = False
    default_location_product_version: Optional[str] = None
    uses_sky_walker_version: bool = False


SCENARIO_DEFINITIONS: Dict[Scenario, ScenarioDefinition] = {
    Scenario.REAL_GPS: ScenarioDefinition(
        scenario=Scenario.REAL_GPS,
        operator_step=(
            "Disable Sky Walker and iAnyGo; use the iPhone's internal location source."
        ),
        default_location_product_version="not-applicable",
    ),
    Scenario.SKY_WALKER_USB: ScenarioDefinition(
        scenario=Scenario.SKY_WALKER_USB,
        operator_step=(
            "Connect USB and start a Sky Walker Location Override at the manifest coordinate."
        ),
        uses_sky_walker_version=True,
    ),
    Scenario.SKY_WALKER_BLE_LNS: ScenarioDefinition(
        scenario=Scenario.SKY_WALKER_BLE_LNS,
        operator_step=(
            "Start the Sky Walker BLE LNS feed at the manifest coordinate, "
            "then keep USB unplugged."
        ),
        requires_usb_disconnection=True,
        uses_sky_walker_version=True,
    ),
    Scenario.IANYGO_GENERAL: ScenarioDefinition(
        scenario=Scenario.IANYGO_GENERAL,
        operator_step=(
            "Start iAnyGo General Mode at the manifest coordinate using its documented workflow."
        ),
        requires_location_product_version=True,
    ),
    Scenario.IANYGO_BLUETOOTH: ScenarioDefinition(
        scenario=Scenario.IANYGO_BLUETOOTH,
        operator_step=(
            "Pair iPhone with this PC, start iAnyGo Bluetooth Game Mode, and keep USB unplugged."
        ),
        requires_location_product_version=True,
        requires_usb_disconnection=True,
    ),
}

SCENARIOS = tuple(scenario.value for scenario in Scenario)


def scenario_definition(value: Union[str, Scenario]) -> ScenarioDefinition:
    """Return the single Python-side definition for a wire scenario value."""

    scenario = value if isinstance(value, Scenario) else Scenario(value)
    return SCENARIO_DEFINITIONS[scenario]
