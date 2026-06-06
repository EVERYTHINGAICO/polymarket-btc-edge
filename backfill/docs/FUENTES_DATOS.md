---
doc_id: FUENTES_DATOS
rol: decision-diseño
estado: verificado (columnas reales con DuckDB/API)
fase: EXP2-1
version: 1.1
creado: 2026-06-01
actualizado: 2026-06-01
uso: inventario de columnas reales de cada fuente y mapeo columna→schema canónico
---

# FUENTES DE DATOS — Inventario y mapeo a schema canónico

> **Estado:** Fase EXP2-1 **verificada el 2026-06-01** con DuckDB (`DESCRIBE` + muestras reales), no de memoria. Columnas y hallazgos confirmados abajo.

## Cómo inspeccionar (sin descargar todo)

```python
import duckdb
# OJO estructura real: markets es UN archivo; el resto son carpetas particionadas
base = 'hf://datasets/BrockMisner/polymarket-btc-updown/data'
duckdb.sql(f"SELECT * FROM '{base}/markets.parquet' WHERE crypto='BTC' AND timeframe='15-minute' LIMIT 100").show()
duckdb.sql(f"SELECT * FROM '{base}/prices/**/*.parquet' WHERE crypto='BTC' AND timeframe='15-minute' LIMIT 100").show()
```

---

## Fuente 1 — Polymarket (columnas REALES confirmadas)

Layout real del repo: `data/markets.parquet` (archivo único) + carpetas `data/{prices,ticks,orderbook,spot_prices}/`.

### `markets` (1 fila por mercado) — tabla maestra de ventanas
| Columna | Tipo | → schema canónico |
|---------|------|-------------------|
| `market_id` | VARCHAR | (clave alterna) |
| `slug` | VARCHAR | **`window_id`** (ej. `btc-updown-15m-1775705400`) |
| `question` | VARCHAR | metadata |
| `crypto` / `timeframe` | VARCHAR | filtro: `BTC` / `15-minute` |
| `resolution` | TINYINT | **`outcome`**: 1→Up, 0→Down, **-1→unknown (ver hallazgo)** |
| `start_ts` | BIGINT (s) | **`ts_open`** |
| `end_ts` | BIGINT (s) | **`ts_close`** |
| `closed_ts` | BIGINT | metadata |
| `up_token_id` / `down_token_id` | VARCHAR | join con `prices`/`ticks`/`orderbook` |
| `condition_id` | VARCHAR | provenance |
| `fee_rate_bps` | SMALLINT | Gate 4b (fee real ≈ 1000 bps = 10%) |

### `prices` (serie temporal)
`market_id, timestamp(BIGINT), up_price(FLOAT), down_price(FLOAT), crypto, timeframe`
→ `pm_up_price_open` (primer tick ≥ ts_open) + **trayectoria** intra-ventana para Gate 3.

### `ticks` (trades individuales)
`market_id, timestamp_ms, token_id, outcome, side, price(DOUBLE), size_usdc, tx_hash, block_number, log_index, source, spot_price_usdt, spot_price_ts_ms, crypto, timeframe`
→ order flow Polymarket + **`spot_price_usdt`** (¡spot BTC ya unido a cada tick! útil para derivar outcome y vol).

### `orderbook` (snapshots)
`ts_ms, market_id, token_id, outcome, best_bid, best_ask, best_bid_size, best_ask_size, crypto, timeframe`
→ spread real (`best_ask - best_bid`) para Gate 4b realista. **Experimento futuro (Exp3).**

### `spot_prices`
`ts_ms, symbol, price(DOUBLE), source` → precio spot BTC (Binance/Chainlink) para derivar outcome y vol realizada.

## 🚩 HALLAZGO CRÍTICO — cobertura de `resolution`

Conteo verificado de ventanas **BTC 15-minute**:

| Dataset | Total | resol=1 (Up) | resol=0 (Down) | **resueltas** | resol=-1 (unknown) | ts_max |
|---------|------:|----:|----:|----:|----:|--------|
| `BrockMisner/polymarket-btc-updown` | 8.304 | 104 | 101 | **205** | 8.099 | ~8 abr 2026 |
| `aliplayer1/polymarket-crypto-updown` | 9.231 | 591 | 541 | **1.132** | 8.099 | ~19 abr 2026 |

**Los 8.099 `-1` son idénticos en ambos** → no es ruido: es un bloque de mercados viejos donde el colector nunca llenó `resolution`. Los resueltos son los recientes.

### Por qué `-1` (causa confirmada con DuckDB)

Corte **puramente temporal** (verificado 2026-06-01):
- `-1`: `start_ts` de **2025-12-26** a **2026-04-05**; **los 8.099 sin `closed_ts`** (null/0).
- resueltos: `start_ts` de **2026-04-06** a **2026-04-20**; **100% con `closed_ts`**.
- Corte limpio (~1h de gap, sin solape).

→ **El colector empezó a guardar el campo `resolution` recién el ~6-abr-2026.** Lo anterior se registró sin resultado. No es un error de datos; es cuándo arrancó la captura del campo. (Por eso los `-1` son idénticos en ambos datasets: mismo origen.)

### El outcome de los `-1` ES RECUPERABLE (verificado)

Los mercados `-1` SÍ resolvieron en su momento (3,5 meses de historia real); solo no se guardó el campo. El **último precio conocido** delata el ganador (al resolver, el token ganador → ~1.0, perdedor → ~0.0). Muestra real de 5 mercados `-1`:

| market_id | last_up | last_down | ganador |
|---|---|---|---|
| 1878580 | 0.9995 | 0.0005 | Up |
| 1884427 | 0.9985 | 0.0015 | Up |
| 1871815 | 0.0060 | 0.9940 | Down |
| 1873005 | 0.9350 | 0.0650 | Up (probable) |
| 1866241 | 0.8150 | 0.1850 | ambiguo (último tick pre-cierre) |

### ⚠️ NO derivar del precio — usar la AUTORIDAD oficial

**Decisión (Pedro, 2026-06-01):** derivar el outcome del último precio capturado **NO es válido**. El último tick puede ser segundos antes del cierre y BTC puede cruzar el strike en el último segundo (**flip de último segundo / last-tick risk**, ~6% de ventanas en Exp1, justo las de movimiento chico). Peor: el error sería **sesgado** hacia las ventanas apretadas, contaminando justo donde D importa. La autoridad real es la **resolución de Polymarket** (anclada a Chainlink/UMA en el segundo exacto).

### ✅ Fuente oficial verificada — CLOB API por `condition_id`

`GET https://clob.polymarket.com/markets/<condition_id>` (read-only, sin keys, gratis). Verificado 2026-06-01 sobre un mercado `-1`:
```
condition_id 0x90daa...6e21  ("Bitcoin Up or Down - April 6, 7:30PM-7:45PM ET")
closed: true
tokens: [ {outcome:"Up", price:1, winner:true}, {outcome:"Down", price:0, winner:false} ]
```
→ **`tokens[].winner` = outcome AUTORIDAD** (resolución del oráculo, no derivada). Recupera las ~8.099 ventanas `-1` con outcome REAL usando el `condition_id` (que sí tenemos en `markets.parquet`). El subset `prices` se usa solo para `pm_up_price_open` y trayectoria, NUNCA para decidir el outcome.

**Plan EXP2-2/EXP2-4:** enriquecer cada ventana (resuelta o `-1`) con `clob.polymarket.com/markets/<condition_id>` → `outcome` autoridad. Por bloques, cacheado, con provenance + hash. (El endpoint Gamma `?condition_id=` indexa distinto; CLOB es la vía directa.)

**Implicaciones:**
1. Para empezar ya: **`aliplayer1` da 1.132 ventanas resueltas > umbral 1.000 de Exp1.** BrockMisner (205) no alcanza hoy → **se invierte la preferencia del caso: arrancar con `aliplayer1`** (o derivar outcome).
2. **El outcome NO depende de `resolution`.** Con `end_ts`/`start_ts` + `spot_prices`/`ticks.spot_price_usdt` se puede **derivar Up/Down** (precio cierre vs apertura, o vs strike), recuperando miles de ventanas `-1`. Es lo que hizo Exp1 (outcome = autoridad Polymarket + referencia spot). → tarea de EXP2-2/EXP2-5.

## Fuente 2 — Deribit (order flow, columnas REALES confirmadas vía API pública)

`GET /public/get_last_trades_by_currency?currency=BTC&kind=option` (read-only, sin keys). Trade real verificado:
```json
{"timestamp":1780362771978,"iv":45.47,"price":0.0003,"amount":18.0,"direction":"buy",
 "index_price":71241.35,"instrument_name":"BTC-3JUN26-75000-C","mark_price":0.00024763,
 "contracts":18.0,"trade_seq":117,"trade_id":"431552893","tick_direction":0}
```

| Campo API | → uso en D |
|-----------|-----------|
| `direction` (buy/sell) | **signo** de `signed_pressure` |
| `amount` | **tamaño** de `signed_pressure` |
| `iv` | input Black-Scholes → **delta** |
| `index_price` | input BS + `deribit_index_open` |
| `instrument_name` `BTC-3JUN26-75000-C` | parsear **strike (75000), tipo (C/P), expiry (3JUN26)** → moneyness |
| `timestamp` | ubicar en ventana de 15m |

✅ **Todo lo necesario para D está presente.** Falta solo computar `delta` y `moneyness` (Black-Scholes, ver [DECISION_FUENTES.md](DECISION_FUENTES.md) §5). Colector: `BarendPotijk/deribit_historical_trades` usa este mismo endpoint (`..._by_currency_and_time`) y conserva todos los campos.

## Mapeo final → schema canónico

Ver [SCHEMA_CANONICO.md](SCHEMA_CANONICO.md). Backfill (`scripts/`) hace **asof join sin lookahead**: para una ventana que cierra en `ts_close`, los trades Deribit usados son solo `[ts_open, ts_close)`, nunca posteriores.

## Provenance

Toda fila registra en `backfill_provenance`: dataset, **revision/commit HF fijada**, ruta del parquet, fecha de descarga, hash de bloque, `overlaps_exp1`.
