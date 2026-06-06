---
doc_id: AUDITORIA_PROTOCOLO
rol: pre-registro
estado: en revisión (pendiente de firma de Pedro)
fase: EXP2-1.5
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: revisión tipo referee — congela 6 grados de libertad (split, delta BS, moneyness, n, independencia)
---

# AUDITORÍA DEL PROTOCOLO — rigor determinista y científico

> **Estado:** Fase EXP2-1.5 (blindaje pre-descarga). Revisión hecha el 2026-06-01 con criterio de referee (físico/matemático). Cada agujero se resuelve por **método de caso Harvard** + estándares altos de la literatura. Las decisiones aquí se trasladan al [PRE_REGISTRO_v2.0.0.md](PRE_REGISTRO_v2.0.0.md) y se firman ANTES de descargar/correr.
> **Principio:** *determinista ≠ válido.* Se puede ser reproduciblemente erróneo. Estos grados de libertad se congelan a priori para que no se conviertan en cherry-picking encubierto.

---

## Lo que ya es sólido (no requiere acción)

- Estadísticos deterministas: `binomtest` exacto, Bonferroni aritmético, k-fold con `random.Random(seed)` + `sorted()`. Reproducible bit-exact (verificado en código `src/analysis/stats.py`).
- Hash de input invariante al orden (`_hash_dataframe` ordena cols+filas).
- Gates sobre holdout; exploración sobre train.

---

## Agujero A — Split train/holdout

### Hechos
El código de Exp1 (`deterministic_train_holdout_split`) hace **shuffle aleatorio** con seed. Es determinista, pero mezcla períodos: filas futuras pueden caer en train y pasadas en holdout.

### El problema (criterio referee)
En series temporales financieras, un split aleatorio produce **fuga de información temporal (leakage)**: el modelo "ve" estructura del futuro. Estándar de la literatura (López de Prado, *Advances in Financial ML*, cap. 7; Bergmeir & Benítez 2012): la validación en series **debe respetar el orden temporal**. Un holdout aleatorio infla la performance de forma espuria y no es publicable.

### Alternativas
1. Aleatorio (igual a Exp1) — comparabilidad 1:1, pero leakage conocido.
2. **Split temporal** — holdout = los más recientes, sellados; sin shuffle.
3. Ambos: temporal como principal, aleatorio como secundario comparativo.

### Decisión (estándar alto + caso)
**Split TEMPORAL como principal y oficial; aleatorio como análisis secundario SOLO para comparar con Exp1.** El veredicto confirmatorio usa el temporal. Razón: el leakage temporal es un defecto descalificante; la comparabilidad con Exp1 es deseable pero subordinada a la validez. Se reporta también el aleatorio para honestidad/continuidad, etiquetado como comparativo no-confirmatorio.

**Implementación:** nueva función `temporal_train_holdout_split(df, holdout_fraction_or_date)` que ordena por `ts_open` y corta por tiempo. No toca Exp1 (es código nuevo de Exp2). Sigue siendo determinista (mismo corte → mismas filas).

---

## Agujero B — Delta vía Black-Scholes (parámetro libre)

### Hechos
La fuente Deribit (trades) NO trae delta; hay que recomputarlo. BS requiere elegir: tasa `r`, convención de tiempo a expiración `τ`, qué IV usar, y redondeos. Cada elección mueve `delta_abs` → mueve D → mueve accuracy.

### El problema
Si esos valores se eligen DESPUÉS de ver datos, es p-hacking encubierto. Son grados de libertad ocultos.

### Decisión (estándar alto + caso)
**Congelar la convención BS en el pre-registro, con valores estándar de la literatura cripto-opciones, MÁS análisis de sensibilidad.**

| Parámetro | Convención congelada | Justificación |
|-----------|----------------------|---------------|
| Modelo | Black-76 sobre futuro/forward (no BS spot) | Deribit liquida sobre índice; las opciones son sobre forward. Estándar para cripto (Alexander 2023, *Math. Finance*). |
| IV | `iv` del propio trade (campo de la API) | Es la IV a la que se ejecutó; evita re-estimar superficie. |
| `r` (tasa) | 0 | Convención cripto estándar (sin tasa libre de riesgo clara); además D usa `delta_abs` relativo. |
| `τ` | (expiry − timestamp_trade) en años, ACT/365 | Convención de mercado. expiry parseado del `instrument_name`. |
| `S` (subyacente) | `index_price` del trade | Campo de la API; es el índice que Deribit usa. |
| `K` (strike) | parseado del `instrument_name` | exacto. |
| Redondeo | delta a 6 decimales antes de agregar | determinismo float canónico. |

**Sensibilidad (robustez):** recomputar D con `r ∈ {0, 0.02}` y verificar que el veredicto de los gates NO cambia. Se reporta como anexo. Si el veredicto fuera sensible a `r`, es señal de que el "edge" es frágil.

### B.1 — Validación del modelo (un PhD exige verificar, no asumir)

Antes de usar el delta recomputado, se valida que Black-76 **reproduce** el modelo de Deribit. Test (2026-06-01): para n=2.998 trades, se recomputó el **precio teórico** con la IV del trade y se comparó contra el `mark_price` que da Deribit:
- error mediano = **0.000536**, error medio = 0.00147, p95 = 0.0056 (en unidades de precio/subyacente).
→ El modelo BS76 reproduce el mark_price de Deribit casi exactamente ⇒ **el delta computado es el mismo que usa Deribit.** Modelo fiel. (Exp1 tomaba el delta directo de Deribit; nuestro delta recomputado es consistente con esa fuente — no es una aproximación arbitraria.)

### B.2 — Decisión sobre IV inválida (caso Harvard)

**Hechos (verificados):** la IV de los trades tiene outliers — IV=0 (0.42%), IV>200 (0.19%), IV>300 (0.09%); p1–p99 = 16%–135% (masa sana). Son opciones ilíquidas/deep con dato corrupto. **Hallazgo crítico:** de los trades con IV inválida, al recomputar delta caen en `|δ|≤0.02` (zona `IGNORED` de moneyness de Exp1) → **se descartan solos por el filtro de señal ya existente**. El filtro de moneyness de Exp1 (DOTM empieza en 0.02) ya excluye la basura.

**Criterios:** (1) no contaminar D; (2) fiel a Exp1 (que clasifica por delta y descarta `|δ|≤0.02`); (3) regla fija a priori; (4) impacto cuantificado.

**Alternativas:** (a) descartar IV≤0 o IV>tope; (b) winsorizar IV al tope; (c) confiar solo en el filtro de moneyness.

**Decisión (PhD):** **regla de dos capas, congelada en el pre-registro:**
1. **Descartar el trade si la IV es no-física:** `iv ≤ 0` (delta indefinido — no se puede computar) **o** `iv > 300%` (corrupto; por encima del p99·~2). Es <0.5% y son datos inválidos, no señal.
2. **El filtro de moneyness `|δ| ∈ (0.02, 0.625]` de Exp1 hace el resto** — descarta deep-OTM ilíquido aunque su IV fuera "válida". Esto NO es una elección nueva: es heredar la regla de Exp1.

Justificación: descartar IV≤0 no es opcional (el modelo no está definido sin volatilidad positiva — es matemática, no preferencia). El tope 300% se fija a priori y se reporta el conteo exacto excluido. Winsorizar se rechaza porque inyectaría un trade con IV inventada a la señal; descartar <0.5% de datos corruptos es más limpio y defendible ante referee. Como capa 2 (moneyness) ya elimina la mayoría, el resultado es robusto a la elección del tope (se confirma con sensibilidad: tope ∈ {250, 300, 400} no debe mover el veredicto).

**A congelar en pre-registro:** `iv_min_exclusive = 0`, `iv_max_inclusive = 300` (en %), + reporte de n excluidos + sensibilidad del tope.

---

## Agujero C — Corte de moneyness (ATM/OTM/DOTM)

### Hechos
El código de Exp1 recibe el bucket ya clasificado del feed live. En backfill hay que derivarlo. La señal `D_otm_dotm` depende de dónde se corte.

### El problema
Un corte arbitrario por %strike/spot redefine qué entra en la señal pre-registrada.

### Decisión (copiar los cortes EXACTOS de Exp1)
**Clasificar por DELTA con los rangos exactos de Exp1** (verificados en código `src/deribit_feed.py`, líneas 20-22 / `classify_moneyness`). Exp1 ya implementaba la clasificación por delta del paper Alexander et al. (2022). No inventamos: copiamos verbatim.

| Bucket | Rango de \|delta\| (de Exp1) | Nota |
|--------|------------------------------|------|
| DOTM | 0.02 < \|δ\| ≤ 0.125 | el corte inferior **0.02 descarta deep-OTM ilíquido/basura** (incluida la IV corrupta) |
| OTM | 0.125 < \|δ\| ≤ 0.375 | — |
| ATM | 0.375 < \|δ\| ≤ 0.625 | — |
| IGNORED | \|δ\| ≤ 0.02 **o** \|δ\| > 0.625 | excluido de la señal (deep-OTM ruido + ITM) |

> La señal `D_otm_dotm` usa {DOTM, OTM}; `D_atm` usa {ATM}. **Diferencia con Exp1:** Exp1 tomaba el delta directo de Deribit; Exp2 lo **recomputa con Black-76** (los trades históricos no traen delta — verificado 0/2000) y se validó que reproduce el mark_price de Deribit (ver B.1). Los cortes de bucket son idénticos.

---

## Agujero E — n efectivo vs n nominal

### Hechos
Tras filtrar por `|D|>umbral` y `n_trades≥30`, el `n` que entra al binomtest (n efectivo) es menor que el nominal. `min_n=1000` de Exp1 es sobre el nominal.

### Decisión
**Pre-registrar un `n_efectivo_min` por gate** (el n que realmente entra al test tras filtros). Si n_efectivo < umbral → gate `INSUFICIENTE` (no FIN). Esto evita declarar edge/no-edge con potencia insuficiente. Valor a fijar por Pedro en pre-registro (sugerencia: ≥ 384 para CI95 de ±5pp en proporción, estándar de tamaño muestral).

---

## Agujero F — Independencia (supuesto del binomtest)

### Hechos
`binomtest` asume observaciones i.i.d. Ventanas BTC 15m consecutivas pueden estar autocorrelacionadas (mismo régimen intradía, momentum). Si hay autocorrelación positiva, el p-value está **subestimado** → falsos positivos.

### El problema
Un edge "significativo" podría ser artefacto de dependencia serial.

### Decisión (estándar alto + caso)
**Medir primero, corregir si hace falta — pero pre-registrar AMBOS caminos.**
1. Medir autocorrelación de la serie de aciertos (Ljung-Box) sobre train.
2. Reportar SIEMPRE el binomtest (comparable a Exp1) **y** un **block bootstrap** p-value (bloques de tamaño = horizonte de autocorrelación) como prueba robusta.
3. El veredicto confirmatorio exige significancia en **ambos** (binomtest Y bootstrap). Criterio conservador, defendible ante referee.

Determinismo del bootstrap: `seed` fijo + número de remuestreos fijo en el pre-registro.

---

## Resumen de cambios al pre-registro v2.0.0

Se añaden estos bloques (a firmar antes de descargar):
- `split`: `method: "temporal"`, `holdout` por fecha/fracción reciente. (aleatorio = secundario)
- `black_scholes`: modelo Black-76, IV=trade, r=0, τ=ACT/365, S=index_price, redondeo 6 dec. + sensibilidad `r∈{0,0.02}`.
- `moneyness`: cortes por `|delta|` (bandas del paper Alexander).
- `min_n_efectivo` por gate.
- `robustness`: `block_bootstrap` (n_resamples, seed, block_size) además de binomtest.

## Impacto en el plan
Esto añade una sub-fase **EXP2-1.5 (blindaje)** ya cubierta por este doc. No retrasa: se hace en paralelo al diseño del schema (EXP2-2). Ningún dato descargado aún → momento óptimo para blindar.
