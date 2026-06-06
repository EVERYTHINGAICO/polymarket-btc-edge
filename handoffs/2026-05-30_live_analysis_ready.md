# HANDOFF — 2026-05-30

## Quién
Claude Code (sesión Pedro / contact@everythingaico.com).

## Contexto rápido (continuidad de handoffs previos)

- `HANDOFF_2026-05-27.md` → primera ventana real con outcome=Up via gamma.
- `HANDOFF_FINAL_2026-05-27.md` → cierre del bloque G-1..G-9 + G6.1b + T-1..T-9 (sampler trayectoria).
- `HANDOFF_2026-05-28.md` → logger persistente operativo (L-1..L-6) + bug fix User-Agent Chainlink.
- **`HANDOFF_2026-05-30.md` (este)** → infraestructura de análisis determinista lista. Esperando llegar a 1000 ventanas.

## Estado actual del experimento (2026-05-30T07:31Z)

- **Logger continuo corriendo desde 2026-05-28T02:56Z** (~52h ininterrumpidas).
- **218 ventanas completas** acumuladas (~21.8% del objetivo de 1000).
- Throughput: ~4 ventanas/h ≈ 96/día.
- **ETA a 1000: ~8 días más** (≈ 2026-06-07).
- Última ventana cerrada: 2026-05-30T07:30Z.
- Sin errores chainlink, sin gamma unresolved.

## Lo que se hizo en esta sesión (2026-05-30)

Implementación completa del **bloque de análisis determinista** que pide PROJECT_DESIGN §7.B. Cero cambios al logger (sigue corriendo intacto).

### Goals ejecutados (todos PASS)

| Goal | Estado |
|------|--------|
| A-1 `analysis_config.json` (pre-registro v1.0.0) | ✅ |
| A-2 `src/analysis/config.py` | ✅ |
| A-3 `src/analysis/data.py` (load + hash input) | ✅ |
| A-4 `src/analysis/stats.py` (binomtest, bonferroni, kfold) | ✅ |
| A-5 `src/analysis/gates.py` (los 5 gates puros) | ✅ |
| A-6 `src/analysis/verdict.py` (consolidación + hash output) | ✅ |
| A-7 `scripts/run_analysis.py` (CLI determinista) | ✅ |
| A-8 `notebooks/analysis.ipynb` (12 celdas, satisface §4) | ✅ |
| A-9 `tests/test_analysis_fixtures.py` (16/16 PASS) | ✅ |
| A-10 Verificar reproducibilidad bit-exact | ✅ (3 corridas idénticas) |

### Las 7 técnicas de determinismo embebidas

1. **Pre-registro JSON versionado** (`analysis_config.json`) — todos los umbrales fijos antes de mirar datos. Cambio requiere bump de version + commit.
2. **Hash SHA256 del input data** — detecta drift entre corridas.
3. **Script Python top-to-bottom** — `run_analysis.py` ejecuta siempre igual.
4. **Synthetic fixtures con respuestas conocidas** — 16 tests validan cada gate sobre datos sintéticos.
5. **Bonferroni multiple-testing correction** — α=0.05 / 5 tests = 0.01.
6. **K-fold cross-validation** — 5 folds, seed=42.
7. **Hash SHA256 del output** — excluye `run_at_utc` para que mismo input → mismo hash.

## Cómo probar el experimento (cuando lleguemos a 1000)

### Comando único

```powershell
cd "D:\openclaw\PROJECT DESIGN"
py scripts/run_analysis.py --output "reports/phases/fase_7_final_analysis.json"
```

Eso es **todo**. El script:
1. Carga el pre-registro `analysis_config.json`.
2. Lee `data/observations.db` (read-only).
3. Hashea el input.
4. Hace train/holdout split 70/30.
5. Corre los 5 gates sobre holdout.
6. K-fold CV sobre train (sanity).
7. Consolida con Bonferroni.
8. Imprime JSON con `project_verdict`.
9. Hash output al final.

### Posibles veredictos

| `project_verdict` | Significado |
|-------------------|-------------|
| `EDGE_VALIDATED` | Todos los 5 gates dieron AVANZA en holdout → edge real. Justifica proyecto Nivel 2. |
| `NO_EDGE_FIN` | Al menos un gate dio FIN → no hay edge. Fin del proyecto. |
| `WAIT_FOR_MORE_DATA` | n<1000 → muestra insuficiente, no se puede concluir. |

### Reproducibilidad

```powershell
py scripts/run_analysis.py | py -c "import sys,json; d=json.loads(sys.stdin.read()); print(d['output_hash'])"
# Mismo input → mismo hash siempre
```

## Snapshot preliminar guardado

`reports/phases/fase_7_preliminary_analysis_2026-05-30.json`

Hoy (con 218 ventanas):
- `project_verdict: WAIT_FOR_MORE_DATA` (correcto, n_holdout=60 < 1000)
- Todos los gates: `INSUFICIENTE`
- K-fold accuracy en train: 56.6% ± 11.2% (varianza alta — esperado con muestra pequeña)

**No se interpreta** ningún número todavía (PROJECT_DESIGN línea 286: "antes de 1000 ventanas, cualquier número es ruido").

## Archivos creados en esta sesión

Copia activa `D:\openclaw\PROJECT DESIGN\`:

- **Nuevo:** `analysis_config.json` (pre-registro v1.0.0)
- **Nuevo:** `src/analysis/__init__.py`
- **Nuevo:** `src/analysis/config.py`
- **Nuevo:** `src/analysis/data.py`
- **Nuevo:** `src/analysis/stats.py`
- **Nuevo:** `src/analysis/gates.py`
- **Nuevo:** `src/analysis/verdict.py`
- **Nuevo:** `scripts/run_analysis.py`
- **Nuevo:** `notebooks/analysis.ipynb`
- **Nuevo:** `tests/test_analysis_fixtures.py`
- **Nuevo:** `reports/phases/fase_7_preliminary_analysis_2026-05-30.json`
- **Nuevo:** `HANDOFF_2026-05-30.md` (este archivo)

Archivos a actualizar en este handoff (append-only):
- `CLAUDE.md`
- `AGENTS.md`
- `OPENCLAW_HANDOFF.md`
- `OPENCLAW_RUNBOOK.md`

Copia base `D:\descargas al dico vergas\PROJECT DESIGN\`:
- **Append:** `CLAUDE.md` (nota espejo)

## Decisiones clave registradas hoy

1. **Pre-registro firmado.** Los umbrales de los 5 gates están en `analysis_config.json` v1.0.0, frozen at 2026-05-30T00:00Z. Cualquier cambio post-recolección debe documentarse en `_changelog` con razón.
2. **Holdout es sagrado.** Los gates corren SOLO sobre holdout (60 ventanas hoy, ~300 al final). Train se usa solo para K-fold CV de sanity. **Nunca tunear umbrales mirando outcomes en holdout.**
3. **Bonferroni con N=5.** Si después agregas más tests (ej. probar variantes de D), debes bumpar `n_tests_total` en el config y re-correr todo.
4. **Hash output es la única firma de "este es el resultado oficial".** Dos corridas con mismo `output_hash` son bit-exact reproducibles.

## Riesgos abiertos

| Riesgo | Estado |
|--------|--------|
| T4 (resilience) WAIVED | Sigue. 52h de uptime sin caída sugiere robustez práctica. |
| Gate 4a ratio borderline (0.95) | A vigilar cuando lleguen 1000. Si pasa de 1.0, hay problema real de Chainlink-Deribit divergence. |
| Cherry-picking de umbrales después de ver outcomes | Mitigado por pre-registro JSON commited. **NO modificar `analysis_config.json` sin documentar en `_changelog`.** |
| Drift de datos entre corridas | Hash input detecta. |

## Punto de retoma para mañana (o cuando lleguemos a 1000)

### Si el logger sigue corriendo
1. Verificar `Get-Process python` que sigue vivo.
2. Verificar `Get-Content reports/live/continuous_stdout.log -Tail 10` para ver últimos boundaries.
3. Contar ventanas: `py -c "import sqlite3; c=sqlite3.connect('data/observations.db'); print(c.execute(\"SELECT COUNT(*) FROM observations WHERE outcome IN ('Up','Down') AND is_incomplete=0\").fetchone())"`
4. Si <1000: esperar más.
5. Si ≥1000: correr `py scripts/run_analysis.py --output reports/phases/fase_7_final_analysis_<fecha>.json`.

### Si el logger murió
1. Relanzar: ver `OPENCLAW_RUNBOOK.md` sección "Modo continuo".
2. Esperar a recuperar ritmo de 4/h.

### Análisis intermedio (opcional)
Si quieres ver progreso preliminar antes de 1000:
```powershell
py scripts/run_analysis.py --output "reports/phases/fase_7_snapshot_$(Get-Date -Format yyyy-MM-dd).json"
```
Guarda snapshot por fecha. Útil para tracking del K-fold accuracy a ver si se estabiliza.

## Cómo verificar que TODO sigue funcionando

```powershell
# 1. Tests fixtures pasan
py -m unittest tests.test_analysis_fixtures

# 2. Script CLI corre sin error
py scripts/run_analysis.py | py -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'verdict={d[\"project_verdict\"]} n={d[\"n_after_filter\"]}')"

# 3. Reproducibilidad bit-exact
py scripts/run_analysis.py | py -c "import sys,json; print(json.loads(sys.stdin.read())['output_hash'])"
py scripts/run_analysis.py | py -c "import sys,json; print(json.loads(sys.stdin.read())['output_hash'])"
# Los dos hashes deben ser idénticos.
```

Generado: 2026-05-30T07:35Z

---

## Hallazgo observacional 2026-05-30 (registrado más tarde el mismo día)

Durante revisión del análisis preliminar sobre 272 ventanas, se observó un patrón consistente con la intuición previa de Pedro sobre **last-tick risk** en mercados Polymarket BTC Up/Down 15m.

### Datos observados (n=272, NO concluyente — muestra insuficiente)

| Tipo de ventana | n | D accuracy (todas) | D accuracy si \|D\|>5 | Movimiento BTC mediano |
|-----------------|---|--------------------|--------------------|------------------------|
| **Estables** (chainlink_dir == outcome) | 253 | 54.2% | 55.1% | $67 |
| **Flippy** (chainlink_dir != outcome) | 19 | 47.4% | 50.0% | $12 |

15/258 ventanas son FLIPs Chainlink vs Polymarket (5.8%). De esas:
- ~50% por movimiento intra-ventana chiquito (<$30 absolute).
- ~50% por staleness del on-chain aggregator vs Chainlink Data Streams que Polymarket usa.

### Hipótesis (no confirmada con n=19)

D parece tener accuracy ~7pp mayor en ventanas con movimiento BTC claro vs ventanas tranquilas. Posible mecanismo:
- En ventanas tranquilas, el "último tick" decide outcome → componente estocástico domina sobre la señal de D.
- En ventanas con movimiento grande, D acierta más porque la dirección del precio es inequívoca.

### Por qué nuestro setup permite observarlo

Sampleamos Chainlink vía aggregator on-chain (lag minutos) mientras Polymarket usa Data Streams (sub-segundo). La discrepancia entre nuestro `chainlink_close` y `outcome` oficial revela cuándo el último tick decidió la resolución.

### Decisión registrada por Pedro 2026-05-30

**Documentar el hallazgo en el repo (este archivo + CLAUDE.md + AGENTS.md). NO modificar código ni pre-registro `analysis_config.json` v1.0.0.**

Razones:
1. Modificar Gates basado en observación preliminar = cherry-picking = invalidación experimental.
2. Pre-registro v1.0.0 sigue siendo la referencia.
3. El hallazgo se re-evalúa en Fase 7 sobre 1000 ventanas como **sub-análisis EXPLORATORIO** (claramente declarado como exploratorio, no confirmatorio).

### Acción futura cuando lleguemos a 1000 ventanas

En notebook Fase 7, después de los 5 gates oficiales, agregar celdas exploratorias:
- Accuracy de D condicionado a estable/flippy (sub-análisis #1).
- Accuracy de D condicionado a V alta/baja (sub-análisis #2 — V ya está en cada fila).
- Accuracy de D condicionado a `n_trades_15m` alto/bajo (sub-análisis #3).

Si en esos sub-análisis aparece patrón fuerte y consistente, eso **justifica un proyecto siguiente** con nuevo pre-registro que incluya filtros por V o n_trades.

**Importante:** los sub-análisis NO cambian el veredicto AVANZA/FIN de los 5 gates oficiales. Son información adicional para el reporte final.

### Estado del logger al momento del hallazgo

- 258 → 272 ventanas (creciendo en tiempo real durante el análisis)
- Logger sigue corriendo sin interrupción desde 2026-05-28T02:56Z
- Sin errores chainlink, sin gamma unresolved en últimas 24h

Generado: 2026-05-30T19:30Z (extensión del handoff principal)

