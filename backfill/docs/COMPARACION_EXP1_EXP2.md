---
doc_id: COMPARACION_EXP1_EXP2
rol: bitacora
estado: cierre
fase: EXP2-9
version: 1.0
creado: 2026-06-02
uso: cierre del experimento — veredicto, comparación con Exp1, limitaciones honestas
---

# EXP2-9 — Cierre: veredicto, comparación con Exp1, limitaciones

## ⛔⛔ VEREDICTO RETRACTADO (2026-06-02): era LOOKAHEAD BIAS — NO hay edge predictivo

> **TODO LO QUE SIGUE ABAJO ESTÁ INVALIDADO.** El agente de Exp1 detectó que Exp2 calculó D con trades de DURANTE la ventana `[ts_open, ts_close)` en vez de ANTES `[ts_open−15min, ts_open)`. Eso es lookahead: el flujo de opciones durante la ventana y el outcome de esa ventana son ambos consecuencia del mismo movimiento de BTC → correlacionan por construcción, no por poder predictivo.
>
> **Test (nuestros datos, read-only):** D concurrente → 60.7% (artefacto); D predictivo correcto → **48.2%, NO significativo**. Exhaustivo en 9 variantes: predictivo 45-49% en todas. **NO existe edge predictivo en la señal D sobre estos datos.**
>
> **Exp1 (~51%) medía bien todo el tiempo.** El "bug del logger Exp1" que este doc diagnostica más abajo NO era bug — Exp1 calculaba D predictivo (correcto), Exp2 concurrente (con lookahead). El veredicto real de ambos converge: **NO_EDGE.**
>
> Lo de abajo se conserva como registro del error y su detección.

## (INVALIDADO) VEREDICTO: EDGE_VALIDATED (histórico) + replicación forward "confirmada"

**Lectura honesta tras los dos tests (2026-06-02):**
1. Edge real y fuerte en el dataset histórico (dic-abr): **60.7%**, 5/5 gates, auditado sin look-ahead/survivorship/correlación serial.
2. Primer test (D pre-calculado de Exp1) sugirió "no replica forward (51%)" — pero ese test usó el D defectuoso de Exp1.
3. **Test correcto (D recalculado Black-76 sobre período de Exp1): 66.95%** → el edge SÍ replica forward. El 51% era un **bug de cálculo de D del logger live**, NO régimen.

**Caveat de tamaño:** el test forward tiene n=118 (CI ancho [57.7%, 75.3%]). Fuerte pero no definitivo — se confirma cuando Exp1 (con D arreglado) o más backfill llegue a n grande. Sigue siendo VALIDACIÓN, no ejecución.

## Veredicto de Exp2 sobre el dataset histórico: **EDGE_VALIDATED**

Sobre el dataset completo (7.799 ventanas BTC 15m, dic-2025→abr-2026, backfill histórico), con la hipótesis pre-registrada `D_15m_otm_dotm`, `|D|>5`, los **5 gates AVANZAN**:

| Gate | Pregunta | Métrica | Umbral | Veredicto |
|------|----------|---------|--------|-----------|
| 1 — D vs moneda | ¿sign(D) acierta el outcome? | **acc 60.7%**, p<1e-4 | ≥55% & p<0.01 | AVANZA |
| 2 — D vs mercado | ¿acierta con mercado indeciso [0.45,0.55]? | acc 60.5% | ≥55% & p<0.01 | AVANZA |
| 3 — lead/lag | ¿la señal precede al precio? | mediana 81s | ≥30s | AVANZA |
| 4a — offset base | ¿Deribit-index ≈ Chainlink-close? | ratio 0.99 | <1.0 | AVANZA |
| 4b — costos | ¿EV neto > 0 tras fee+spread? | **EV +0.064/apuesta** | ≥0.005 | AVANZA |

`output_hash`: `5de32306…` (determinista). Bootstrap robustez: p≈0.

## Validación secundaria (holdout temporal — datos NUNCA vistos)

El 30% más reciente (mar-abr 2026), sellado durante toda la exploración:
- **Gate 1 accuracy = 62.1%** (incluso mejor que el completo), bootstrap p=1e-09.
- Veredicto formal del holdout = `WAIT_FOR_MORE_DATA` **solo** porque n(|D|>5)=678 < min_n 1000 (límite de potencia del split 30%, NO una falla de la señal).

**Lectura correcta (sin suavizar):** la señal se ve más fuerte en holdout (62.1%), lo cual es real e importante (sugiere robustez en datos no vistos). **PERO el criterio formal pre-registrado (n≥1000) NO se cumplió** en el holdout (n=678). Por lo tanto el holdout es **sugestivo, no confirmatorio formal**. El veredicto EDGE_VALIDATED se sostiene por el **dataset completo** (que sí cumplió), NO por el holdout.

## ✅ RESOLUCIÓN: el edge SÍ replica forward — Exp1 calculaba D mal (test 2026-06-02)

**Test definitivo (sugerido por Pedro):** usar los OUTCOMES de Exp1 + recalcular D con el método de Exp2 (Black-76) sobre trades históricos del período de Exp1 (may-jun, bajados de history.deribit.com). Aísla la variable "cálculo de D".

**Resultado:**
- **Accuracy con MI D sobre el período de Exp1: 66.95%** (n=118, CI95 [57.7%, 75.3%]). NO 51%.
- **D_exp1 vs D_mio: correlación −0.016, coincidencia de signo 53.6%.** Son señales casi NO relacionadas.

**Conclusión (3 hipótesis resueltas):**
- A (régimen, edge no generaliza) → **DESCARTADA**: con D bien calculado, may-jun da 67%.
- B/C (Exp1 mide D mal) → **CONFIRMADA**: el D del logger live y el D Black-76 no correlacionan.

**El edge ES real y SÍ generaliza forward.** El ~51% de Exp1 era un **defecto del cálculo/recolección de D en vivo** (WebSocket perdiendo trades, delta directo vs Black-76, o ambos) — NO un cambio de régimen. → Tarea nueva: auditar/arreglar el cálculo de D del logger de Exp1 (fuera del alcance de Exp2, pero crítico).

## 🚩 (Histórico) El falso susto del régimen — superado por el test de arriba

**El problema:** Exp1 (live, may-jun 2026) está en **50.86%** (n=116, |D|>5, n_trades≥30), CI95 [41.4%, 60.3%]. El 60.7% de Exp2 cae en el borde/fuera. **No es solo "ruido de poca muestra"** — son estadísticamente distinguibles.

> ⚠️ **ESTA SECCIÓN QUEDÓ INVALIDADA por el test correcto (ver sección "RESOLUCIÓN" arriba). Se conserva como registro del razonamiento.** El "test A-vs-B" de abajo usó el D **ya guardado por Exp1** (NO el mismo cálculo — ese era el error). Cuando se recalculó D con Black-76, dio 67%, no 51%.

**Primer test (DEFECTUOSO — usó D pre-guardado de Exp1, no recalculado):**
| Variante | n | accuracy (con D de Exp1) |
|----------|---|--------------------------|
| D_15m_otm_dotm | 116 | 50.9% |

Esto SUGIRIÓ "régimen", pero era un artefacto: el D guardado por Exp1 está mal calculado (corr −0.016 con Black-76). El test correcto (recalcular D) dio 67% → **es cálculo, NO régimen.**

## Pendientes (tras la resolución)

1. **Auditar/arreglar el cálculo de D del logger live de Exp1** (bug confirmado: su D no correlaciona con Black-76).
2. **Confirmar forward con n mayor** (el test correcto fue n=118, CI ancho).
3. **Exp3 paper trading** — precondición (replicación forward) cumplida en evidencia preliminar.
4. La decisión Exp3 **espera** este resultado. No se cierra operativo antes.

## Comparación Exp1 vs Exp2

| | Exp1 | Exp2 |
|---|------|------|
| Datos | recolección live | **backfill histórico** (independiente) |
| n | objetivo 1000 (en curso) | **7.799** ventanas |
| Periodo | mayo-jun 2026 (live) | dic-2025 → abr-2026 |
| Señal D | delta directo de Deribit | **delta recomputado Black-76** (validado vs mark_price) |
| Outcome | Polymarket gamma | **CLOB winner** (autoridad) |
| Split | aleatorio 70/30 | **temporal** 70/30 (anti-leakage) + completo |
| Accuracy D_15m | ~54-60% preliminar | **60.7%** (completo), 62.1% (holdout) |
| Veredicto | (pendiente al cierre de Exp1) | **EDGE_VALIDATED** |

**Consistencia con el paper (Alexander et al. 2022):** confirmado — la señal direccional vive en OTM/DOTM, y el edge es real pero modesto (~60%, no 90%). Coincide con "señal direccional débil pero presente".

**Replica:** Exp2 reproduce y **fortalece** la dirección de Exp1, con datos independientes, más muestra, y rigor metodológico añadido (split temporal, delta validado, bootstrap).

## Auditoría de las 5 verificaciones críticas (pre-firma, 2026-06-02)

| # | Verificación | Resultado | Evidencia |
|---|--------------|-----------|-----------|
| 1 | Variante de D | **D_15m_otm_dotm = idéntica a Exp1 → es REPLICACIÓN** | config v2.0.0 |
| 1b | Salto 50.96%→60.7%? | **No es salto real**: el 50.96% de Exp1 era con n~104 (CI95 ±9.6pp → indistinguible de 60%). Exp2: n=2.408 (75×). | binom CI |
| 2a | Sesgo supervivencia | **Bajo**: cobertura mediana 99% (95/96 markets/día); CLOB resolvió 9231/9231 limpio. Días incompletos (24%) = gaps técnicos del colector, NO exclusión por outcome (aleatorio respecto a aciertos). | conteo días |
| 2b | Look-ahead en pm_up_price_open | **NO hay**: primer tick a mediana 16s tras apertura (p10=0); **0 ticks antes de ts_open**. Precio real del arranque, no rellenado. | timing trayectoria |
| 2c | Sesgo selección mercados | **No**: usamos 100% (9231); filtro n≥30 deja 84.5%, descarta ilíquidos (correcto). | conteos |
| 3 | Periodo | dic-2025→abr-2026 (~4 meses). NO solapa Exp1. Riesgo régimen único (ver limitación 1). | dataset |
| 4 | Correlación serial | **Despreciable**: ACF ~±0.02 todos los lags; n efectivo ≈ nominal; p con n efectivo = 5.9e-27. Bootstrap por bloques: p≈0. | ACF + bootstrap |

## Limitaciones (declaradas honestamente)

1. **Periodo acotado (~4 meses)** → riesgo de régimen único. El edge podría no generalizar a otros regímenes. (btc-updown-15m no existe antes de ~ago-2025.)
2. **Delta recomputado** (el histórico no trae delta directo). Mitigado: validado vs mark_price (err 0.0005); sensibilidad a `r` pendiente como anexo.
3. **El holdout NO cumplió el criterio formal pre-registrado.** El pre-registro v2.0.0 fijó n≥1000 para veredicto. El holdout temporal tiene n=678 (<1000) → su veredicto formal es `WAIT_FOR_MORE_DATA`. **Dos cosas verdaderas a la vez:** (a) la señal se ve MÁS fuerte en holdout (62.1%, p=1e-09) — real e importante; (b) el criterio formal NO se cumplió en ese subset. El holdout es **sugestivo, NO confirmatorio formal**. El veredicto EDGE_VALIDATED descansa en el **dataset completo** (n=2.408>1000), que SÍ cumplió. Origen: `min_n=1000` heredado de Exp1 era para dataset completo, no para un split 30% — error de calibración detectado en EXP2-8 antes de ver accuracy del holdout.
4. **Cobertura diaria irregular** (24% de días con <80 markets, gaps del colector). No sesga accuracy (aleatorio respecto a aciertos) pero reduce ligeramente el n efectivo en esos días.
5. **Es VALIDACIÓN, no ejecución.** PROJECT_DESIGN §0: registra, no opera. Trading = Exp3/Nivel 2 fuera de alcance, requiere autorización explícita.

## Hipótesis para Exp3 (del barrido exploratorio, NO parte de este veredicto)

El barrido en train mostró que el edge existe en TODOS los umbrales y que **participar en más mercados da más ganancia TOTAL** (|D|>0: ~245u vs |D|>5: ~102u), aunque menor EV por apuesta. → Exp3 podría pre-registrar un umbral bajo (más mercados) y validarlo en datos nuevos. **NO se usó para cambiar el |D|>5 de Exp2** (sería cherry-picking).

## Handoff a Exp3 (NO es trading real)

**Precondición**: Exp3 NO arranca hasta resolver la replicación forward (Exp1 ≥55% a n=1000). Si el edge no generaliza, no hay nada que paper-tradear.

Si procede, **Exp3 = paper trading / dry-run** (NO dinero real). Debe incluir:
- **Walk-forward MES A MES** (no solo agregado) — ver si el edge es estable en el tiempo o solo vivió en un régimen.
- Latencia simulada real explícita (1-3s de colocación de orden).
- Spread bid-ask real (no midpoint) + **slippage por tamaño de orden** (del order book real).
- **Capacity sizing**: ¿qué tamaño máximo por market antes de que el edge se evapore?
- Métricas de cartera: **Sharpe / Sortino / max-drawdown**, no solo accuracy+EV.
- Mínimo 2-4 semanas de dry-run.
- Hipótesis del barrido: pre-registrar umbral bajo (más mercados = más ganancia total) con datos nuevos.

Solo si Exp3 confirma viabilidad operativa → discusión de "Nivel 2 con capital real", que sigue siendo decisión fuera del alcance técnico y requiere autorización explícita de Pedro.

## Tercera confirmación independiente (en paralelo)
Exp1 sigue recolectando live (ETA n=1000 ~ inicios jun-2026). Su veredicto final será una **tercera confirmación independiente** — datos live, ventanas que nunca estuvieron en el backfill de Exp2.

## Estado final
EXP2-0..9 cerradas. Veredicto: **EDGE_VALIDATED sobre el dataset HISTÓRICO** (dic-2025→abr-2026; 5/5 gates, acc 60.7%, EV neto +0.064, sin look-ahead/survivorship/correlación serial — auditado). **PERO la replicación forward NO está confirmada**: Exp1 live (may-jun) está en ~51%, y el test A-vs-B mostró que es cambio de RÉGIMEN, no microestructura. El edge histórico es real pero **no generaliza (aún) al período live**. **NO es EDGE_VALIDATED operativo.** Decisión Exp3 espera Exp1 a n=1000: si ≥55% procede paper trading; si <55%, reabrir investigación de régimen. Sigue siendo VALIDACIÓN, nunca ejecución sin autorización explícita.
