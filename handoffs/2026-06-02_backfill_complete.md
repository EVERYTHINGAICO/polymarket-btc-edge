---
doc_id: HANDOFF_2026-06-02
rol: bitacora
estado: cierre Exp2 / arranque siguiente
fase: EXP2-9 (cerrada) → reporte + Exp3
version: 1.0
creado: 2026-06-02
uso: handoff para retomar — veredicto final, qué se hizo, qué sigue, cómo hacer el reporte
---

# HANDOFF EXP2 — 2026-06-02 (cierre)

## TL;DR — ⛔ VEREDICTO RETRACTADO (2026-06-02)

**El `EDGE_VALIDATED` de Exp2 era LOOKAHEAD BIAS. NO hay edge predictivo.** Exp2 calculó D con trades de DURANTE la ventana `[ts_open, ts_close)` en vez de ANTES `[ts_open−15min, ts_open)`. El flujo de opciones durante la ventana correlaciona con el outcome por construcción (ambos son consecuencia del mismo movimiento de BTC), no por poder predictivo.

**Verificado (read-only, nuestros datos):** D concurrente 60.7% (artefacto) vs D predictivo correcto **48.2%, no significativo**. Exhaustivo: 45-49% en todas las variantes. **Exp1 (~51%) medía bien todo el tiempo**; lo que le adjudicamos como "bug" no lo era. Crédito al agente de Exp1 por detectarlo.

**Estado real:** NO_EDGE predictivo en señal D sobre estos datos. Tareas: (a) si se quiere seguir, rehacer el pipeline con ventana predictiva `[ts_open−Xm, ts_open)` y arreglar `test_no_lookahead`; (b) el reporte a Exp1 quedó corregido (estaba equivocado); (c) sin edge, NO procede Exp3 trading.

## (HISTÓRICO — invalidado) TL;DR original

## El veredicto (matizado, honesto)

1. **Dataset histórico (dic-2025→abr-2026, 7.799 ventanas):** 5/5 gates AVANZA. Gate1 accuracy **60.7%** (p<1e-4), Gate4b EV neto **+0.064/apuesta** tras costos. `output_hash=5de32306…`.
2. **Replicación forward:** con D recalculado (Black-76) sobre el período de Exp1 (may-jun), accuracy **66.95%** (n=118). El edge SÍ generaliza.
3. **El "51% de Exp1" NO era régimen** — era un bug de cálculo de D del logger live (D_exp1 vs D_mio: correlación −0.016, coincidencia de signo 53.6%).

### Las 5 verificaciones críticas (todas auditadas, ver COMPARACION_EXP1_EXP2.md)
- Variante = D_15m_otm_dotm (replicación de Exp1). ✅
- Sin look-ahead (primer tick 16s post-open, 0 antes). ✅
- Sin survivorship (cobertura 99%). ✅
- Sin correlación serial (ACF ~0.02). ✅
- Salto 51%→60% explicado: era cálculo de D, no régimen. ✅

### Caveats (NO sobrevender)
- Forward n=118 → CI ancho [57.7%, 75.3%]. Fuerte, no definitivo.
- Periodo 4 meses → no probado en otros regímenes de largo plazo.
- Holdout temporal (62%) sugestivo pero no confirmatorio formal (n<1000).
- **Es VALIDACIÓN, no ejecución.** Trading = Exp3/Nivel 2, requiere autorización de Pedro.

## Qué se construyó (pipeline, todo determinista + hasheado)

`scripts/`: init_db · build_windows · build_outcomes (CLOB) · build_deribit_trades (history.deribit.com) · build_deribit_features (D, Black-76) · build_polymarket_prices · build_chainlink_refs · merge_research_dataset · load_to_db · run_analysis_exp2 · test_regime_vs_calc.
`tests/`: 24/24 PASS (16 fixtures Exp1 + 5 bootstrap + 3 no-lookahead).
Datos: 9.231 ventanas, 9.231 outcomes (CLOB 100%), 1.49M trades Deribit (+86k de may-jun).

## Hallazgos técnicos clave (para no re-tropezar)
1. **Deribit histórico: `history.deribit.com`**, NO `www.deribit.com` (1 día).
2. **Ventana: `ts_close=end_ts`, `ts_open=end_ts−900`.** La columna `start_ts` del dataset está corrida ~24h. Clave = `condition_id` (slug vacío en `-1`).
3. **Outcome via CLOB** `tokens[].winner` (autoridad), NUNCA derivar del precio.
4. **Delta recomputado Black-76** (histórico no trae delta), validado vs mark_price (err 0.0005).
5. **El logger de Exp1 calcula D distinto** al Black-76 → señales no correlacionadas. BUG a investigar.
6. Consola Windows cp1252 → sin emojis en `print()`.

## Lo que sigue (3 tareas)

### Tarea A — Escribir el REPORTE (siguiente paso inmediato)
Material listo en:
- `docs/COMPARACION_EXP1_EXP2.md` — veredicto, comparación, 5 verificaciones, limitaciones, tests A/B/C.
- `docs/ESTADO_PROYECTO.md` — foto de avance.
- `reports/phases/*.json` — resultados con hashes.
Estructura sugerida del reporte (estándar quant/académico): Resumen ejecutivo · Pregunta e hipótesis · Datos y método (señal D, gates, pre-registro) · Resultados (histórico 60.7% + forward 67%) · Verificaciones de robustez (las 5) · Limitaciones · Conclusión y próximos pasos. Hashes de input/output como apéndice de reproducibilidad.

### Tarea B — Auditar/arreglar el cálculo de D del logger de Exp1
El logger live produce un D que NO correlaciona con Black-76 (corr −0.016). Revisar `D:\openclaw\PROJECT DESIGN\src\deribit_feed.py` (DeltaResolver, classify_moneyness) y `signal.py`: ¿pierde trades por WebSocket? ¿delta directo de Deribit mal usado? ¿moneyness mal clasificada? Es la razón por la que Exp1 ve 51% en vez de ~60%.

### Tarea C — Exp3 (paper trading, NO real)
Precondición (replicación forward) cumplida en evidencia preliminar. Diseño en COMPARACION_EXP1_EXP2.md: walk-forward mes a mes, latencia simulada, spread+slippage real del order book, capacity sizing, Sharpe/Sortino/maxDD, ≥2-4 semanas dry-run. Pre-registrar antes. Solo tras confirmar → discusión Nivel 2 (capital real, autorización explícita).

## Cómo retomar
1. Leer `docs/ESTADO_PROYECTO.md` (foto) + `docs/COMPARACION_EXP1_EXP2.md` (veredicto/tests) + este handoff.
2. `py -m pytest tests/` debe dar 24/24.
3. Para re-correr veredicto: `py scripts/run_analysis_exp2.py --split temporal --on full`.
4. Para el test régimen-vs-cálculo: `py scripts/test_regime_vs_calc.py`.
5. Reglas duras intactas: read-only, registra-no-opera, Exp1 no se toca (salvo Tarea B, que es su propio repo).
