---
doc_id: FEASIBILITY_BACKTEST_DOSPATAS
rol: feasibility report
estado: pre-implementacion (NO codear hasta aprobar)
fase: Exp5 maker / estrategia de dos patas
version: 1.0
creado: 2026-06-03
uso: feasibility para backtestear la estrategia maker de dos patas (NO@X / YES@Y) con los datos del repo
---

# FEASIBILITY — Backtest estrategia de dos patas (NO@X, YES@Y)

> La estrategia: postear bid de NO a X (ej. 0,90) y, si llena, bid de YES a Y (ej. 0,07). Si ambas llenan, set completo a 0,97 → paga 1,00 → +0,03. **No predice el outcome; cosecha el spread.** Riesgo principal = **legging risk** (llena pata 1, no pata 2, y el mercado resuelve en contra → pierde ~X). Es la versión concreta del **vig maker (~1%)** que medimos en [HALLAZGOS_DATOS_FINOS.md](HALLAZGOS_DATOS_FINOS.md) §8.

## A. Juicio resumido

**PARCIALMENTE — con validez MEDIA.** SÍ podemos backtestear la mecánica (reconstruir el libro tick-a-tick, simular fills con un modelo conservador explícito, resolver con el outcome autoritativo, medir PnL/legging/fill-rate). NO podemos modelar con precisión **posición en cola, latencia ni órdenes fallidas/ghost** — y de esos depende justamente el fill de límites. Por eso el resultado será un **rango con cota** (un fill model optimista y uno pesimista), no un número único confiable.

Aclaración de regla dura: **backtestear = análisis (permitido)**; operar en vivo = PROHIBIDO (READ-ONLY, registra-no-opera). Este informe es solo para simulación histórica.

## B. Inventario de datos (archivos reales, verificados 2026-06-03)

| Necesidad | Archivo | Qué tiene | Estado |
|-----------|---------|-----------|--------|
| Metadata de mercado | `data/raw/polymarket_markets_btc15m.parquet` | slug, market_id, condition_id, up/down_token_id, start_ts, end_ts, closed_ts, resolution, fee_rate_bps | ⚠️ PARCHADA (solo ~1.484/3.826 markets ticados matchean; faltan días) |
| YES/NO mapping | orderbook + ticks traen `token_id` + `outcome` (Up/Down) por fila | no depende de la metadata parchada | ✅ |
| Open/close window | regla verificada `ts_open=end_ts−900`, `ts_close=end_ts` (100% en 1.028 ventanas) | + grid 15-min limpio en research_v1 | ✅ |
| **Order book** | `data/raw/orderbook/btc15m_orderbook_part0.parquet` (866M filas) | **L1 event-level**: ts_ms, token_id, outcome, best_bid, best_ask, best_bid_size, best_ask_size, local_recv_ts_ns. Ambos tokens (2.525 markets). Mediana **329.539 updates/market**, gaps sub-seg. Sizes al 100%. | ✅ para L1; ❌ profundidad/cola |
| Order book (procesado) | `data/interim/orderbook_btc15m_snapshots.parquet` (94M) | por ventana: best_bid/ask up&down, sizes, time_to_close_s, spread, capacity | ✅ |
| **Trades/fills** | `data/raw/pm_ticks.parquet` (20,5M) | timestamp_ms, token_id, outcome, **side (=lado del TOMADOR, verificado)**, price, size_usdc, spot. Mar13–Abr26. | ✅ precio/size/lado/ts; ❌ order_id, maker flag, fallidas |
| Resolución (autoridad) | `data/interim/outcomes.parquet` (CLOB winner) + research_v1 | outcome Up/Down autoritativo | ✅ |
| Spot BTC (para riesgo) | spot en cada tick (abril) + Binance 1m | ms en abril | ✅ parcial |

**Universo backtesteable** = orderbook (Mar30–Abr25, 2.525 markets) ∩ outcome resuelto ≈ **~1.000–1.500 ventanas BTC 15-min** (1 mes). Suficiente para un backtest; ajustado para robustez por régimen.

## C. Datos faltantes (y por qué importan)

1. **Posición en cola (queue) — el faltante crítico.** Tenemos L1 (best + size total), no order IDs ni profundidad. No sabemos si NUESTRA orden (atrás en la cola) se hubiera llenado. → el fill de límites solo se puede *aproximar*.
2. **Profundidad L2/L3.** Solo el mejor nivel. No vemos liquidez detrás del best.
3. **Latencia.** `local_recv_ts_ns` solo en 18,8% de las filas → no se puede modelar latencia de forma fiable.
4. **Órdenes fallidas / ghost fills.** No hay registro. No modelable.
5. **Cobertura.** ~1 mes; metadata parchada (mitigable usando token_id/outcome del propio orderbook + outcomes por tiempo).

## D. Calificación de validez

**MEDIA.** Tenemos order book L1 **event-level** + trade prints con lado y tamaño → se pueden simular fills con un **modelo conservador explícito** (no es candle-based). Pero **sin cola/latencia/fallidas**, el fill de límites es una aproximación. → Reportar **banda [pesimista, optimista]**, nunca un PnL puntual como si fuera real.

- Alta validez: requeriría L2 + order IDs + latencia. **No la tenemos.**
- Media validez (la nuestra): L1 event-level + trades, fill conservador.
- Baja: solo velas. (Estamos por encima de esto.)

## E. Plan de implementación (por fases, NO arrancar sin aprobar)

- **Fase 1 — Loader + reconstrucción de mercado.** Por market: unir orderbook (ambos tokens) + ticks + outcome + open/close. Universo backtesteable con QC (descartar markets con orderbook ralo o sin outcome). Hash del dataset reconstruido.
- **Fase 2 — Simulador event-driven.** Cola de eventos (updates de libro + trades) ordenados por ts_ms. El estado en t usa SOLO eventos ≤ t. Sin lookahead por construcción (test que falle si se lee un evento futuro).
- **Fase 3 — Modelo de fill (el corazón).** DOS modos explícitos:
  - *Pesimista (back-of-queue):* nuestra límite a precio P llena solo cuando el volumen tomador acumulado a P (de los ticks) supera el `best_size` que había al postear.
  - *Optimista (top-of-queue):* llena apenas un trade toca P.
  - Reportar **ambos**; la verdad está en el medio. Penalizar por latencia (offset fijo configurable).
- **Fase 4 — Lógica de estrategia.** Postear NO@X; si fill → postear YES@Y; si fill → ciclo completo. Timeout/risk rules (sección H). Sin reposicionar con info futura.
- **Fase 5 — Métricas.** PnL, drawdown, fill-rate por pata, **tasa de ciclos incompletos**, inventario atascado, time-to-hedge, PnL por ventana, % ventanas positivas (window-weighted, no solo agregado — la lección del +2,2%).
- **Fase 6 — Robustez / barrido.** Grilla (X, Y, size, timeout, min-seg-al-cierre). **Selección por vecino ±20% más fuerte en el peor caso**, no por PnL máximo. Split temporal + (si se puede) ETH/SOL virgen.
- **Fase 7 — Benchmarks.** Comparar vs (a) no operar, (b) entrada aleatoria, (c) solo-taker complete-set (que ya sabemos pierde, sum_asks>1). Sanity check.

## F. Supuestos explícitos (obligatorios)

1. Fill de límites = aproximado (modos pesimista/optimista; sin cola real).
2. Resolución = CLOB winner (autoridad), no último precio.
3. fee maker = 0 (verificar `fee_rate_bps`); taker fee 1,8% para hedges de emergencia.
4. Hold del set completo hasta resolución paga exactamente 1,00 (1 YES + 1 NO).
5. Latencia ignorada o offset fijo (datos insuficientes).
6. Sin fallidas/ghost (no modelable) → el fill-rate real será PEOR que el simulado.
7. Universo = markets con orderbook denso + outcome (declarar survivorship: excluimos los de data pobre).

## G. Recomendación

**IMPLEMENTAR el backtest, pero con expectativas calibradas y como MEDIDA, no como validación de un edge operable.** Razones:
- Es el experimento correcto para cuantificar **cuánto del vig (~1-3%) sobrevive al legging risk** — la pregunta abierta real.
- Predicción honesta (de lo ya medido): el +0,03/ciclo se erosiona fuerte con los ciclos de pata-1-sola que resuelven en contra (perder ~X≈0,90 borra ~30 ciclos exitosos). El neto probablemente quede **fino o negativo** en el modo pesimista, y dependa críticamente del fill-rate de la 2ª pata — que es justo lo que peor modelamos.
- Aun si da positivo: **no es operable por nosotros** (READ-ONLY) y requeriría infra de velocidad para la cola real.

**Antes de Fase 1, decisión de Pedro:** ¿implementar el backtest medida-de-vig (validez media, banda de fills), o priorizar conseguir más datos (L2/cola, o más meses) para que valga más? Mi voto: implementarlo en modo banda pesimista/optimista — es barato, usa lo que ya tenemos, y el modo pesimista nos dice rápido si la idea está muerta o no.

---

## H. RESULTADO DEL BACKTEST (Fases 1-6 ejecutadas, 2026-06-03/04)

Universo: `data/interim/backtest_universe.parquet` (1.028 ventanas, Mar29-Abr20, sha256 `c5cc0bf4…`). Stream: `trades_bt.parquet` (2,05M, sha `c16d5625…`) + `ob_bt.parquet` (3,34M a 1s, sha `43010ad0…`). Scripts: `backtest_phase1_universe.py`, `phase2a_extract.py`, `phase2b_sim.py`, `phase6_sweep.py`.

**Veredicto: la estrategia PIERDE robustamente. Toda la grilla X∈{0.85,0.90,0.93} × Y∈{0.05,0.07,0.10,0.15} es NEGATIVA en ambos modos de fill.**

| | base (sin cap) | grilla con risk rule (MAX_CYCLES=5) |
|---|---|---|
| PnL pesimista | −$6.922 | −$1.466 a −$1.501 |
| PnL optimista | −$7.513 | −$1.615 a −$1.747 |
| Legging | 99,5% / 98,1% | **99,7% – 100% en TODA la grilla** |

**Por qué muere (estructural, no parametrico):** la pata 2 (comprar el LONGSHOT pasivo a Y) casi nunca llena — subir Y de 0,05 a 0,15 NO baja el legging. Causa: **el longshot no tiene flujo VENDEDOR** (nadie malvende el lado barato). El flujo es **86% comprador**; para llenar hay que VENDER a la manada, no comprar. La estrategia está del lado equivocado del flujo. Confirma [HALLAZGOS_DATOS_FINOS.md](HALLAZGOS_DATOS_FINOS.md) §8: el vig ~1% solo lo cobra quien vende (posteando asks continuamente, MM de dos lados + velocidad), no un bid pasivo. Perfil de riesgo del legging = mediana/ventana POSITIVA pero media NEGATIVA (centavos delante de la aplanadora).

### H.2 Correccion (bid pasivo) + hedge de emergencia — el hallazgo mas profundo

Tras observacion de Pedro: la v1 CRUZABA el spread (compraba el favorito al ask ~0,55 en toda ventana = apuesta direccional, no arb). Corregido a **bid estrictamente PASIVO** (`backtest_passive.py`, + `size_usdc` tratado como notional→shares, fill cubre cola+SIZE):
- PASIVO/HOLD: **−$2.99K** (opt) / −$2.98K (pes). 633/1028 ventanas operan; 89% legging.
- PASIVO/HEDGE (cerrar a mercado al timeout): **−$3.25K** — PEOR.

**La pistola humeante:** al hedgear, el ask del longshot es **0,456 de media (mediana 0,41), no ~0,10** (solo 29% ≤0,12). Es **seleccion adversa pura**: el bid pasivo del favorito a 0,90 llena justo cuando un vendedor informado lo endosa porque el favorito esta por debilitarse → el longshot sube a 0,41 → hedgear cuesta 0,90+0,42=**1,32 por el set**. Aguantar → favorito pierde. Hedgear → longshot ya caro. **Ambos pierden porque el fill esta adversamente seleccionado.**

**Veredicto FINAL (robusto a todas las correcciones):** la estrategia pierde −$3K/mes en TODAS las variantes (hold/hedge × opt/pes × grilla). No es parametro ni bug: es seleccion adversa estructural. Un bid pasivo en estos mercados llena justo antes de moverse en contra. Cierra la tesis del proyecto: el participante pasivo/lento PROVEE los fills toxicos que el MM rapido evita. Somos el pez, no el tiburon.
