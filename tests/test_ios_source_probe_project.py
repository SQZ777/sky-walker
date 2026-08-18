"""Static checks for the Mac-built Source Probe project."""

from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).parents[1]
PROBE = ROOT / "poc" / "ios-source-probe"


def test_xcode_project_references_every_swift_source_and_test():
    project = (PROBE / "SourceProbe.xcodeproj" / "project.pbxproj").read_text(
        encoding="utf-8"
    )
    swift_files = sorted(path.name for path in PROBE.rglob("*.swift"))

    assert swift_files == [
        "ContentView.swift",
        "LocationCaptureStore.swift",
        "ProbeModels.swift",
        "ProbeSerializationTests.swift",
        "SourceProbeApp.swift",
    ]
    for filename in swift_files:
        assert f"/* {filename} in Sources */" in project
    assert "IPHONEOS_DEPLOYMENT_TARGET = 17.4;" in project
    assert "SourceProbeTests.xctest" in project


def test_probe_requests_only_foreground_location_permission():
    with (PROBE / "SourceProbe" / "Info.plist").open("rb") as file:
        info = plistlib.load(file)

    assert "NSLocationWhenInUseUsageDescription" in info
    assert "NSLocationAlwaysAndWhenInUseUsageDescription" not in info
    assert "NSLocationAlwaysUsageDescription" not in info
    assert "UIBackgroundModes" not in info


def test_shared_scheme_does_not_enable_xcode_location_simulation():
    scheme = (
        PROBE
        / "SourceProbe.xcodeproj"
        / "xcshareddata"
        / "xcschemes"
        / "SourceProbe.xcscheme"
    ).read_text(encoding="utf-8")

    assert 'allowLocationSimulation = "NO"' in scheme
    assert "SourceProbeTests" in scheme
