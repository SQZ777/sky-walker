"""Saved Paths persistence (ticket 04).

A Saved Path is a named, ordered list of Waypoints. They live in a single JSON
file (default ~/.sky-walker/paths.json) as {name: [{lat, lng}, ...]}. A missing
or corrupt file reads as no saved paths, so a first run or a hand-mangled file
never crashes the GUI. Movement Speed and loop count are deliberately NOT stored
here — they stay live UI settings (see spec).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


def default_paths_file() -> Path:
    return Path.home() / ".sky-walker" / "paths.json"


class PathStore:
    def __init__(self, path) -> None:
        self._path = Path(path)

    def _read(self) -> Dict[str, List[dict]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: Dict[str, List[dict]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def names(self) -> List[str]:
        return sorted(self._read().keys())

    def save(self, name: str, waypoints: List[dict]) -> None:
        # Waypoints arrive already coerced to {lat, lng} floats by the caller;
        # store just those keys so unrelated fields never leak into the file.
        data = self._read()
        data[name] = [{"lat": w["lat"], "lng": w["lng"]} for w in waypoints]
        self._write(data)

    def load(self, name: str) -> Optional[List[dict]]:
        return self._read().get(name)

    def delete(self, name: str) -> None:
        data = self._read()
        data.pop(name, None)
        self._write(data)
