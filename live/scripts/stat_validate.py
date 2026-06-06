from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path('data/observations.db')
MIN_WINDOWS = 1000


def main() -> int:
    if not DB_PATH.exists():
        print(json.dumps({'status': 'INSUFFICIENT_DATA', 'reason': 'database_missing', 'required_windows': MIN_WINDOWS}, indent=2))
        return 0
    connection = sqlite3.connect(DB_PATH)
    try:
        count = connection.execute('SELECT COUNT(*) FROM observations WHERE ts_close IS NOT NULL').fetchone()[0]
    finally:
        connection.close()
    if count < MIN_WINDOWS:
        print(json.dumps({'status': 'INSUFFICIENT_DATA', 'reason': 'not_enough_complete_windows', 'complete_windows': count, 'required_windows': MIN_WINDOWS}, indent=2))
        return 0
    print(json.dumps({'status': 'READY_FOR_STATISTICAL_GATES', 'complete_windows': count, 'required_windows': MIN_WINDOWS}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
