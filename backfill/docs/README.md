---
doc_id: README
rol: indice
estado: vivo
version: 2.0
actualizado: 2026-06-01
uso: índice maestro de toda la documentación de Exp2
---

# Documentación Exp2 — Índice maestro

Repo de investigación cuantitativa. Cada documento lleva **frontmatter** (`rol`, `estado`, `fase`, `version`, `uso`) para trazabilidad. Este índice los clasifica por **rol epistémico** (no por fecha): protocolo, pre-registro, decisiones de diseño, bitácora, trabajo futuro.

## Cómo leer (orden recomendado)

1. **[ESTADO_PROYECTO.md](ESTADO_PROYECTO.md)** — empezá aquí: dónde vamos hoy.
2. **[PLAN_EXP2.md](PLAN_EXP2.md)** — qué calculamos (señal D + 5 gates).
3. **[PLAN_MAESTRO_EJECUCION.md](PLAN_MAESTRO_EJECUCION.md)** — cómo (fases EXP2-0..9, determinismo).
4. El resto según necesidad (tabla abajo).

## Clasificación por rol

### 🧭 Protocolo — qué y cómo (estable, el "Methods")
| Doc | Fase | Estado | Uso |
|-----|------|--------|-----|
| [PLAN_EXP2.md](PLAN_EXP2.md) | todas | estable | Define la señal D y los 5 gates |
| [PLAN_MAESTRO_EJECUCION.md](PLAN_MAESTRO_EJECUCION.md) | 0..9 | vivo | Fases con compuertas, pipeline determinista, anti-cherry-picking |
| [PROTOCOLO_FASES.md](PROTOCOLO_FASES.md) | 5..9 | vivo | Procedimiento paso-a-paso + **prompt de ejecución por fase** (anti-atajos) |

### 🔒 Pre-registro — congelado/firmado (anti-cherry-picking)
| Doc | Fase | Estado | Uso |
|-----|------|--------|-----|
| [AUDITORIA_PROTOCOLO.md](AUDITORIA_PROTOCOLO.md) | 1.5 | en revisión | Referee: congela 6 grados de libertad (split, delta BS, moneyness, n, independencia) |
| [PRE_REGISTRO_v2.0.0.md](PRE_REGISTRO_v2.0.0.md) | 7 | BORRADOR sin firmar | Hipótesis + parámetros que Pedro firma antes de correr gates |

### 🧱 Decisiones de diseño — con evidencia verificada (casos Harvard)
| Doc | Fase | Estado | Uso |
|-----|------|--------|-----|
| [DECISION_FUENTES.md](DECISION_FUENTES.md) | 1 | decidido | Qué repos para D y outcome (criterios + riesgos) |
| [FUENTES_SECUNDARIAS.md](FUENTES_SECUNDARIAS.md) | 1 | decidido | 4 fuentes extra: activas vs solo documentadas |
| [FUENTES_DATOS.md](FUENTES_DATOS.md) | 1 | verificado | Columnas reales (DuckDB/API) → mapeo a schema |
| [SCHEMA_CANONICO.md](SCHEMA_CANONICO.md) | 2 | implementado | Diseño de `observations_exp2.db` (mirror Exp1) |

### 📓 Bitácora — cronológico (cambia con el tiempo)
| Doc | Fecha | Estado | Uso |
|-----|-------|--------|-----|
| [ESTADO_PROYECTO.md](ESTADO_PROYECTO.md) | vivo | rolling | **Foto de avance — leer primero** |
| [COMPARACION_EXP1_EXP2.md](COMPARACION_EXP1_EXP2.md) | EXP2-9 | **veredicto RETRACTADO** | El EDGE_VALIDATED era lookahead bias; NO hay edge predictivo (~48%). Ver retractación arriba del doc. |
| [METRICAS_RENDIMIENTO.md](METRICAS_RENDIMIENTO.md) | post-EXP2-9 | invalidado | Métricas del falso edge concurrente; ROI +13% era lookahead y NO es rendimiento real |
| [AUDITORIA_DATOS_vs_PLAN.md](AUDITORIA_DATOS_vs_PLAN.md) | EXP2-4/8 | vivo | Control de calidad: fidelidad a Exp1, cobertura, plan del veredicto |
| [../HANDOFF_EXP2_2026-06-02.md](../HANDOFF_EXP2_2026-06-02.md) | 2026-06-02 | **cierre/retractación** | **EDGE_VALIDATED retractado por lookahead; NO hay edge predictivo; no procede Exp3 trading** |
| [../HANDOFF_EXP2_2026-06-01.md](../HANDOFF_EXP2_2026-06-01.md) | 2026-06-01 | archivado | Decisión datos-primero, 6 palancas |
| [../HANDOFF_EXP2_2026-05-31.md](../HANDOFF_EXP2_2026-05-31.md) | 2026-05-31 | archivado | Por qué existe Exp2 |

### 🔭 Trabajo futuro — parqueado
| Doc | Fase | Estado | Uso |
|-----|------|--------|-----|
| [EXPERIMENTO_FUTURO_MICROESTRUCTURA.md](EXPERIMENTO_FUTURO_MICROESTRUCTURA.md) | Exp3 | parqueado | Microestructura, orderbook, EV/backtest, ML |

## Leyenda de `estado`
`estable` (no cambia salvo versión) · `vivo` (se actualiza) · `en revisión` (pendiente de firma) · `BORRADOR` (no firmado) · `decidido`/`verificado`/`implementado` · `archivado`/`parqueado`.

## Convenciones del repo (estándar de investigación)
- **Determinismo:** cada artefacto de datos lleva SHA256; mismo input → mismo hash.
- **Provenance:** revisions de fuentes fijadas; tabla `backfill_provenance`.
- **Pre-registro antes de mirar:** parámetros congelados en v2.0.0 antes de correr gates.
- **Versionado:** cambiar un doc de pre-registro requiere bump de `version` + nota.
- Estructura física del repo (carpetas `data/`, `scripts/`, `src/`, `tests/`): ver [../CLAUDE.md](../CLAUDE.md).
