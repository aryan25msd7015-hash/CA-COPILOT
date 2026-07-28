"""Immutable JSONL audit trail writer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class ImmutableAuditTrail:
    """Append-only JSONL logger with hash chaining."""

    path: Path
    _lock: Lock = field(default_factory=Lock)
    _last_hash: str = "GENESIS"

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._recover_last_hash()

    def write_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            event = {
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
                "prev_hash": self._last_hash,
            }
            encoded = json.dumps(event, sort_keys=True, ensure_ascii=True)
            event_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            row = {**event, "event_hash": event_hash}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
            self._last_hash = event_hash
            return row

    def _recover_last_hash(self) -> str:
        if not self.path.exists():
            return "GENESIS"
        with self.path.open("r", encoding="utf-8") as handle:
            last_line = ""
            for line in handle:
                last_line = line.strip()
        if not last_line:
            return "GENESIS"
        try:
            payload = json.loads(last_line)
            return str(payload.get("event_hash") or "GENESIS")
        except json.JSONDecodeError:
            return "GENESIS"
