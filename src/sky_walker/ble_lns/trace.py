"""Append-only evidence emitted by one foreground BLE feed."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sky_walker.accessory_probe.ble_trace import TraceRecordType


class BleTraceWriter:
    def __init__(self, path: Path, session_id: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._session_id = session_id
        self._file = path.open("x", encoding="utf-8", newline="\n")

    def write(self, record_type: TraceRecordType, **fields: Any) -> None:
        record = {
            "schema_version": 1,
            "session_id": self._session_id,
            "record_type": record_type.value,
            "observed_at": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            **fields,
        }
        self._file.write(json.dumps(record, sort_keys=True) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
