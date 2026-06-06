from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import list_observations
from src.polymarket_feed import ts_open_from_slug_epoch

WINDOW_ID_RE = re.compile(r"^btc-updown-15m-(\d{10})$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def audit_window_id(row: dict[str, Any]) -> dict[str, Any]:
    window_id = str(row.get("window_id") or "")
    ts_open = row.get("ts_open")
    match = WINDOW_ID_RE.match(window_id)
    result: dict[str, Any] = {
        "window_id": window_id,
        "ts_open": ts_open,
        "status": "INVALID",
        "valid": False,
        "issues": [],
    }
    if not window_id.startswith("btc-updown-15m-"):
        result["status"] = "SKIPPED"
        result["issues"].append("non_polymarket_btc_15m_window")
        return result
    if not match:
        result["issues"].append("window_id_not_btc_updown_15m_10_digit_epoch")
        return result

    open_epoch_seconds = int(match.group(1))
    expected_ts_open = ts_open_from_slug_epoch(open_epoch_seconds)
    result["open_epoch_seconds"] = open_epoch_seconds
    result["expected_ts_open"] = expected_ts_open
    result["epoch_digits"] = len(match.group(1))
    if ts_open != expected_ts_open:
        result["issues"].append("ts_open_mismatch")
        return result

    result["status"] = "VALID"
    result["valid"] = True
    return result


def build_audit(db_path: Path) -> dict[str, Any]:
    rows = list_observations(db_path) if db_path.exists() else []
    audited_rows = [audit_window_id(row) for row in rows]
    invalid_rows = [row for row in audited_rows if row["status"] == "INVALID"]
    skipped_rows = [row for row in audited_rows if row["status"] == "SKIPPED"]
    return {
        "generated_at_utc": utc_now(),
        "db_path": str(db_path.relative_to(ROOT)) if db_path.is_relative_to(ROOT) else str(db_path),
        "row_count": len(audited_rows),
        "valid_count": len([row for row in audited_rows if row["status"] == "VALID"]),
        "invalid_count": len(invalid_rows),
        "skipped_count": len(skipped_rows),
        "rows": audited_rows,
    }


def write_report(audit: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "observations.db"))
    parser.add_argument("--output", default=str(ROOT / "reports" / "phases" / "fase_6_window_id_audit.json"))
    args = parser.parse_args()

    audit = build_audit(Path(args.db))
    write_report(audit, Path(args.output))
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 1 if audit["invalid_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
