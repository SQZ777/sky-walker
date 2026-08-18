"""Create Source Test Session manifests without touching Location Override."""

from __future__ import annotations

import json
import platform
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sky_walker.accessory_probe import SCHEMA_VERSION, scenario_definition
from sky_walker import __version__
from sky_walker.config import DEFAULT_LOCATION, Coordinate


_SESSION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_session_id() -> str:
    return "".join(secrets.choice(_SESSION_ALPHABET) for _ in range(8))


def create_session(
    *,
    scenario: str,
    ios_version: str,
    source_probe_build: str,
    output_dir: Path,
    expected_location: Coordinate = DEFAULT_LOCATION,
    location_product_version: Optional[str] = None,
    bluetooth_adapter: Optional[str] = None,
    user_confirmed_usb_disconnected: Optional[bool] = None,
    windows_apple_usb_status: str = "not-required",
    windows_apple_usb_device_count: int = 0,
) -> tuple[Path, Dict[str, Any]]:
    """Create one versioned Source Test Session manifest."""
    session_id = _new_session_id()
    definition = scenario_definition(scenario)
    if location_product_version is None:
        if definition.uses_sky_walker_version:
            location_product_version = f"sky-walker {__version__}"
        else:
            location_product_version = definition.default_location_product_version
    latitude_step = 50.0 / 111_320.0
    second_latitude = (
        expected_location.latitude - latitude_step
        if expected_location.latitude > 89.0
        else expected_location.latitude + latitude_step
    )
    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "scenario": definition.scenario.value,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "expected_location": {
            "latitude": expected_location.latitude,
            "longitude": expected_location.longitude,
            "horizontal_tolerance_m": 25.0,
        },
        "timing": {
            "stabilization_seconds": 10,
            "maximum_capture_seconds": 120,
            "minimum_post_stabilization_callbacks": 10,
        },
        "stimulus": {
            "primary": {
                "kind": "static",
                "latitude": expected_location.latitude,
                "longitude": expected_location.longitude,
            },
            "fallback": {
                "kind": "two-point-route",
                "waypoints": [
                    {
                        "latitude": expected_location.latitude,
                        "longitude": expected_location.longitude,
                    },
                    {
                        "latitude": second_latitude,
                        "longitude": expected_location.longitude,
                    },
                ],
                "update_frequency_hz": 1.0,
                "movement_speed_kmh": 5.0,
            },
        },
        "environment": {
            "ios_version": ios_version,
            "source_probe_build": source_probe_build,
            "windows_version": platform.platform(),
            "location_product_version": location_product_version,
            "bluetooth_adapter": bluetooth_adapter,
        },
        "connection_evidence": {
            "user_confirmed_usb_disconnected": user_confirmed_usb_disconnected,
            "windows_apple_usb_status": windows_apple_usb_status,
            "windows_apple_usb_device_count": windows_apple_usb_device_count,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{session_id}.manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path, manifest
