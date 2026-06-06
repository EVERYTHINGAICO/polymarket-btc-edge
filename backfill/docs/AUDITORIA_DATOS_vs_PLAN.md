---
doc_id: AUDITORIA_DATOS_vs_PLAN
rol: bitacora
estado: vivo
fase: EXP2-4 (cierre) / EXP2-5 (entrada)
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: control de calidad — fidelidad a Exp1 + cobertura de datos vs plan, antes de construir D
---

# AUDITORÍA — lo que llevamos vs Exp1, y datos vs plan

Control de calidad pedido por Pedro antes de EXP2-5. Dos partes: (1) fidelidad metodológica a Exp1, (2) cobertura de los datos descargados vs lo que el plan exige.

## Parte 1 — Fidelidad a Exp1

| Componente | Exp1 | Exp2 | Veredicto |
|------------|------|------|-----------|
| Señal D | `(A_C−A_P)/2` ponderada por delta_abs | misma (clon `signal.py`) | ✅ idéntico |
| Moneyness | \|δ\|: DOTM(0.02,0.125] OTM(0.125,0.375] ATM(0.375,0.625] | mismos cortes | ✅ idéntico |
| Fuente delta | directo de Deribit (trade/ticker) | **recomputado Black-76** | ⚠️ difiere — obligado (histórico no trae delta, 0/2000) y **validado**: reproduce mark_price (err mediano 0.0005) |
| Outcome | autoridad Polymarket gamma `outcomePrices` | autoridad CLOB `winner` | ✅ misma filosofía (autoridad, NO derivado del precio) |
| 5 gates | `gates.py` | mismo `gates.py` (16/16 tests) | ✅ idéntico |
| Schema DB | `observations` 25 cols + intrawindow | mirror exacto (`schema_sha256=cef7a01e`) | ✅ idéntico |
| `min_n_trades_15m` | 30 | a heredar en v2.0.0 | ✅ planeado |
| Split train/holdout | aleatorio (seed 42) | **temporal** | ⚠️ mejora deliberada (Exp1 tenía fuga temporal; ver AUDITORIA_PROTOCOLO A) |
| Independencia | binomtest | binomtest + block bootstrap | ⚠️ refuerzo deliberado (AUDITORIA_PROTOCOLO F) |

**Conclusión P1:** fiel a Exp1 en lo esencial. Las 3 diferencias (delta recomputado, split temporal, bootstrap) son **deliberadas, documentadas y justificadas** — no descuidos. La única forzada (delta) está validada contra la propia fuente Deribit.

## Parte 2 — Datos vs plan

| Ítem | Plan exige | Tenemos | Veredicto |
|------|-----------|---------|-----------|
| Ventanas BTC 15m | n ≥ 1000 | **9.231** | ✅ 9× el mínimo |
| Outcome autoridad | 100%, no derivado | **9.231/9.231 vía CLOB** (Up 4624 / Down 4607) | ✅ completo, balance ~50/50 |
| Período | el de las ventanas | ventanas y Deribit: **ambos 2025-12-26 → 2026-04-21** | ✅ solape temporal perfecto |
| Trades Deribit | order flow del período | **1.491.915 trades, 117 días** | ✅ cubre todo |
| Campos para D | direction, amount, iv, index, instrument | 0 nulos (verificado) | ✅ |
| Cobertura por ventana | ≥30 trades/ventana (Exp1) | **PENDIENTE** (cruce trades↔ventana corriendo) | ⏳ ver Parte 2b |

### Parte 2b — Cobertura intra-ventana (la prueba decisiva) — RESUELTA

**🚩 HALLAZGO CRÍTICO (la columna `start_ts` está corrida):** en `markets.parquet`, `start_ts` NO es el inicio de la ventana de 15 min — está ~24h antes (parece ser cuando el market se creó para trading). El **`end_ts` sí es el cierre real**, y el **`slug` codifica el `ts_open` correcto** (`btc-updown-15m-<ts_open>`, y `end_ts = ts_open+900`). Verificado: slug_ts=00:30 → end_ts=00:45 (15 min ✅), pero start_ts=00:38 del día anterior.
→ **Regla correcta de ventana:** `ts_close = end_ts`, `ts_open = end_ts − 900s`. (NO usar `start_ts` del dataset.) Esto se codifica así en EXP2-5.

**Otro hallazgo:** `slug` está VACÍO en las 8.099 filas `-1`; usar **`condition_id`** (único, 9.231) como clave maestra, NO `slug`.

**Cobertura (cruce corregido, ventana=[end_ts−900, end_ts)):**
| Métrica | Valor |
|---------|-------|
| Ventanas (condition_id únicos) | 9.231 |
| Con 0 trades Deribit | 6 (0.1%) |
| **Con ≥30 trades (umbral Exp1)** | **8.251 (89.4%)** |
| Mediana trades/ventana | 88 (p10=29, p90=286) |

→ **8.251 ventanas usables = 8× el mínimo de 1.000 de Exp1.** Potencia estadística de sobra. ✅

Nota técnica: cargar trades con `executemany` fila-a-fila es lentísimo; usar `read_json_auto('data/raw/deribit/*.jsonl', format='newline_delimited')` en DuckDB (segundos).

### Parte 2c — Gate 4a y Chainlink histórico (caso resuelto)

**Problema:** Gate 4a necesita `chainlink_close` y `price_to_beat` del oráculo **Chainlink** (el que Polymarket usa para resolver BTC 15m — confirmado: partnership Polymarket-Chainlink Data Streams). Exp1 leía Chainlink EN VIVO; en backfill hay que leer el histórico. Binance NO sirve (no es el oráculo-autoridad).

**Hechos (verificados 2026-06-01):**
- Chainlink BTC/USD en Polygon (`0xc907E116054Ad103354f2D350FD2514433D57F6f`, el mismo de Exp1) responde vía RPC público gratis.
- El **histórico es accesible** vía `getRoundData(roundId)` — verificado hasta feb-2026 (cubre dic-2025→abr-2026).
- Volumen total ~585k rounds (leer todo = horas, innecesario).

**Decisión (método de caso + ciencia):** **Opción A — leer Chainlink solo en los 2 instantes por ventana** (`ts_open`, `ts_close`), no todo el histórico.

**Algoritmo elegido: BÚSQUEDA BINARIA PURA (sin estado).** Caso entre cursor-secuencial vs binaria vs híbrido — los tres dan el MISMO resultado determinista (el round vigente en T es único), pero difieren en riesgo/auditabilidad:
- Cursor secuencial: arrastra estado entre ventanas → un bug se propaga silenciosamente. Rápido pero frágil. RECHAZADO.
- **Búsqueda binaria: sin estado, cada timestamp se resuelve aislado → imposible que un error contamine otra ventana; verificable como invariante (`updatedAt(round) ≤ T < updatedAt(round+1)`). ELEGIDA** — en investigación, corrección+auditabilidad > velocidad.
- Híbrido: reintroduce el estado que queremos evitar. RECHAZADO.

Mitigación de velocidad: **caché de rounds** (las búsquedas comparten rounds ya leídos → << 388k lecturas reales). Corre en background una vez.
- No-lookahead: round vigente = último con `updatedAt ≤ T`. Validado (target 14:30:00 → round 14:29:59).
- Fiel a Exp1 (mismo contrato/oráculo). Determinista. Gratis.
- Rechazadas: Binance (no es autoridad), bajar-todo (innecesario), INSUFICIENTE (el dato existe).

## Riesgos detectados / a vigilar
1. Si muchas ventanas tienen <30 trades → el n efectivo (post-filtro) podría caer; relevante para `min_n_efectivo` (AUDITORIA_PROTOCOLO E).
2. `price_to_beat` (strike de la ventana): el dataset no lo trae explícito → se deriva del precio BTC al `ts_open` (spot). Confirmar fuente exacta en EXP2-5.
3. `pm_up_price_open`: requiere el subset `prices` de Polymarket (aún no descargado; falta para Gate 2/4b y trayectoria Gate 3). **Pendiente EXP2-5.**

## Pendientes antes/durante EXP2-5
- [x] Completar cobertura intra-ventana (≥30 trades) → 7.799 ventanas.
- [x] Descargar subset `prices` Polymarket (pm_up_price_open + trayectoria).
- [x] Definir fuente de `price_to_beat` y `deribit_index_open/close` (Chainlink histórico + index Deribit).

## EXP2-8 — Plan del veredicto (caso resuelto 2026-06-02)

**Problema:** al partir 70/30 temporal, el holdout (30%) tiene 678 ventanas |D|>5 < `min_n=1000` (heredado de Exp1, pensado para dataset completo). Daría WAIT automático.

**Decisión (Pedro + caso):** reportar DOS veredictos, declarando rol de cada uno (NO elegir el mejor = no cherry-picking):
- **PRINCIPAL — dataset completo (7.799), k-fold CV como Exp1.** n(|D|>5)=~2.470 > 1.000. Es el enfoque con que Exp1 daba veredicto → comparabilidad 1:1. NO toca el config firmado.
- **SECUNDARIO — holdout temporal (30%).** Prueba más exigente (datos no vistos); se reporta aunque algún gate dé INSUFICIENTE por n.

**Barrido de umbrales (train, EXPLORATORIO — NO afecta veredicto):** el edge existe en todos los umbrales; participar en más mercados da más ganancia TOTAL (|D|>0: ~245u vs |D|>5: ~102u), aunque menor EV/apuesta. Punto dulce EV/apuesta en |D|∈[3,10]. → hipótesis para **Exp3** (pre-registrar umbral bajo + datos nuevos). NO se cambia el |D|>5 pre-registrado.

**Disciplina:** cada corrida es única, veredicto aceptado tal como caiga. No re-tunear. No cambiar umbral ni min_n por lo visto en train.
