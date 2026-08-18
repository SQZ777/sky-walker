"""Tests for the hot-plug device monitor (ticket 08).

The transition logic lives in DeviceMonitor.tick(), driven here by a scripted
poll function so connect/disconnect edges are exercised without a real device
or a background thread.
"""

from sky_walker.gui.monitor import DeviceMonitor


def build(poll_values, udid="ABC"):
    events = []
    seq = iter(poll_values)
    mon = DeviceMonitor(
        udid=udid,
        poll=lambda: next(seq),
        on_lost=lambda: events.append("lost"),
        on_found=lambda present: events.append(("found", tuple(present))),
    )
    return mon, events


def test_lost_fires_once_on_disappearance():
    mon, events = build([[], []])
    mon.tick()  # gone
    mon.tick()  # still gone
    assert events == ["lost"]


def test_found_fires_after_a_loss():
    mon, events = build([[], ["ABC"]])
    mon.tick()  # lost
    mon.tick()  # back
    assert events == ["lost", ("found", ("ABC",))]


def test_no_events_while_steadily_present():
    mon, events = build([["ABC"], ["ABC"]])
    mon.tick()
    mon.tick()
    assert events == []


def test_poll_error_counts_as_disconnected():
    def boom():
        raise RuntimeError("usbmux hiccup")

    events = []
    mon = DeviceMonitor("ABC", poll=boom,
                        on_lost=lambda: events.append("lost"),
                        on_found=lambda p: events.append("found"))
    mon.tick()
    assert events == ["lost"]


def test_set_device_resets_presence_for_reconnect():
    # After reconnecting to a (possibly new) device, monitoring resumes cleanly.
    mon, events = build([[], ["XYZ"]], udid="ABC")
    mon.tick()  # ABC lost
    mon.set_device("XYZ")
    mon.tick()  # XYZ present, no spurious 'found' because set_device marks present
    assert events == ["lost"]
