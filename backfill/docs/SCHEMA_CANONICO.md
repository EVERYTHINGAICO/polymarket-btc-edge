---
doc_id: SCHEMA_CANONICO
rol: decision-diseño
estado: implementado (scripts/init_db.py, schema_sha256=cef7a01e)
fase: EXP2-2
version: 1.1
creado: 2026-06-01
actualizado: 2026-06-01
uso: diseño de data/observations_exp2.db (mirror Exp1 + provenance)
---

# SCHEMA CANÓNICO — `data/observations_exp2.db`

> **Estado:** diseño de Fase B. Debe ser **mirror del schema de Exp1** para que `src/analysis/` se reutilice sin cambios. Las columnas marcadas (gates) son exigidas por `src/analysis/gates.py`.

## Tabla `observations` (1 fila = 1 ventana de 15 min)

| Columna | Tipo | Origen | Usada por |
|---------|------|--------|-----------|
| `window_id` | TEXT PK | Polymarket **`condition_id`** (único; `slug` está vacío en las `-1`) | todos |
| `ts_open` | TEXT (ISO UTC) | **`end_ts − 900s`** (¡NO `start_ts`, que está corrido ~24h! ver AUDITORIA_DATOS_vs_PLAN) | metadata |
| `ts_close` | TEXT (ISO UTC) | Polymarket `end_ts` (cierre real de la ventana 15m) | metadata |
| `outcome` | TEXT 'Up'/'Down' | **CLOB API `tokens[].winner`** por `condition_id` (autoridad). NO derivar del precio. `resolution` del dataset solo si ≠ -1 y concuerda | Gate 1, 2, 4b |
| `pm_up_price_open` | REAL | primer tick `up_price` ≥ `ts_open` (subset `prices`) | Gate 2, 4b |
| `deribit_index_open` | REAL | `index_price` del primer trade Deribit en `ts_open` | Gate 4a |
| `chainlink_close` | REAL | precio referencia al cierre (Binance 1m close ≈ `ts_close`; spot, no autoridad) | Gate 4a |
| `price_to_beat` | REAL | precio BTC al `ts_open` (strike implícito de la ventana up/down) | Gate 4a |
| `n_trades_15m` | INTEGER | conteo de trades clasificados (ventana 15m) | filtro `min_n_trades_15m` |
| `D_5m_otm_dotm` | REAL | señal (ver PLAN §1) | exploratorio |
| `D_10m_otm_dotm` | REAL | señal | exploratorio |
| `D_15m_otm_dotm` | REAL | señal | **Gate 1, 4b (pre-registrada Exp1)** |
| `D_5m_atm` | REAL | señal | exploratorio |
| `D_10m_atm` | REAL | señal | exploratorio |
| `D_15m_atm` | REAL | señal | exploratorio |
| `V_5m_otm_dotm` | REAL | volumen/presión | exploratorio |
| `V_10m_otm_dotm` | REAL | volumen/presión | exploratorio |
| `V_15m_otm_dotm` | REAL | volumen/presión | exploratorio |
| `is_incomplete` | INTEGER 0/1 | 1 si falta outcome | filtro `filter_is_incomplete` |
| `notes` | TEXT | trazabilidad | — |

> El config de Exp1 filtra: `outcome ∈ {Up,Down}`, `is_incomplete=0`, `window_id != demo-window`, `n_trades_15m ≥ 30`. Exp2 hereda estos filtros (declarados en el pre-registro v2.0.0).

## Tabla `trajectory` (intra-ventana — SOLO si el backfill lo permite)

| Columna | Tipo | Origen | Usada por |
|---------|------|--------|-----------|
| `window_id` | TEXT FK | join con observations | Gate 3 |
| `t_seconds` | INTEGER | segundos desde `ts_open` | Gate 3 |
| `pm_up_price` | REAL | `up_price` en ese instante | Gate 3 |

El subset `prices` de Polymarket SÍ trae serie temporal `up_price` (verificado). Si la densidad intra-ventana resultara insuficiente para algunas ventanas → esas salen sin trayectoria y **Gate 3 INSUFICIENTE** para ellas (mismo estado que Exp1 hoy). Aceptable, no inventa datos.

> **Nota Exp1:** el código `data.py` lee la tabla como `observations_intrawindow`. Para reutilizarlo verbatim, nombrar la tabla **`observations_intrawindow`** (y exponer `trajectory` como vista o alias si se prefiere el nombre corto).

## Tabla `backfill_provenance` (trazabilidad)

| Columna | Tipo | Para qué |
|---------|------|----------|
| `window_id` | TEXT | qué fila |
| `source_dataset` | TEXT | ej. `aliplayer1/polymarket-crypto-updown` |
| `source_path` | TEXT | ruta del parquet |
| `source_revision` | TEXT | **commit/revision HF fijado** (los datasets se refrescan ~3h) |
| `block_hash` | TEXT | hash del bloque descargado |
| `downloaded_at_utc` | TEXT | fecha de descarga |
| `outcome_source` | TEXT | `clob_winner` \| `dataset_resolution` (trazar de dónde salió cada outcome) |
| `overlaps_exp1` | INTEGER 0/1 | 1 si `ts_open` cae en periodo ya recolectado por Exp1 |

## Cómo se computan las señales D/V (resumen — detalle en AUDITORIA_PROTOCOLO.md)

Las columnas `D_*`/`V_*`/`n_trades_15m` NO vienen de la fuente: se calculan de los trades de Deribit (`BarendPotijk`) replicando `src/signal.py` de Exp1. Por cada trade: `delta` y `moneyness` se **recomputan** (Black-76, IV=`iv` del trade, cortes por |delta| del paper Alexander). `signed_pressure = sign(direction)·amount·delta_abs`. Convenciones congeladas en el pre-registro v2.0.0.

## Regla anti-lookahead (la que protege todo el backtest)

Para una ventana `[ts_open, ts_close)`:
- Trades de Deribit para D: solo `timestamp < ts_close` (y dentro de la ventana de la variante: 5m/10m/15m previos al punto de evaluación).
- `pm_up_price_open`: primer tick `≥ ts_open`.
- **Nada con `timestamp ≥ ts_close` toca los features.** El `outcome` (resolution) es la única cosa post-cierre, y solo es el target, nunca un feature.
