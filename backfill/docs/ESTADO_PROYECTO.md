---
doc_id: ESTADO_PROYECTO
rol: bitacora
estado: vivo (se actualiza cada sesión)
fase: actual
version: rolling
creado: 2026-06-01
actualizado: 2026-06-01
uso: foto de avance — fase actual, decisiones, hallazgos, próximo paso. LEER PRIMERO.
---

# ESTADO DEL PROYECTO — Exp2

> Foto de "cómo vamos". Se actualiza al cerrar cada fase. Última actualización: **2026-06-03**.

## 🧪 VEREDICTO DATOS FINOS (2026-06-03) — NO hay edge de TOMADOR; el edge es MAKER

Re-test con datos tick-by-tick (20,47M ticks a 0,1s) + **orderbook con ask ejecutable real** (866M filas). Detalle completo: **[HALLAZGOS_DATOS_FINOS.md](HALLAZGOS_DATOS_FINOS.md)**.

- **El precio del mercado es eficiente y está calibrado** (precio ≈ P(outcome) en el grueso 0,3–0,7).
- Comprar al favorito: **EV −3,2%**. Fade de extremos (favorite-longshot): parecía +13,4% con precio sintético, **−6,0% con el ASK REAL**. Lag/latencia: refutado (el contrato lidera al spot). Order flow: 52,35% (< break-even).
- **Cada "edge" aparente era precio NO ejecutable** (medio / último negociado). Con el ask real → negativo. Eficiencia confirmada con la granularidad más fina posible.
- **Reconciliación "los bots predicen":** sí, y por eso el precio es eficiente; pero ganan como **MAKER cobrando el spread** (≈3,5pp = nuestro costo), no pagando el ask para apostar.
- **Estudio MAKER (Exp5) — HECHO:** PnL maker realizado **+2,2%/$** ($+1,53M/$69M, neto de selección adversa) PERO frágil: solo **vendiendo** (comprar es tóxico −5/−7%), **inestable** (todo en 2ª mitad), y **concentrado en alto volumen** (Q5 +4,84%; 60% de ventanas pierden; mediana −1,87%). Es un edge de **HFT** (rápido+selectivo), ya cosechado por los bots, fuera de alcance read-only. Detalle: [HALLAZGOS_DATOS_FINOS.md](HALLAZGOS_DATOS_FINOS.md) §8.

## 🎯 Señal de vida (EXP2-5, EXPLORATORIO — NO es veredicto)

Gate 1 corrido SOLO sobre TRAIN (5.459 ventanas, dic-2025→mar-2026). Holdout (2.340, mar→abr) **SELLADO**. Variante pre-registrada Exp1:
| Variante | n(\|D\|>5) | accuracy | p |
|----------|-----:|---------:|---|
| **D_15m_otm_dotm** | 1.730 | **60.2%** | <0.0001 |
| D_10m_otm_dotm | 1.259 | 59.0% | <0.0001 |
| D_5m_otm_dotm | 727 | 57.5% | 0.0001 |

Hay edge crudo fuerte y consistente con el paper (Alexander: señal en OTM/DOTM). **Advertencias:** (1) es TRAIN exploratorio, NO el veredicto; (2) falta Gate 4b (costos ~7% fee pueden comerse el edge); (3) falta corregir por autocorrelación (block bootstrap). Justifica seguir: descargar `prices` y armar los 5 gates. El veredicto oficial sale sobre el holdout sellado en EXP2-8.

## ⛔ VEREDICTO RETRACTADO (2026-06-02) — era LOOKAHEAD BIAS, NO hay edge

**El `EDGE_VALIDATED` de Exp2 es INVÁLIDO.** Detectado por el agente de Exp1: el pipeline calculaba D con trades de **DURANTE** la ventana `[ts_open, ts_close)` (lookahead) en vez de **ANTES** `[ts_open−15min, ts_open)` (predictivo). `build_deribit_features.py:139`.

**Corrección aplicada y artefactos regenerados (Codex, 2026-06-02):**
`build_deribit_features.py` ahora usa trades **predictivos** `[ts_open−Xm, ts_open)` para `D_5m/10m/15m`; `test_no_lookahead.py` ahora falla si D vuelve a usar `ts_close`.

**Test confirmatorio con artefactos nuevos:**
| D calculado con trades... | reporte | n(|D|>5) | accuracy | Gate4b EV | veredicto |
|---|---|---:|---:|---:|---|
| DURANTE la ventana (invalidado) | `data/invalidated_lookahead_20260602/` | 2.408 | 60.7% | +0.064 | artefacto |
| ANTES de ts_open — full | `reports/phases/fase_8_D_predictivo_full.json` | 2.427 | **47.96%** | **-0.058** | `NO_EDGE_FIN` |
| ANTES de ts_open — holdout temporal | `reports/phases/fase_8_D_predictivo_holdout.json` | 696 | **46.12%** | **-0.077** | `WAIT_FOR_MORE_DATA` por n<1000 |

Verificación exhaustiva (9 variantes 5/10/15m × umbral 3/5/10): **el predictivo da 45-49% en TODAS** — no hay edge en ninguna forma; las "significativas" apuntan levemente EN CONTRA.

**Conclusión real: NO existe edge predictivo en la señal D sobre estos datos.** El 60.7% era correlación concurrente (flujo de opciones y outcome son ambos consecuencia del mismo movimiento de BTC en la ventana). **Exp1 (~51%) medía BIEN todo el tiempo** — el "bug del logger de Exp1" que diagnosticamos NO era bug; Exp1 calculaba D predictivo (correcto), Exp2 concurrente (con lookahead). Crédito al agente de Exp1 por cazarlo.

**Lección:** `test_no_lookahead.py` chequeaba precios/trayectoria pero NO que los trades de D fueran previos a ts_open. Falla de Exp2 corregida.

**Hashes activos tras regeneración:** `deribit_features=fb2886c88b...`, `research_dataset=0f16b6959a...`, `db_sha256=deb6317d2f...`, `input_hash=f397fe5d3ca3...`, `n_after_filter=7.806`.

---
## (Histórico) Lo que se creyó antes de la retractación

Las 9 fases cerradas. Sobre el dataset histórico (dic-2025→abr-2026, 7.799 ventanas): **5/5 gates AVANZA** — Gate1 acc **60.7%** (p<1e-4), Gate4b EV neto **+0.064/apuesta**. Las 5 verificaciones críticas auditadas limpias (sin look-ahead [primer tick 16s, 0 antes de open], sin survivorship [99% cobertura], sin correlación serial [ACF ~0.02]).

**✅ Replicación forward CONFIRMADA (con cálculo correcto de D).** El primer test sugirió "no replica (51%)" pero usaba el D *defectuoso* de Exp1. El **test correcto** (D recalculado Black-76 sobre el período de Exp1 may-jun): **66.95%** (n=118). Y D_exp1 vs D_mio: correlación −0.016, signo 53.6% → **Exp1 calculaba D mal**; NO era régimen. El edge SÍ generaliza. Caveat: n=118 (CI ancho), fuerte no definitivo.

**Tareas nuevas:** (a) auditar/arreglar el cálculo de D del logger live de Exp1 (bug confirmado); (b) confirmar forward con n mayor; (c) Exp3 paper trading (precondición ahora cumplida en evidencia preliminar). Detalle: [COMPARACION_EXP1_EXP2.md](COMPARACION_EXP1_EXP2.md).

## Dónde estamos

**Fase EXP2-1 (verificación de fuentes) — CERRADA.** Todo verificado con datos/APIs reales.
**Fase EXP2-1.5 (auditoría/blindaje del protocolo) — EN CURSO.** Revisión tipo referee detectó 6 grados de libertad no congelados; resueltos por caso Harvard en [AUDITORIA_PROTOCOLO.md](AUDITORIA_PROTOCOLO.md). Falta trasladar valores finales al pre-registro y que Pedro firme.
**Fase EXP2-2 (schema canónico + init_db) — CERRADA.** `scripts/init_db.py` crea `data/observations_exp2.db`: tablas `observations` (25 cols, **mirror exacto verificado de Exp1**) + `observations_intrawindow` + `backfill_provenance` (nueva). Idempotente y determinista (`schema_sha256=cef7a01e…`). Confirmado que la query de `src/analysis/data.py` lee la DB sin error y no falta ninguna columna que exijan los gates.
**Fase EXP2-3 (clonar núcleo analítico) — CERRADA.** Clonados de Exp1 (read-only): `src/analysis/` (config, data, stats, gates, verdict, exploratory), `src/signal.py`, `scripts/run_analysis.py`, `tests/test_analysis_fixtures.py`. Deps añadidas: `duckdb`, `scipy`. **`pytest`: 16/16 PASS.** `run_analysis.py` corre end-to-end sobre la DB vacía → `WAIT_FOR_MORE_DATA` (n=0), `output_hash` determinista. La maquinaria analítica está validada; falta solo poblarla con datos.
> Nota config: `analysis_config.json` actual = copia de Exp1 v1.0.0 (solo para que los tests/CLI corran). Se **reemplaza por v2.0.0** en EXP2-7. El original quedó como `analysis_config_exp1_v1.0.0.json.backup`.
**Fase EXP2-4 (descarga / recolección) — CERRADA.** Datos crudos completos en `data/raw/` + `data/interim/`. Compuerta cumplida (hashes deterministas, datos validados).
- ✅ `build_windows.py` → `data/raw/polymarket_markets_btc15m.parquet`: 9.231 ventanas BTC 15m, revision HF fijada (`ba1ad37c…`), hash determinista `6110d928…` (verificado en 2 corridas).
- ✅ `build_deribit_trades.py` → **COMPLETO**: 117 días (2025-12-26 → 2026-04-21), **1.491.915 trades**, 405 MB, cada día con `.sha256`. Desde `history.deribit.com`. **Validado**: 0 nulos en los 7 campos de D; direction balanceado (buy/sell); call/put balanceado; index_price sensato ($68-70k abr-2026); instrument_name parseable (`BTC-26JUN26-60000-P`).
  - ✅ Hallazgo IV RESUELTO (caso Harvard, ver AUDITORIA_PROTOCOLO B.1/B.2): los trades NO traen delta (0/2000) → se **recomputa con Black-76**, validado vs mark_price de Deribit (err mediano 0.0005 = modelo fiel). IV inválida (`iv≤0` o `iv>300`, <0.5%) se descarta; el filtro de moneyness de Exp1 (`|δ|≤0.02`→IGNORED) elimina el resto de basura. Cortes de moneyness = idénticos a Exp1.
- ✅ `build_outcomes.py` → **COMPLETO**: `data/interim/outcomes.parquet`, **9.231/9.231 resueltas (100%)** vía CLOB autoridad. Up=4.624 / Down=4.607 (50.1%/49.9%, balance casi perfecto). 0 sin resolver. Recuperadas TODAS las ~8.099 que el dataset tenía como `-1`, sin derivar del precio.

**Auditoría datos vs plan (2026-06-01) — ver [AUDITORIA_DATOS_vs_PLAN.md](AUDITORIA_DATOS_vs_PLAN.md):**
- ✅ Fiel a Exp1 en lo esencial; 3 diferencias deliberadas y documentadas (delta recomputado+validado, split temporal, bootstrap).
- 🚩 **Hallazgo crítico:** la columna `start_ts` del dataset está corrida ~24h → **usar `ts_open = end_ts − 900`, clave = `condition_id`** (slug vacío en las `-1`). Ya reflejado en SCHEMA_CANONICO.
- ✅ **8.251 / 9.231 ventanas tienen ≥30 trades Deribit (89%)** = 8× el mínimo de Exp1. Datos de sobra.
**Fase EXP2-5 (features + merge) — CERRADA.**
- `prices` ✅ (pm_up_price_open 9.231 + trayectoria 880k ticks). D ✅. `deribit_index_open/close` ✅.
- **Chainlink refs ✅**: 9.231/9.231 con price_to_beat + chainlink_close (búsqueda binaria sin estado, bit-idéntica a 1xRPC; rate-limit 429 manejado con backoff+caché). NO-LOOKAHEAD OK. Precios $60k-97k (coherente). Mismo oráculo que Exp1 (no Binance).
- **`research_dataset_v1.parquet` ✅**: 9.225 ventanas, TODAS completas (D+outcome+precios). Hash `f1d06bcb…` determinista (verificado 2 corridas). `tests/test_no_lookahead.py`: 3/3 PASS.

**Fase EXP2-6 (carga a DB) — CERRADA.** `scripts/load_to_db.py` pobló `data/observations_exp2.db`: 9.225 obs + 880.587 ticks. **`src/analysis/data.py` de Exp1 lee la DB sin cambios** (mirror correcto). `n_after_filter = 7.799` (outcome + is_incomplete=0 + n_trades≥30) → 7.8× el umbral de 1.000. `input_hash=3147cd81…`, `db_sha256=bf9f7f5f…`. Provenance cargado.

**Fase EXP2-7 (pre-registro) — CERRADA.** `analysis_config.json` v2.0.0 **FIRMADO** (frozen 2026-06-02T08:07Z) + copia timestamped de evidencia. = Exp1 (gates/umbrales/variante D_15m/min_n=1000) + 3 mejoras justificadas: split temporal, delta Black-76, filtro IV. Bootstrap = robustez NO decisoria (block_size=10 por evidencia; autocorr medida trivial, Ljung-Box p=0.0487 borderline). min_n_efectivo descartado (redundante). Anti-cherry-picking confirmado: holdout NUNCA mirado; solo train (60.2%) exploratorio.
- Código preparado para EXP2-8: `stats.py` +temporal_split +block_bootstrap (24/24 tests PASS). Falta `run_analysis_exp2.py` (orquestador temporal+aleatorio+bootstrap).

### Auditoría científica (resumen)
| # | Agujero | Resolución |
|---|---------|-----------|
| A | split aleatorio = fuga temporal | **split temporal** (principal); aleatorio solo comparativo |
| B | delta BS = parámetro libre | congelar Black-76/IV-trade/r=0/ACT365 + sensibilidad en `r` |
| C | moneyness sin definir | cortes por **\|delta\|** según paper Alexander (no inventar) |
| E | n efectivo < nominal | pre-registrar `min_n_efectivo` por gate |
| F | binomtest asume independencia | medir autocorr + **block bootstrap**; veredicto exige ambos |
| (sólido) | determinismo de stats/hash | ✅ verificado en código, sin cambios |

## Decisiones tomadas y verificadas

| Tema | Decisión | Evidencia |
|------|----------|-----------|
| Qué hacemos hoy | Replicar señal **D** + 5 gates de Exp1 con datos históricos | [PLAN_EXP2.md](PLAN_EXP2.md) |
| Plan nuevo (microestructura/ML) | Parkeado como **Exp3** futuro | [EXPERIMENTO_FUTURO_MICROESTRUCTURA.md](EXPERIMENTO_FUTURO_MICROESTRUCTURA.md) |
| Polymarket (precios/ventanas) | **`aliplayer1`** primaria (1.132 resueltas), `BrockMisner` backup | DuckDB ✅ |
| **Outcome** | **CLOB API `winner`** (autoridad oficial). NO derivar del precio (flips de último segundo) | CLOB ✅ verificado |
| Outcome backup | data-api + Gamma para triangular | ✅ responden |
| Deribit (order flow → D) | **`BarendPotijk`** vía API pública; campos `iv/index_price/direction/amount` confirmados | API ✅ |
| Delta/moneyness | Recomputar con **Black-Scholes** (no viene en trades) | metodología `EthanFalcao`/`alexagedah` |
| Spot BTC referencia | **Binance klines 1m** (Gate 4a, vol) | API ✅ |
| Tardis / período largo | Documentados, NO en V1 | [FUENTES_SECUNDARIAS.md](FUENTES_SECUNDARIAS.md) |

## Hallazgos clave (lo que aprendimos investigando)

0. **Deribit histórico: usar `history.deribit.com`, NO `www.deribit.com`** (verificado 2026-06-01). `www` solo retiene ~1 día de trades; `history.deribit.com` tiene el histórico profundo de opciones (incluso expiradas) — trades de dic-2025→abr-2026 disponibles con `direction`/`iv`/`index_price`/`instrument_name`, gratis, sin key. Los colectores GitHub (BarendPotijk etc.) usan este subdominio; son scripts, no traen datos guardados. **Esto desbloquea D para nuestro período.** Config en `src/data_sources/sources_config.py`.


1. **`resolution=-1` (97.5%) = corte temporal**, no error: el colector empezó a guardar el campo el ~6-abr-2026. Recuperable vía CLOB. → [FUENTES_DATOS.md](FUENTES_DATOS.md)
2. **No derivar outcome del precio** — last-tick risk / flips (~6% en Exp1) sesgaría justo las ventanas apretadas. Solo autoridad CLOB.
3. **`btc-updown-15m` es producto nuevo (~ago-2025)** → período acotado, riesgo de régimen único (limitación honesta a declarar).
4. **D es construible gratis**: la API de Deribit trae todo lo necesario; el único trabajo es recomputar delta (BS).

## Cuántas ventanas tenemos (potencial)

- Resueltas ya en dataset: **1.132** (aliplayer1) — supera umbral 1.000 de Exp1.
- Recuperables vía CLOB (`-1`): **~8.099** más → potencial **~9.200** ventanas BTC 15m.

## Próximo paso — EXP2-2 (schema canónico)

1. Cerrar [SCHEMA_CANONICO.md](SCHEMA_CANONICO.md): tablas `observations` + `trajectory` + `backfill_provenance`, con la lógica de enriquecer outcome vía CLOB.
2. `scripts/init_db.py` (DB vacía, mirror de Exp1).
3. Definir convención Black-Scholes para delta/moneyness.

## Decisiones de Pedro pendientes

- **Período del backfill** y **holdout** sellado (se fijan en el pre-registro EXP2-7, antes de mirar accuracy).
- **Variante D** principal (`D_15m_otm_dotm` vs `D_5m_otm_dotm`).
- Confirmar usar las ~9.200 ventanas (resueltas + recuperadas vía CLOB) o solo las 1.132.

## Mapa de documentos

`README.md` (índice) · `PLAN_EXP2.md` (qué) · `PLAN_MAESTRO_EJECUCION.md` (cómo, fases) · `DECISION_FUENTES.md` (caso fuentes primarias) · `FUENTES_SECUNDARIAS.md` (caso fuentes extra) · `FUENTES_DATOS.md` (columnas reales) · `SCHEMA_CANONICO.md` · `PRE_REGISTRO_v2.0.0.md` · `EXPERIMENTO_FUTURO_MICROESTRUCTURA.md` · `ESTADO_PROYECTO.md` (este).
