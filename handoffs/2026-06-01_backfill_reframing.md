---
doc_id: HANDOFF_2026-06-01
rol: bitacora
estado: histórico (archivado)
fase: pre-EXP2-0
version: 1.0
creado: 2026-06-01
uso: handoff cronológico — decisión datos-primero, las 6 palancas, re-framing
---

# HANDOFF EXP2 — 2026-06-01 (actualización sobre el de 2026-05-31)

## TL;DR para arrancar mañana

1. Abrí chat nuevo en VS Code apuntando a `D:\EXPERIMENTOS BTC OPTIONS\`.
2. Leé este archivo PRIMERO, luego `HANDOFF_EXP2_2026-05-31.md` para contexto inicial.
3. Pegá las URLs de los 2 repos de backfill (Deribit + Polymarket).
4. **NO empezar por estrategia.** Empezar por: **ordenar y descargar datos primero**.
5. Estrategia se decide DESPUÉS de tener data validada en formato canónico.

---

## Estado al cierre de hoy (2026-06-01)

- **Folder Exp2:** sigue vacío excepto handoffs. No se clonó código todavía.
- **Logger Exp1:** sigue corriendo intacto. NO se detuvo. NO se tocó.
- **Exp1 a las 23:00Z:** ~453 ventanas totales / 358 con `|D|>5` (~36% del objetivo 1000).
- **Veredicto preliminar Exp1:** WAIT_FOR_MORE_DATA (todos los gates INSUFICIENTE, esperado).
- **Última corrida análisis Exp1:** `reports/phases/fase_7_preliminary_2026-06-01.json` con hash `2114bb45a9b7737e...`.

---

## Lo nuevo que se discutió hoy

### 1. Hallazgos preliminares Exp1 confirman el patrón del paper

Tabla de variantes (n=358 con |D|>5):

| Variante | n_all | acc_all | n con \|D\|>5 | acc \|D\|>5 |
|----------|------:|--------:|-------------:|------------:|
| **D_5m_otm_dotm** | 355 | **54.93%** | 39 | 48.72% |
| D_10m_otm_dotm | 358 | 49.72% | 69 | 49.28% |
| D_15m_otm_dotm ← pre-registrada | 358 | 48.32% | 104 | 50.96% |
| D_5m_atm | 321 | 47.98% | 52 | 42.31% |
| D_10m_atm | 349 | 50.43% | 87 | 52.87% |
| D_15m_atm | 356 | 50.00% | 103 | 50.49% |

Lectura: el paper Alexander et al. (2022) predice (a) edge en OTM+DOTM no ATM, (b) degradación de señal en ~1h. Los datos confirman: D_5m_otm_dotm tiene la accuracy más alta sin filtro (54.93%), y las variantes ATM están casi en 50%. La variante pre-registrada D_15m_otm_dotm está casi en moneda — consistente con "señal direccional débil pero presente" del paper.

### 2. El umbral `|D|>5` está mal diseñado

Brackets exploratorios revelan que accuracy NO es monotónica con magnitud de D:
- `[5,10)` parece sweet spot
- `[10,20)` baja a 48.6%
- `[20,100)` sube a 52%
- `[100,∞)` cae a 33% (n=3)

Implicación: el umbral binario es arbitrario. El paper original usa regresión continua, no clasificación. Exp2 debería considerar ponderación continua en vez de corte.

### 3. Last-tick risk confirmado

~6% de ventanas son FLIPs Chainlink↔Polymarket. Mediana movimiento BTC: $12 (flippy) vs $67 (estables). Ventanas tranquilas las decide ruido microstructural del último segundo, no la señal D.

### 4. Re-framing del proyecto: meta = ganar dinero

Cambio conceptual importante para Exp2:

- **Hasta ahora (Exp1):** edge se define solo sobre outcome final (Up/Down a 15min). Estrategia implícita: apostar al `ts_open` y esperar al cierre.
- **A partir de Exp2:** el edge puede vivir sobre el **movimiento intra-ventana de `pm_up_price`**, no solo sobre outcome. Si D predice movimiento del precio del contrato Up en los próximos N segundos, se puede entrar y salir antes del cierre.

Esto abre el espacio de estrategias:
- **A:** entrar al `ts_open`, salir al `ts_close` (Exp1).
- **B:** entrar al `ts_open`, salir cuando `pm_up_price` se mueve ≥X% favorable (take-profit intra-window).
- **C:** entrar al `ts_open`, salir si se mueve ≥X% contra (stop-loss intra-window).
- **D:** entrar TARDE en la ventana si D sigue apuntando y precio aún no se ajustó (lead-lag explotado).

**Regla dura preservada:** Exp2 sigue siendo VALIDACIÓN, no ejecución. PROJECT_DESIGN §0 vive. Ejecución es hipotético Exp3/Nivel 2, fuera de alcance.

### 5. Las 6 palancas de afinación posibles para hipótesis Exp2

Ordenadas por respaldo teórico:

1. **Variante temporal corta** (`D_5m_otm_dotm` en vez de `D_15m`). Justifica: paper predice degradación rápida.
2. **Filtro de calidad de mercado** (`n_trades_5m >= X mínimo`). Justifica: señal se construye sobre trades reales.
3. **Filtro de volatilidad observada** (skip ventanas tranquilas/flippy). Justifica: hallazgo de last-tick risk en Exp1.
4. **Magnitud sin umbral binario** (ponderación continua). Justifica: paper usa regresión, no corte.
5. **Combinación D × V** (señal direccional condicionada a vol alta). Justifica: paper dice desbalance predice vol mejor que dirección.
6. **Ensemble D_5m + D_10m + D_15m concordando** (consenso entre horizontes).

**Recomendación inicial:** combinar palancas 1 + 3 (`D_5m_otm_dotm` + filtro de vol mínima). Pero Pedro decide en chat nuevo, ANTES de tocar backfill.

---

## Decisión operativa hoy: datos primero, estrategia después

Pedro confirmó: antes de pre-registrar hipótesis/estrategia de Exp2, hay que **ordenar y descargar los datos**.

Razón: sin formato canónico de datos validado, cualquier hipótesis es prematura. Si el backfill no incluye `pm_up_price` intra-ventana, descarta automáticamente las estrategias B/C/D.

### Fase A — Inventario de fuentes (chat nuevo paso 1)

Pedro pega los 2 repos identificados:
- **Repo 1:** Deribit histórico (trades de opciones BTC, formato, periodo cubierto).
- **Repo 2:** Polymarket histórico (markets `btc-updown-15m-*`, qué campos exponen, formato).

Necesito de Pedro al pegar las URLs:
- ¿Qué campos tiene cada uno?
- ¿Qué periodo cubren?
- ¿Polymarket trae `pm_up_price` intra-ventana o solo outcome?
- ¿Deribit trae trades clasificables por moneyness/delta o necesitamos enriquecer?
- ¿Hay rate limits o requiere descarga masiva por bloques?

### Fase B — Diseño del schema canónico Exp2

Una vez vista la data, diseñar `data/observations_exp2.db` schema:
- Tabla `observations` (igual que Exp1 para reutilizar `src/analysis/`).
- Tabla `observations_intrawindow` SOLO si el backfill Polymarket lo permite. Si no, omitir y descartar estrategias intra-window.
- Tabla nueva `backfill_provenance` para trazabilidad: qué fila vino de qué fuente, qué fecha de descarga, qué hash de bloque.

### Fase C — Pipeline de backfill determinista

`scripts/backfill_data.py`:
- Lee `analysis_config.json` v2.0.0 (periodo histórico declarado).
- Descarga por bloques de los 2 repos.
- Computa todas las 6 variantes de D + V + n_trades.
- Inserta en `data/observations_exp2.db`.
- Imprime SHA256 del .db al final.

`scripts/verify_backfill_determinism.py`:
- Corre el backfill 2 veces con mismo periodo.
- Verifica mismo hash en ambas corridas.
- Si difiere → racing/orden no determinista, fix obligatorio.

### Fase D — Solo entonces pre-registrar v2.0.0

Después de Fase A/B/C completas y data validada en formato canónico:
- Pedro decide hipótesis (1 + posiblemente exploratorias secundarias).
- Pedro decide estrategia (A/B/C/D según lo que el backfill permita).
- Pedro decide periodo de holdout temporal (últimos N meses sin tocar hasta corrida final).
- Pedro firma `analysis_config.json` v2.0.0.
- Solo entonces correr análisis.

---

## Reglas duras (reforzadas)

- READ-ONLY sobre toda fuente externa. NO trading, NO signing, NO wallets, NO secrets.
- NO modificar `PROJECT_DESIGN.md`.
- NO modificar `analysis_config.json` v1.0.0 de Exp1.
- NO tocar `data/` de Exp1 manualmente (solo SELECTs read-only si se necesita comparar).
- Exp2 vive 100% aislado en `D:\EXPERIMENTOS BTC OPTIONS\`.
- Pre-registro v2.0.0 se firma **antes** de mirar el backfill (anti-cherry-picking).
- Si el backfill solapa temporalmente con datos de Exp1, declarar el solape y considerar exclusión.

---

## Anti-cherry-picking (tentaciones específicas a evitar)

| Tentación | Trampa | Defensa |
|-----------|--------|---------|
| "Probemos 4 estrategias, declaramos la mejor" | Selección post-hoc | Pre-registrar UNA principal, otras como exploratorias |
| "El veredicto salió FIN, ajustemos umbral" | p-hacking | Cambiar requiere Exp3 con datos nuevos |
| "Optimicemos periodo histórico que da mejor resultado" | Cherry-picking de periodo | Periodo se pre-registra antes de correr backfill |
| "Filtramos noise post-hoc" | Filtros decididos después de mirar = invalidante | Filtros se declaran en pre-registro |
| "Usamos data que ya miramos en Exp1" | Doble dipping | Si solapa, declarar y excluir |

---

## Archivos en `D:\EXPERIMENTOS BTC OPTIONS\` al cierre de hoy

```
HANDOFF_EXP2_2026-05-31.md      ← handoff inicial
HANDOFF_EXP2_2026-06-01.md      ← este archivo (actualización)
```

Nada más. Folder vacío esperando datos.

---

## Próximo paso concreto (chat nuevo mañana)

```
1. Abrir VS Code en D:\EXPERIMENTOS BTC OPTIONS\
2. /init o nuevo chat con Claude Code
3. Leer este handoff + HANDOFF_EXP2_2026-05-31.md
4. Pedro pega las URLs de los 2 repos de backfill
5. Claude inventaría qué tiene cada repo (sin descargar todavía)
6. Diseñar schema canónico
7. Implementar pipeline determinista
8. SOLO ENTONCES pensar en estrategia
```

Logger Exp1 sigue corriendo. Buenas noches.
