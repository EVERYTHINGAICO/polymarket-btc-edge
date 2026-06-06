---
doc_id: HALLAZGOS_DATOS_FINOS
rol: bitacora
estado: veredicto (Etapa 3 — re-test con datos finos tick-by-tick)
fase: microestructura / datos finos (Exp4)
version: 1.0
creado: 2026-06-03
uso: veredicto del re-test de hipotesis con datos tick-by-tick + orderbook ejecutable real. Leer junto con ESTADO_PROYECTO y PLAN_MAESTRO_ETAPAS.
---

# HALLAZGOS — Re-test con datos FINOS (tick-by-tick + orderbook ejecutable)

> Método del caso de Harvard: hechos → criterios → alternativas → decisión razonada → riesgos.

## 0. Resumen ejecutivo (una frase)

**Con los datos más finos posibles (tick a 0,1s + spot en ms + ask ejecutable real del orderbook), NO existe edge direccional para el TOMADOR: el precio del mercado es eficiente/calibrado, y cada "edge" aparente se evapora al usar el ask real en vez de un precio sintético. La ganancia de los bots está del lado MAKER (cobrar el spread que el tomador paga), no en predecir.**

## 1. HECHOS (los datos y qué se midió)

### Datos adquiridos (Etapa 1, verificada)
| Fuente | Cobertura | Granularidad |
|--------|-----------|--------------|
| Ticks Polymarket BTC 15m | 20,47M ticks, Mar13–Abr26 2026, 3.826 markets | **0,1s** (mediana gap), ~123 trades Up en los primeros 60s |
| Spot BTC (en cada tick) | abril (~4,8M ticks; marzo casi sin spot) | **ms** |
| Orderbook (best_bid/ask/sizes) | 866M filas raw + 94M snapshots, Mar29–Abr20, 1.028 windows | ask **ejecutable real** |
| Outcomes (CLOB, autoritativo) | research_v1, 9.225 windows | resolución oficial |

**Universo limpio analizable** (research_v1 ∩ ticks, outcome autoritativo): **1.488 ventanas** (con precio en t\*), **971** (con orderbook/ask real). Período Mar13–Abr20.

### Diseño del test (anti-lookahead estricto)
- Momento de decisión **t\* = ts_open + 60s** (y 300s como control). Se entra DURANTE la ventana, como los bots.
- Toda feature usa info con timestamp **≤ t\***; el outcome se resuelve en ts_close (t\*+840s). Spot y precio son timestamps reales ≤ t\* (no velas que cierran en el futuro → sin el lookahead de 59s que nos engañó antes).

### Resultados (t\*=60s salvo indicado)
| # | Señal / hipótesis | Resultado | Lectura |
|---|-------------------|-----------|---------|
| 1 | `sign(spot − línea)` (BTC ya cruzó) | **55,85%** | informativa pero **dominada por el precio** |
| 2 | `sign(precio − 0,5)` (lo que dice el mercado) | **59,70%** | el precio predice MÁS que el spot |
| 3 | **Calibración del precio** (bins 0,3–0,7) | gaps **±2–4pp** | **bien calibrado**: precio ≈ P(outcome) |
| 4 | EV de **comprar al favorito** @ precio negociado | **−3,2%** (acc 59,8% vs break-even 63,0%) | predecir ≠ ganarle al precio |
| 5 | **Lag/latencia**: cuando spot y precio discrepan | gana el **PRECIO** (57,2% / 45,8%) | el contrato **lidera** al spot, NO va retrasado → no hay lag que explotar |
| 6 | **Favorite-longshot** (comprar lado barato en extremos) — precio sintético | +13,4% (¡trampa!) | usaba último precio negociado, NO ejecutable |
| 6b| **Favorite-longshot con ASK REAL del orderbook** | **−6,0%** (spread 3,5pp del lado barato) | el "edge" era artefacto de precio no-ejecutable |
| 7 | **Order flow** (BUY−SELL Up, side+size del tick) | direccional **52,35%** (< break-even 52,7%), corr 0,10, redundante con precio | no agrega edge de tomador |

## 2. CRITERIOS (qué cuenta como edge, fijados de antemano)

1. **EV ejecutable** = `win·1 − ask_real·(1+fee) > 0`. El **ask real** del orderbook, NUNCA el precio medio ni el último negociado. (fee Polymarket: 1,8% taker.)
2. **Ganarle al precio**, no solo predecir: si el precio está calibrado (precio ≈ P), no hay EV aunque la "accuracy" sea 60%.
3. **Robustez**, no bins post-hoc: n suficiente, no subgrupos chicos elegidos a posteriori.
4. **Anti-lookahead estricto**: verificado timestamp por timestamp (spot/precio ≤ t\*, outcome en ts_close).

## 3. ALTERNATIVAS consideradas (y por qué cada una cayó)

- **Momentum de spot fino** (la duda que quedó de Exp2): a 60s el spot crudo da 55,85% pero el **precio lo domina** (59,7%) → no aporta. Sin el lookahead de velas, no hay momentum-edge.
- **Latencia (lead-lag contrato↔spot)**: refutada — el contrato lidera al spot, no al revés.
- **Favorite-longshot / fade extremos**: el patrón existe en la calibración (extremos sesgados) pero **NO sobrevive al ask real** (−6,0%). El sesgo es real; capturarlo como tomador no lo es.
- **Order flow (microestructura del contrato)**: 52,35% direccional, por debajo del break-even; el precio ya incorpora el flujo. Un subgrupo (precio>0,55 ∧ flujo<0, **n=42**) mostró Δ+24,6pp pero es n chico post-hoc → **no se persigue** (es el patrón de cherry-pick que ya nos engañó).

## 4. DECISIÓN RAZONADA (veredicto)

**NO_EDGE_TOMADOR_FINO.** A granularidad tick con ask ejecutable real:
- El precio del mercado es **eficiente y está calibrado** (precio ≈ probabilidad real).
- Ninguna señal computable (spot, momentum, lag, extremos, order flow) le gana al precio lo suficiente para EV>0 **después del ask real + fee**.
- Cada "edge" aparente (54%, 13,4%) provino de usar un **precio no ejecutable** (medio, o último negociado por debajo del ask). Corregido con el ask real → negativo.

### Reconciliación con "los bots SÍ predicen, me consta"
Ambas cosas son ciertas y no se contradicen:
1. **Los bots predicen — y por eso el precio es eficiente.** El precio ES el agregado de sus predicciones; está calibrado porque ellos lo arbitran. "Predicen" se manifiesta como un precio que ya nadie le gana fácil.
2. **Pero ganan como MAKER, no como tomador.** El spread que medimos (≈3,5pp en extremos) es **su ingreso** y **nuestro costo**. Cobran ese spread posteando límites + velocidad. No ganan pagando el ask para apostar una predicción — eso (lo que probamos) pierde.

## 5. RIESGOS Y LIMITACIONES (honestidad)

- **Período corto** (~5–6 semanas, Mar13–Abr20) y **solapa** con el holdout ya usado de Exp2 → NO es dato virgen. El veredicto null es robusto (varias pruebas coinciden), pero un edge marginal necesitaría validación virgen.
- **n moderado** (1.488 / 971 con ask) → un holdout fresco sería chico; potencia limitada para efectos finos.
- **Subgrupo n=42** (order flow × precio alto) quedó abierto: probablemente ruido; requeriría holdout sellado + ETH/SOL para creerle. NO se reportó como edge.
- **t\* = 60s y 300s**: no se barrió exhaustivamente cada instante de decisión.
- **Validación virgen pendiente**: ETH/SOL (mismo dataset, otro activo) es el camino limpio para confirmar el null y/o testear el residual.

## 6. QUÉ ABRE ESTO (la frontera no explorada: el lado MAKER)

Todo lo probado fue del lado **tomador** (pagar el ask para apostar). El veredicto empuja la pregunta real de "cómo ganan los bots 24/7" hacia el lado que **no hemos estudiado**:

> **¿Una estrategia MAKER (postear órdenes límite, cobrar el spread) es rentable después de la selección adversa?**

- Coincide con lo que el usuario observó: *"casi todos los bots hacen orden límit… van escalando".*
- Tenemos **todos los datos** para estudiarlo (orderbook 866M + outcomes): simular postear al bid/ask, medir tasa de fill y el outcome de lo que se llena (adverse selection: te llenan en los perdedores).
- Caveat estructural: ejecutarlo requiere infra de velocidad (competir con otros makers) y este proyecto es **READ-ONLY / registra-no-opera** → se puede **estudiar/medir**, no operar.

## 8. ESTUDIO MAKER (Exp5) — ¿es ahí donde ganan los bots?

Medición del PnL **realizado** del maker usando fills reales (ticks) + outcomes reales: cada trade tiene un maker del lado opuesto al tomador; `pnl_maker = ±(precio − outcome)` según lado. Esto netea la selección adversa por construcción (usa los fills que de verdad ocurrieron). maker fee = 0. Verificado que `side`=lado del tomador (BUY pega al ask, SELL al bid). Scripts: `scripts/study_maker.py`, `study_maker_robust.py`, `study_maker_regime.py`.

**Headline:** 5,28M fills, $69,3M volumen → PnL maker **+$1,53M = +2,207%/$** (neto de selección adversa). Making aparentemente rentable.

**Pero la robustez lo califica fuertemente — NO es un edge simple/estable:**

| Chequeo | Resultado | Lectura |
|---|---|---|
| Por **lado** | VENDE Down +5,76%, VENDE Up +0,87%, COMPRA Up −4,75%, COMPRA Down −7,07% | gana **vendiendo** a compradores; **comprar** es tóxico (los vendedores están informados) |
| **Estabilidad temporal** | 1ª mitad −0,12%, 2ª mitad +3,46% | **no estable** en el tiempo |
| **Por ventana** | solo **35% positivas**, mediana **−1,87%**, media −0,73% | la ventana típica PIERDE; el agregado lo cargan pocas |
| **Por quintil de volumen** | Q1–Q3 (60% ventanas) −1 a −3%; **Q5 (alto vol) +4,84%** | el edge vive ENTERO en alto volumen |
| Régimen (Up/Down) | balanceado (814/759); gana en Up (+2,87%) y Down (+1,46%) | **no** es apuesta direccional disfrazada |

**Veredicto maker:** existe PnL maker real, pero **concentrado en las ventanas de alto volumen** (FOMO chasing un movimiento; el maker vende a los que persiguen y el movimiento continúa), **asimétrico** (solo el lado vendedor) y **negativo en la ventana mediana**. Capturarlo exige ser **rápido + selectivo + gestionar selección adversa** = un HFT market maker. Un maker lento/pasivo vive la mediana y pierde. Coincide con "los bots ganan 24/7 con límites" — y explica por qué no es accesible a un participante lento. Además, este proyecto es **READ-ONLY** (registra, no opera): se puede medir, no ejecutar.

**Conclusión integrada del proyecto:** el edge no está en *predecir* (tomador, refutado: mercado eficiente) sino en *hacer mercado* (maker), y ese edge es estructuralmente de **infraestructura de velocidad/selectividad**, ya cosechado por los bots, fuera del alcance de un análisis read-only. Los "bots que predicen" en realidad **pricean eficientemente y cobran el spread a los que persiguen** — predicción al servicio del market-making, no una señal descargable.

## 7. Reproducibilidad
- Builder ticks: `scripts/build_pm_ticks.py` → `data/raw/pm_ticks.parquet` (sha256 `4a902449c7ad5b…`, 20,47M filas).
- Sondas: `scripts/probe_orderflow.py` (+ sondas inline documentadas en la sesión 2026-06-03).
- Orderbook ejecutable: `data/interim/orderbook_btc15m_snapshots.parquet` (94M, best_ask real).
- Outcomes autoritativos: `data/processed/research_dataset_v1.parquet` (window_id ↔ ts_open/close ↔ outcome, grid 15-min 100% limpio).
