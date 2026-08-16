"""Tests for Saved Paths persistence (ticket 04) against a temp file."""

from sky_walker.gui.paths import PathStore

WPS = [{"lat": 1.0, "lng": 2.0}, {"lat": 3.0, "lng": 4.0}]


def test_save_list_load_delete_round_trip(tmp_path):
    store = PathStore(tmp_path / "paths.json")
    assert store.names() == []

    store.save("home loop", WPS)
    assert store.names() == ["home loop"]
    assert store.load("home loop") == WPS

    store.save("office", WPS)
    assert store.names() == ["home loop", "office"]  # sorted

    store.delete("home loop")
    assert store.names() == ["office"]


def test_persists_across_instances(tmp_path):
    PathStore(tmp_path / "p.json").save("a", WPS)
    assert PathStore(tmp_path / "p.json").load("a") == WPS


def test_missing_file_reads_as_empty(tmp_path):
    assert PathStore(tmp_path / "nope.json").names() == []


def test_corrupt_file_reads_as_empty(tmp_path):
    p = tmp_path / "paths.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert PathStore(p).names() == []


def test_load_missing_name_returns_none(tmp_path):
    assert PathStore(tmp_path / "p.json").load("ghost") is None
