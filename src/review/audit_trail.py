from __future__ import annotations

import json
from pathlib import Path


def export_audit_trail(events: list[dict], out_path: str) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    return path
