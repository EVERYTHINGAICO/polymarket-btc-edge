---
doc_id: HANDOFF_2026-05-31
rol: bitacora
estado: histórico (archivado)
fase: pre-EXP2-0
version: 1.0
creado: 2026-05-31
uso: handoff cronológico inicial — por qué existe Exp2
---

# HANDOFF EXP2 — 2026-05-31

## Qué es esto

Carpeta vacía creada hoy en `D:\EXPERIMENTOS BTC OPTIONS\` para alojar un **segundo experimento independiente (Exp2)** del proyecto PROJECT_DESIGN, en paralelo al original que sigue corriendo en `D:\openclaw\PROJECT DESIGN\`.

Hoy NO se clonó ningún código todavía. Hoy solo se creó este folder vacío y este handoff. Mañana se decide qué meter dentro paso por paso.

## Estado al cierre de hoy

- **Folder Exp2 creado:** `D:\EXPERIMENTOS BTC OPTIONS\` (vacío excepto este handoff).
- **Exp1 NO tocado:** `D:\openclaw\PROJECT DESIGN\` sigue intacto.
- **Logger continuo NO detenido:** sigue corriendo en background recolectando ventanas para Exp1.
- **DB de Exp1 NO tocada:** `D:\openclaw\PROJECT DESIGN\data\observations.db` sigue creciendo.
- **Pre-registro v1.0.0 de Exp1 NO tocado:** `D:\openclaw\PROJECT DESIGN\analysis_config.json` FROZEN.
- **PROJECT_DESIGN.md NO tocado.**

## Contexto del Exp2 (por qué existe)

Durante revisión de los datos parciales de Exp1 (~272-358 ventanas) aparecieron dos observaciones:

1. **Last-tick risk / FLIPs Chainlink↔Polymarket**: ~5.8% de ventanas tienen `chainlink_dir != outcome_polymarket`, con mediana de movimiento BTC de $12 (vs $67 en estables). D parece tener accuracy ~7pp mayor en ventanas estables.
2. **D_5m_otm_dotm parece tener mejor accuracy (57.8%) que la variante pre-registrada D_15m_otm_dotm (50.4%).**

**Decisión registrada (Pedro, 2026-05-30):** NO modificar el pre-registro v1.0.0 de Exp1 — eso sería cherry-picking. Documentar las observaciones y correrlas en Fase 7 como **EXPLORATORIO**, no confirmatorio.

**Idea de Exp2:** correr un segundo experimento **paralelo e independiente** con:
- Pre-registro NUEVO v2.0.0 con hipótesis específica (probablemente `D_5m_otm_dotm` o variante por decidir).
- **Datos NUEVOS** vía backfill histórico (Deribit + Polymarket), NO sobre las mismas ventanas que ya miramos en Exp1.
- Validación estricta (pre-registro firmado ANTES de tocar datos, hold-out, veredicto AVANZA/FIN).

## Lo que falta decidir mañana (antes de copiar código)

1. **Hipótesis exacta** que Exp2 pre-registrará. Candidatas:
   - H_a: `D_5m_otm_dotm` con threshold 5 (cambia solo la variante temporal).
   - H_b: `D_5m_otm_dotm` con threshold en bracket [5, 10) (sweet spot observado).
   - H_c: `D_10m_otm_dotm` (variante media).
   - H_d: D + filtro de V (volatilidad) o filtro stable/flippy.

2. **Fuentes de backfill**: Pedro ya identificó repos con datos históricos de Deribit y de Polymarket markets `btc-updown-15m-*`. URLs específicas a compartir en chat nuevo mañana.

3. **Alcance del backfill Polymarket**:
   - ¿Solo outcome (Up/Down) y `price_to_beat`?
   - ¿O también `pm_up_price_open`/`pm_up_price_close` (requiere order book histórico, más complejo)?
   - ¿Trayectoria intra-ventana (sub-15min)? Probablemente no para backfill — exclusivo de recolección live.

4. **Periodo histórico**: ¿últimos 6 meses? ¿1 año? ¿2+ años? Más periodo = más muestra = más poder estadístico, pero también más riesgo de regime change.

## Pasos para mañana (orden sugerido)

### Paso 1 — Abrir chat nuevo en VS Code apuntando a `D:\EXPERIMENTOS BTC OPTIONS\`
Razón: aislar el contexto. El chat actual ya tiene mucho de Exp1; conviene empezar limpio para Exp2.

### Paso 2 — Decidir hipótesis exacta de Exp2
Pedro decide. Una vez decidida, NO se cambia (eso es el pre-registro).

### Paso 3 — Copiar el código analítico desde Exp1 (sin DB ni reportes)
Comando exacto (ejecutar desde PowerShell):
```powershell
robocopy "D:\openclaw\PROJECT DESIGN" "D:\EXPERIMENTOS BTC OPTIONS" /E /XD .venv __pycache__ .git data reports /XF "*.log" /R:2 /W:5
```
- `/XD ... data reports` excluye explícitamente la DB de Exp1 y los reportes de Exp1 (Exp2 empieza con DB vacía y reportes propios).
- El logger de Exp1 NO se detiene. `robocopy` no toca el origen.

### Paso 4 — Limpieza adicional post-clone
En `D:\EXPERIMENTOS BTC OPTIONS\`:
- Borrar `HANDOFF_*.md` (excepto este de Exp2).
- Renombrar `analysis_config.json` → `analysis_config_exp1_v1.0.0.json.backup` (preservar como referencia, NO usarlo).
- Crear `analysis_config.json` v2.0.0 NUEVO con la hipótesis de Exp2.
- Crear venv nuevo: `py -m venv .venv` + `pip install -r requirements.txt`.

### Paso 5 — Escribir `scripts/backfill_data.py`
Lee periodos históricos de Deribit + Polymarket, computa todas las variantes de D, inserta en `data/observations.db` del clon. **NO ejecutar el análisis todavía.**

### Paso 6 — Pre-registrar v2.0.0 (firmar antes de mirar)
Commit (o copia espejo timestamp) del `analysis_config.json` v2.0.0 ANTES de correr el backfill. Esto garantiza que la hipótesis se fijó antes de mirar los datos.

### Paso 7 — Correr backfill → DB de Exp2 se llena.

### Paso 8 — Correr análisis sobre Exp2
```powershell
py scripts/run_analysis.py --config analysis_config.json --output reports/phases/fase_7_final_analysis_exp2.json
```

### Paso 9 — Comparar veredictos Exp1 vs Exp2
Cuando ambos terminen (Exp1 ~2026-06-07, Exp2 cuando complete backfill).

## Reglas duras (NO NEGOCIABLES, mañana también aplican)

Todas heredadas de PROJECT_DESIGN §0:

- **READ-ONLY** sobre Polymarket, Deribit, Chainlink. NO trading, NO signing, NO wallets, NO secrets, NO órdenes reales.
- NO modificar `.env` (no existe en Exp2 todavía; cuando se cree, mismas reglas).
- NO tocar `data/` manualmente.
- NO modificar `PROJECT_DESIGN.md` sin autorización explícita de Pedro.
- NO tocar `controller.py` legacy.
- NO modificar `analysis_config.json` v1.0.0 de Exp1 (FROZEN).
- Exp2 vive 100% aislado en su carpeta; cero cross-talk con Exp1.

## Anti-cherry-picking (crítico)

Para que Exp2 sea científicamente válido:

1. **Pre-registrar v2.0.0 ANTES de mirar el backfill.** Si Pedro mira backfill primero, luego ajusta la hipótesis, eso ES cherry-picking.
2. **Backfill data debe ser data que NO hemos mirado todavía.** Los repos históricos identificados son aceptables si no se exploraron previamente.
3. **Veredicto AVANZA/FIN del Exp2 se acepta tal como caiga.** No re-ajustar umbrales si sale FIN.

## Estado de Exp1 (informativo, NO tocar)

- Recolección continua desde 2026-05-28T02:56Z.
- ~22-36% del objetivo de 1000 ventanas (creciendo ~4 ventanas/h).
- ETA a 1000: aproximadamente 2026-06-07.
- Logger corre desde `D:\openclaw\PROJECT DESIGN\` con `py -m src.logger --continuous`.
- Cuando llegue a 1000: correr `py scripts/run_analysis.py --output "reports/phases/fase_7_final_analysis.json"` para veredicto oficial.

## Archivos clave en Exp1 (referencia para Exp2)

| Archivo en Exp1 | Función | Reutilizable en Exp2 |
|-----------------|---------|----------------------|
| `analysis_config.json` v1.0.0 | Pre-registro Exp1 (FROZEN) | NO — Exp2 usa v2.0.0 nuevo |
| `src/analysis/config.py` | Carga inmutable | SÍ |
| `src/analysis/data.py` | Load + hash input | SÍ |
| `src/analysis/stats.py` | binomtest, bonferroni, kfold | SÍ |
| `src/analysis/gates.py` | 5 gates puros | SÍ |
| `src/analysis/verdict.py` | Consolidación + hash output | SÍ |
| `src/analysis/exploratory.py` | Sub-análisis exploratorios | SÍ |
| `scripts/run_analysis.py` | CLI determinista | SÍ |
| `tests/test_analysis_fixtures.py` | 16 tests sintéticos | SÍ |
| `data/observations.db` | DB de Exp1 | NO — Exp2 tiene DB propia |
| `src/continuous_logger.py` | Logger live | Probablemente NO (Exp2 usa backfill) |
| `src/deribit_feed.py` | Feed live Deribit | NO — reemplaza con backfill |
| `src/polymarket_feed.py` | Feed live Polymarket | NO — reemplaza con backfill |
| `src/chainlink_feed.py` | Chainlink RPC | NO si Exp2 usa solo precio Deribit |

## Plan maestro (referencia)

El plan completo de Exp2 vive en:
`C:\Users\User\.claude\plans\esto-es-algo-de-delightful-clarke.md`

Buscar dentro de ese archivo la sección **"Plan completo Exp2: Backfill histórico clonado (2026-05-31)"** para el detalle de las 6 fases (EXP2-0 a EXP2-6).

## Cierre

Este handoff es punto de continuación. Mañana abrir chat nuevo en `D:\EXPERIMENTOS BTC OPTIONS\`, leer este archivo PRIMERO, decidir hipótesis exacta de Exp2, y continuar desde Paso 3.

Nada del Exp1 se debe tocar mañana excepto consultas SELECT a la DB (read-only) si se necesita comparar muestras.

Logger sigue corriendo. Buenas noches.
