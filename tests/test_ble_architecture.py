"""Guard the experimental Bluetooth path from the USB/DVT actuator."""

from __future__ import annotations

import ast
from pathlib import Path


def test_ble_lns_package_cannot_import_usb_location_override() -> None:
    package = Path(__file__).parents[1] / "src" / "sky_walker" / "ble_lns"
    forbidden = (
        "pymobiledevice3",
        "sky_walker.backend",
        "sky_walker.location",
    )
    violations = []
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported = [node.module]
            for module in imported:
                if module.startswith(forbidden):
                    violations.append(
                        f"{path.name}:{getattr(node, 'lineno', '?')} imports {module}"
                    )

    assert violations == []
