"""Typed result vocabulary shared by evidence assessments."""

from enum import Enum


class ProbeVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ProbeReason(str, Enum):
    ACCESSORY_ATTRIBUTION_CONFIRMED = "accessory-attribution-confirmed"
    ACCESSORY_ATTRIBUTION_NOT_OBSERVED = "accessory-attribution-not-observed"
    NONCONSECUTIVE_CALLBACKS = "nonconsecutive-callbacks"
    STALE_SAMPLES = "stale-samples"
    INSUFFICIENT_CALLBACKS = "insufficient-callbacks"
    CAPTURE_DURATION_EXCEEDED = "capture-duration-exceeded"
    ENVIRONMENT_INCOMPLETE = "environment-incomplete"
    ENVIRONMENT_MISMATCH = "environment-mismatch"
    EXPECTED_LOCATION_INACTIVE = "expected-location-inactive"
    BLE_TRACE_MISSING = "ble-trace-missing"
    APPLE_USB_PRESENT = "apple-usb-present"
    APPLE_USB_TRACE_INCOMPLETE = "apple-usb-trace-incomplete"
    APPLE_USB_STATUS_UNKNOWN = "apple-usb-status-unknown"
    USB_DISCONNECTION_UNCONFIRMED = "usb-disconnection-unconfirmed"
    BLE_DISCONNECTED = "ble-disconnected"
    BLE_TRANSPORT_ERROR = "ble-transport-error"
    BLE_TRANSPORT_INTERRUPTED = "ble-transport-interrupted"
    BLE_NOT_SUBSCRIBED = "ble-not-subscribed"
    BLE_SAMPLE_TRACE_INCOMPLETE = "ble-sample-trace-incomplete"
    SOURCE_INFORMATION_MISSING = "source-information-missing"
    MIXED_ACCESSORY_FLAGS = "mixed-accessory-flags"
    EVIDENCE_INCOMPLETE = "evidence-incomplete"
