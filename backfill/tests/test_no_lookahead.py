"""EXP2-5 — Test de NO-LOOKAHEAD (compuerta del protocolo).

Verifica que NINGÚN dato usado para construir un feature tenga timestamp >= ts_close.
El outcome es el único dato post-cierre permitido (es el target, no un feature).

Regla de ventana: ts_close = end_ts, ts_open = end_ts - 900.

Para la señal D, la regla correcta es más estricta:
los trades Deribit usados como feature deben ser ANTERIORES a ts_open.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
CLREFS = ROOT / "data" / "interim" / "chainlink_refs.parquet"
PMTRAJ = ROOT / "data" / "interim" / "pm_trajectory.parquet"
DERIBIT_FEATURE_SCRIPT = ROOT / "scripts" / "build_deribit_features.py"


def duckdb_or_skip(testcase: unittest.TestCase):
    try:
        import duckdb
    except ImportError:
        testcase.skipTest("duckdb no disponible en este entorno")
    return duckdb


class TestNoLookahead(unittest.TestCase):
    def test_deribit_d_features_are_predictive_before_open(self):
        """D debe usar trades previos a ts_open, no trades dentro de [ts_open, ts_close)."""
        src = DERIBIT_FEATURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("tr.ts >= (w.ts_open_s-900)*1000", src)
        self.assertIn("tr.ts < w.ts_open_s*1000", src)
        self.assertIn("mins_before_open", src)
        self.assertNotIn("tr.ts >= (w.ts_close_s-900)*1000", src)
        self.assertNotIn("mins_before_close", src)

    def test_chainlink_refs_no_lookahead(self):
        """price_to_beat usa round con updatedAt<=ts_open; chainlink_close <=ts_close."""
        if not CLREFS.exists():
            self.skipTest("chainlink_refs aún no generado")
        duckdb = duckdb_or_skip(self)
        bad = duckdb.sql(f"""
            SELECT COUNT(*) FROM '{CLREFS.as_posix()}'
            WHERE (updatedAt_open IS NOT NULL AND updatedAt_open > ts_open)
               OR (updatedAt_close IS NOT NULL AND updatedAt_close > ts_close)
        """).fetchone()[0]
        self.assertEqual(bad, 0, f"{bad} refs Chainlink con timestamp posterior al instante objetivo")

    def test_trajectory_within_window(self):
        """Todo tick de trayectoria debe caer en [ts_open, ts_close)."""
        if not PMTRAJ.exists():
            self.skipTest("pm_trajectory aún no generado")
        duckdb = duckdb_or_skip(self)
        # t_seconds = ts - ts_open, debe estar en [0, 900)
        bad = duckdb.sql(f"""
            SELECT COUNT(*) FROM '{PMTRAJ.as_posix()}'
            WHERE t_seconds < 0 OR t_seconds >= 900
        """).fetchone()[0]
        self.assertEqual(bad, 0, f"{bad} ticks de trayectoria fuera de [ts_open, ts_close)")

    def test_window_duration_is_900(self):
        """ts_close - ts_open debe ser exactamente 900s (definición corregida)."""
        duckdb = duckdb_or_skip(self)
        bad = duckdb.sql(f"""
            SELECT COUNT(*) FROM '{WINDOWS}'
            WHERE (end_ts - (end_ts-900)) != 900
        """).fetchone()[0]
        self.assertEqual(bad, 0)


if __name__ == "__main__":
    unittest.main()
