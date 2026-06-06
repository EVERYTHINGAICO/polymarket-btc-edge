---
doc_id: PLAN_MAESTRO_EJECUCION
rol: protocolo
estado: vivo (se actualiza al cerrar cada fase)
fase: EXP2-0..9
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: define CÓMO se ejecuta — fases con compuertas, pipeline determinista, principios invariantes
---

# PLAN MAESTRO DE EJECUCIÓN — Exp2 (determinismo + método científico)

> **Propósito:** este es el plan de la tarea larga (recolectar → ordenar → analizar). Hereda los principios que hicieron válido a Exp1 y los aplica al backfill histórico. Todo paso es **determinista** (mismo input → mismo output_hash) y **pre-registrado** (la hipótesis se firma antes de mirar resultados).
> Léase junto con: [PLAN_EXP2.md](PLAN_EXP2.md) (qué calculamos), [DECISION_FUENTES.md](DECISION_FUENTES.md) (de dónde), [SCHEMA_CANONICO.md](SCHEMA_CANONICO.md) (formato), [PRE_REGISTRO_v2.0.0.md](PRE_REGISTRO_v2.0.0.md) (la firma).

---

## A. Principios invariantes (aplican a TODA etapa)

Estos no se negocian en ninguna fase. Son la columna del método científico del proyecto:

1. **Determinismo bit-exact.** Cada artefacto (parquet, .db, reporte) se acompaña de su **SHA256**. Recorrer una etapa con el mismo input debe reproducir el mismo hash. Sin esto, no es ciencia, es anécdota.
2. **Provenance total.** Cada fila sabe de dónde vino: dataset, revision/commit, ruta, fecha de descarga, hash de bloque (tabla `backfill_provenance`).
3. **Sin lookahead.** Para una ventana `[ts_open, ts_close)`, ningún feature usa datos con `timestamp ≥ ts_close`. El `outcome` es target, nunca feature. Test automatizado obligatorio (`test_no_lookahead`).
4. **Pre-registro antes de mirar.** La hipótesis/umbrales (`analysis_config.json` v2.0.0) se firman ANTES de correr los gates sobre el holdout. Cambiar después = bump de versión + `_changelog` con razón.
5. **Train/holdout temporal sellado.** El holdout (período más reciente) no se toca hasta la corrida confirmatoria final. Toda exploración vive solo en train y se reporta como EXPLORATORIA.
6. **Read-only + registra-no-opera.** Cero trading/wallets/keys. Exp1 (`D:\openclaw\PROJECT DESIGN\`) es referencia read-only intocable.
7. **Reusar, no reescribir.** El núcleo analítico (`src/analysis/`) se clona verbatim de Exp1. Solo se escribe nuevo el pipeline de ingesta.
8. **Verdad sobre conveniencia.** Si una fuente no trae un campo, se documenta y se deriva o se acepta el gate INSUFICIENTE — no se inventan datos.

## B. Pipeline determinista (la cadena de artefactos)

Cada flecha es un script con input/output fijos y hash registrado:

```
[fuentes verificadas]
   │  (revision HF fija + API Deribit por bloques)
   ▼
raw/                         ← descargas crudas (JSONL/parquet) + hash por bloque
   │  build_windows.py
   ▼
interim/windows_15m.parquet  ← 1 fila por ventana BTC 15m (Polymarket)   [hash]
   │  build_deribit_features.py  (incluye recompute delta BS + moneyness)
   ▼
interim/deribit_features.parquet ← D/V/IV/OI por ventana (Deribit)        [hash]
   │  merge_research_dataset.py  (asof join sin lookahead)
   ▼
processed/research_dataset_v1.parquet ← tabla unida                       [hash]
   │  load_to_db.py
   ▼
data/observations_exp2.db    ← schema canónico (mirror Exp1)              [hash]
   │  run_analysis.py  (clonado de Exp1, sobre HOLDOUT)
   ▼
reports/phases/fase_7_final_analysis_exp2.json ← veredicto + output_hash
```

## C. Fases de ejecución (con compuertas — no se avanza sin cerrar la anterior)

| Fase | Nombre | Entregable | Compuerta de salida (gate) |
|------|--------|-----------|----------------------------|
| **EXP2-0** | Setup | docs/ completos, estructura, venv | Plan revisado por Pedro ✔ |
| **EXP2-1** | Verificación de fuentes | [DECISION_FUENTES.md](DECISION_FUENTES.md) + confirmar campos API Deribit (`iv`/`index_price`/`direction`) + `LIMIT 100` columnas Polymarket | Confirmado que D es construible (C1+C2 cubiertos) |
| **EXP2-2** | Schema canónico | [SCHEMA_CANONICO.md](SCHEMA_CANONICO.md) cerrado + `scripts/init_db.py` | DB vacía creada con schema mirror de Exp1 |
| **EXP2-3** | Clonar núcleo analítico | `robocopy src/analysis + tests` de Exp1; `pytest` de fixtures pasa | 16/16 tests sintéticos PASS sobre el clon |
| **EXP2-4** | Descarga (recolección) | `raw/` poblado por bloques; revision HF fija; hashes en provenance | Re-descarga del mismo bloque = mismo hash |
| **EXP2-5** | Features + merge | `deribit_features` ✅, `prices`+`research_dataset_v1` (delta BS), `tests/test_no_lookahead.py` | test_no_lookahead PASS; verify_determinism = mismo hash 2x; reporte n completas |
| **EXP2-6** | Carga a DB | `observations_exp2.db` poblada (25 cols) | `data.py` lee OK; **n tras filtros Exp1 ≥ 1000** (est. ~7.799); DB hash registrado |
| **EXP2-7** | **Pre-registro v2.0.0** | Pedro firma config + [PRE_REGISTRO_v2.0.0.md](PRE_REGISTRO_v2.0.0.md) | Todos los parámetros del blindaje en config; Pedro confirma no haber visto holdout; copia timestamped |
| **EXP2-8** | Análisis confirmatorio (UNA corrida) | `run_analysis.py` sobre holdout + bootstrap + sensibilidad | output_hash reproducible; veredicto **aceptado tal como cae** (NO re-tunear) |
| **EXP2-9** | Comparación + cierre | Tabla Exp1 vs Exp2; limitaciones; handoff | comparación + limitaciones declaradas + handoff |

**Regla de las compuertas:** una fase no empieza hasta que la anterior cierra su gate. Procedimiento paso-a-paso + **prompt de ejecución por fase** (anti-atajos): ver [PROTOCOLO_FASES.md](PROTOCOLO_FASES.md).

## D. Determinismo en la práctica (cómo se hace cumplir en código)

- **Revision HF fija:** `load_dataset(..., revision="<commit_sha>")` o ruta `hf://...@<sha>`. Anotar el sha en provenance. (Los datasets se actualizan cada 3h; sin pin, no hay reproducibilidad.)
- **Descarga Deribit por bloques ordenados:** iterar por tiempo/`trade_seq` ascendente; ordenar determinísticamente antes de hashear (el orden de llegada de la API no es determinista).
- **`scripts/verify_determinism.py`:** corre la cadena 2 veces sobre el mismo período; afirma mismos hashes en cada artefacto. Si difieren → hay no-determinismo (orden, timestamp de runtime, float no canónico) → fix obligatorio.
- **Hash excluye campos de runtime:** igual que Exp1 (`output_hash` excluye `run_at_utc`).
- **Black-Scholes determinista:** misma fórmula, mismos inputs redondeados canónicamente → mismo delta. Documentar convención de redondeo.

## E. Anti-cherry-picking (las tentaciones específicas y su defensa)

| Tentación | Trampa | Defensa pre-registrada |
|-----------|--------|------------------------|
| "Probemos las 6 variantes de D y reportamos la mejor" | selección post-hoc | UNA variante principal en v2.0.0; el resto EXPLORATORIO |
| "Salió NO_EDGE, ajustemos el umbral \|D\|" | p-hacking | cambiar requiere Exp3 con datos nuevos |
| "Elijamos el período histórico que da mejor resultado" | cherry-pick de período | período se fija en v2.0.0 antes de descargar |
| "Filtremos las ventanas ruidosas que vimos" | filtro post-hoc | filtros declarados en pre-registro |
| "Usemos las ventanas que ya miramos en Exp1" | doble-dipping | marcar `overlaps_exp1`, excluir del holdout |
| "Miremos el holdout solo para chequear" | contamina la confirmación | holdout sellado; solo se abre en EXP2-8 |

## F. Decisiones de Pedro pendientes (se firman en EXP2-7)

Ver [PRE_REGISTRO_v2.0.0.md](PRE_REGISTRO_v2.0.0.md): variante D principal, umbral, período histórico, período de holdout, `min_n_for_verdict`, filtros heredados.

## G. Estado actual (2026-06-01)

- ✅ **EXP2-0** (setup) cerrado.
- ✅ **EXP2-1** cerrado — fuentes verificadas con DuckDB + API real:
  - Deribit: campos `iv`/`index_price`/`direction`/`amount`/`instrument_name` **confirmados** en un trade real → D es construible (delta vía BS).
  - Polymarket: columnas reales confirmadas; **`aliplayer1` = Fuente #1** (1.132 ventanas resueltas vs 205 de BrockMisner).
  - 🚩 Hallazgo: ~8.099 ventanas con `resolution=-1` → **derivar outcome** de spot vs strike/apertura (tarea EXP2-2/EXP2-5).
- ✅ **EXP2-2** cerrado — `scripts/init_db.py` crea la DB canónica (mirror Exp1 verificado + `backfill_provenance`); idempotente, `schema_sha256=cef7a01e…`. La DB vacía la lee `src/analysis/data.py` sin error.
- ✅ **EXP2-3** cerrado — núcleo analítico clonado de Exp1 (`src/analysis/`, `src/signal.py`, `run_analysis.py`, tests). **16/16 pytest PASS**; `run_analysis.py` end-to-end sobre DB vacía → `WAIT_FOR_MORE_DATA` determinista. Deps: +`duckdb`, +`scipy`.
- ⏳ **Siguiente: EXP2-4** (descarga por bloques: Polymarket HF con revision fija + Deribit API; outcome vía CLOB; hashes en `backfill_provenance`).
- El resto, sin empezar. Compuertas en orden.
- Nota técnica: la consola Windows es cp1252 → evitar emojis/unicode en `print()` de scripts.

### Decisión pendiente de Pedro para arrancar EXP2-2
¿Cómo definir `outcome`? (a) usar solo las ~1.132 ventanas con `resolution` ya resuelto (rápido, suficiente para n≥1000, pero período corto y reciente), o (b) **derivar** outcome de spot para recuperar miles de ventanas `-1` (más muestra y período, más trabajo + decisión metodológica que debe pre-registrarse). Recomendación: derivar (más poder estadístico y replica lo que hizo Exp1), pero la regla de derivación se fija ANTES de mirar accuracy.
