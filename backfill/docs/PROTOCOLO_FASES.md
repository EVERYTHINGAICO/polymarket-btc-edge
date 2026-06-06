---
doc_id: PROTOCOLO_FASES
rol: protocolo
estado: vivo
fase: EXP2-5..9 (restantes)
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: procedimiento paso-a-paso + prompt de ejecución por fase, para mantener rigor científico/determinista sin atajos
---

# PROTOCOLO DE EJECUCIÓN POR FASE — prompts diseñados

Complementa [PLAN_MAESTRO_EJECUCION.md](PLAN_MAESTRO_EJECUCION.md). Para cada fase restante:
**Objetivo · Precondición · Pasos · Criterio de salida (verificable) · Prompt de ejecución** (el texto que se le da a quien ejecute — humano o Claude — para que NO tome atajos).

## Invariantes que TODO prompt debe respetar
1. **Determinismo:** todo artefacto se hashea (SHA256); re-correr = mismo hash. Si difiere → bug, no avanzar.
2. **No-lookahead:** ningún feature usa `timestamp ≥ ts_close`. `ts_close = end_ts`, `ts_open = end_ts−900`.
3. **Holdout sellado:** el 30% temporal más reciente NO se mira hasta EXP2-8. Exploración solo en train, declarada.
4. **Pre-registro antes de confirmar:** parámetros congelados en v2.0.0 antes de la corrida confirmatoria.
5. **Verdad sobre conveniencia:** si algo no da, se documenta; no se inventa ni se ajusta para que "salga".
6. **Una sola corrida confirmatoria:** EXP2-8 se corre UNA vez. No iterar sobre el holdout.

---

## EXP2-5 — Features + dataset de investigación

**Objetivo:** producir `data/processed/research_dataset_v1.parquet`, 1 fila por ventana, con TODAS las columnas que los 5 gates exigen, sin lookahead.

**Precondición:** EXP2-4 cerrada (raw completo). ✅

**Pasos:**
1. ✅ `build_deribit_features.py` → D/V/n por ventana (hecho, hash `9976c733…`).
2. `build_polymarket_prices.py` → descargar subset `prices` (revision fija) → `pm_up_price_open` (primer tick con `timestamp ≥ ts_open`) + tabla `trajectory` (`t_seconds`, `pm_up_price`) para Gate 3.
3. Definir y computar: `price_to_beat` (precio BTC al `ts_open`), `deribit_index_open` (`index_price` del primer trade ≥ ts_open), `chainlink_close` (Binance 1m close ≈ ts_close, referencia).
4. `merge_research_dataset.py` → asof join (D + outcome + precios) por `window_id`. **Filtrar nada aún** (los filtros viven en el config, los aplica `data.py`).
5. Escribir `tests/test_no_lookahead.py` (ver criterio).

**Criterio de salida:**
- [ ] `research_dataset_v1.parquet` con columnas: `window_id, ts_open, ts_close, outcome, pm_up_price_open, deribit_index_open, chainlink_close, price_to_beat, n_trades_{5,10,15}m, D_*, V_*`.
- [ ] `tests/test_no_lookahead.py` PASS: para una muestra de ventanas, **ningún** trade/tick usado tiene `timestamp ≥ ts_close`.
- [ ] `verify_determinism`: re-correr el merge da el mismo hash.
- [ ] Reporte de cuántas ventanas quedan completas (todas las columnas no-nulas).

**Prompt de ejecución EXP2-5:**
> Construí `research_dataset_v1.parquet` uniendo D (deribit_features) + outcome (CLOB) + precios Polymarket (subset `prices`, revision FIJA) + referencia spot (Binance). Regla de ventana: `ts_close=end_ts`, `ts_open=end_ts−900`. `pm_up_price_open` = primer tick con `timestamp ≥ ts_open` y `< ts_close`. NUNCA uses datos con `timestamp ≥ ts_close` para un feature. Escribí `test_no_lookahead.py` que lo verifique y debe PASAR. Hashea el output y confirmá que re-correr da el mismo hash. NO apliques filtros de gate aquí (eso es del config). NO mires el holdout. Reportá n de ventanas completas + hash.

---

## EXP2-6 — Carga a la DB canónica

**Objetivo:** poblar `data/observations_exp2.db` (tabla `observations` + `observations_intrawindow`) desde el dataset, lista para `run_analysis.py`.

**Precondición:** EXP2-5 cerrada.

**Pasos:**
1. `load_to_db.py` → INSERT del dataset en `observations` (mapear nombres a las 25 columnas exactas); trayectoria en `observations_intrawindow`; provenance en `backfill_provenance`.
2. `is_incomplete=1` si falta outcome o columna crítica; las 6 ventanas sin trades → `insufficient_flow=1`.
3. Verificar contra el loader real de Exp1 (`src/analysis/data.py`).

**Criterio de salida:**
- [ ] `data.py` lee la DB sin error; `n_after_filter` reportado.
- [ ] n de ventanas que pasan los filtros de Exp1 (`outcome∈{Up,Down}`, `is_incomplete=0`, `n_trades_15m≥30`) **≥ 1000** (umbral). (Ya estimado: ~7.799 con outcome+n≥30.)
- [ ] DB hash registrado.

**Prompt de ejecución EXP2-6:**
> Cargá `research_dataset_v1.parquet` en `observations_exp2.db` mapeando a las 25 columnas exactas de Exp1. Marcá `is_incomplete`/`insufficient_flow` según corresponda; NO descartes filas (los filtros los aplica el config). Confirmá que `src/analysis/data.py` lee la DB y reportá `n_after_filter`. Registrá el SHA256 de la DB. NO mires accuracy ni holdout.

---

## EXP2-7 — Pre-registro v2.0.0 (FIRMA)

**Objetivo:** congelar y firmar `analysis_config.json` v2.0.0 ANTES de la corrida confirmatoria.

**Precondición:** EXP2-6 cerrada. Datos cargados pero **gates NO corridos sobre holdout**.

**Pasos:**
1. Trasladar a `analysis_config.json` v2.0.0 todos los valores congelados: variante D principal, umbral, split temporal 70/30, BS (Black-76/iv/r=0/ACT365), moneyness (cortes Exp1), filtro IV (≤0 o >300), `min_n_efectivo`, bonferroni, bootstrap (seed, n_resamples, block_size).
2. Pedro revisa y firma (`frozen_at_utc`, `frozen_by`, entrada en `_changelog`).
3. Checklist de [PRE_REGISTRO_v2.0.0.md](PRE_REGISTRO_v2.0.0.md).

**Criterio de salida:**
- [ ] Config v2.0.0 con todos los campos del blindaje + `_changelog`.
- [ ] Pedro confirma por escrito que NO vio los resultados sobre holdout.
- [ ] Copia timestamped del config (evidencia de que se firmó antes).

**Prompt de ejecución EXP2-7:**
> Generá `analysis_config.json` v2.0.0 con TODOS los parámetros congelados en AUDITORIA_PROTOCOLO + PRE_REGISTRO. Mostrale a Pedro el diff vs Exp1 v1.0.0 y la checklist de firma. NO corras gates. Guardá copia timestamped. Solo tras la firma de Pedro se avanza a EXP2-8.

---

## EXP2-8 — Análisis confirmatorio (UNA corrida)

**Objetivo:** veredicto oficial sobre el HOLDOUT sellado.

**Precondición:** EXP2-7 firmada.

**Pasos:**
1. `run_analysis.py --config analysis_config.json` → corre los 5 gates sobre el holdout temporal.
2. Añadir robustez: block bootstrap p-value (Gate 1/2) + sensibilidad (`r∈{0,0.02}`, tope IV∈{250,300,400}).
3. Registrar `output_hash`, veredicto, y todos los detalles.

**Criterio de salida:**
- [ ] Reporte `reports/phases/fase_7_final_analysis_exp2.json` con veredicto.
- [ ] `output_hash` reproducible (re-correr = mismo hash).
- [ ] Veredicto **aceptado tal como cae** (EDGE_VALIDATED / NO_EDGE_FIN / WAIT). NO re-tunear.

**Prompt de ejecución EXP2-8 (CRÍTICO — sin atajos):**
> Esta es la corrida CONFIRMATORIA. Se corre UNA vez sobre el holdout sellado. Corré `run_analysis.py` con el config v2.0.0 firmado. Reportá el veredicto y el `output_hash`. Si algún gate da FIN, el veredicto es NO_EDGE_FIN — **acéptalo, NO ajustes umbrales, NO vuelvas a correr con otra variante**. Agregá el block bootstrap y la sensibilidad como anexos de robustez. Cualquier cambio post-resultado requeriría un Exp3 con datos nuevos.

---

## EXP2-9 — Comparación + cierre

**Objetivo:** comparar Exp1 vs Exp2, escribir el handoff de cierre.

**Pasos:** tabla comparativa (accuracy, veredicto, n, período); discutir consistencia con el paper; limitaciones (período acotado/régimen único, autocorrelación, delta recomputado); handoff.

**Criterio de salida:**
- [ ] Doc de comparación Exp1 vs Exp2.
- [ ] Limitaciones declaradas honestamente.
- [ ] Handoff `HANDOFF_EXP2_<fecha>.md` actualizado.

**Prompt de ejecución EXP2-9:**
> Compará el veredicto y métricas de Exp2 vs Exp1 en una tabla. Discutí si el resultado es consistente con Alexander et al. (2022). Declará TODAS las limitaciones (período ~4 meses = posible régimen único; autocorrelación; delta recomputado vs directo; solape con Exp1 si lo hubiera). Escribí el handoff de cierre. No exageres el resultado: reportá lo que hay.

---

## Estado de ejecución
- EXP2-0..4 ✅ · EXP2-5 🔄 (D hecho; falta prices+merge+test) · resto ⏳.
- Hallazgo exploratorio (train): D_15m_otm_dotm acc 60.2% (n=1730, p<1e-4). NO es veredicto.
