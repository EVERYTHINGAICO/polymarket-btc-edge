# Fase 6 — Real Window PASS Report

**Fecha:** 2026-05-27T19:08:20.545176Z
**Estado:** PASS

## Resumen

- `window_id`: `btc-updown-15m-1779875100`
- `ts_open` → `ts_close`: 2026-05-27T09:45:00Z → 2026-05-27T10:00:00Z
- `outcome`: **Down** (autoridad: Polymarket gamma)
- `chainlink_close`: 75789.17611316 (referencia, oráculo Polygon)
- `deribit_index_open` → `deribit_index_close`: 75824.22 → 75803.0
- `price_to_beat`: 75814.71473071 (G6.1b: desde Chainlink al ts_open)
- `pm_up_price_open` → `pm_up_price_close`: 0.485 → 0.005
- `n_trades_15m`: 31
- `is_incomplete`: 0
- `insufficient_flow`: 0
- `notes`: ``

## Criterios de evaluación

- ✅ outcome_valid
- ✅ is_incomplete_zero
- ✅ has_n_trades
- ✅ has_deribit_open
- ✅ has_deribit_close
- ✅ has_chainlink_close
- ✅ has_price_to_beat_g61b
- ✅ trajectory_count_ok

## Trayectoria intra-ventana (Fase 6.b)

- Puntos capturados: **31**
- Primer punto: t=3s, pm_up_price=0.485
- Último punto: t=900s, pm_up_price=0.005
- Min/Max: 0.005 / 0.575

## T-7 stdout (resumen)

```json
{
  "status": "PASS",
  "row_kind": "REAL",
  "selected_window_id": "btc-updown-15m-1779875100",
  "finished_at_utc": "2026-05-27T10:07:20.759768Z",
  "trajectory_samples": 31,
  "trajectory_errors": []
}
```

## Riesgos residuales

- T4 (resilience caída de red/luz) sigue WAIVED_BY_HUMAN.
- Gamma puede tardar >7 min en publicar resolución. Si recurre, subir `poll_intervals_seconds`.
- RPC públicos de Polygon pueden cambiar; lista de fallback en `src/chainlink_feed.py`.

## Siguiente acción recomendada

- Si PASS: avanzar a G6.2 (3-5 ventanas consecutivas con `--with-trajectory`).
- Si FAIL: revisar criterios fallidos arriba y replanear.
