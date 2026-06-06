---
doc_id: PLAN_ORDERBOOK_SPREAD
rol: protocolo
estado: plan (pre-ejecucion)
fase: validacion de ejecucion (post-momentum)
version: 1.0
creado: 2026-06-03
uso: plan + prompts para medir el spread/ask real del orderbook y recalcular el EV con precios ejecutables
---

# PLAN — Medir spread real (orderbook) y recalcular EV con precios ejecutables

## 1. Planteo del problema (por que esto importa)

Todos los EV que calculamos hasta ahora usaron `up_price` (precio MEDIO del subset `prices`), NO el precio ejecutable. El precio real al que se compra es el **best_ask** (del orderbook), que está por encima del medio por el **spread**.

**La pregunta de fondo:** el edge del momentum (~1 punto sobre break-even) ¿sobrevive al spread real (~2.3pp medido en 1 ventana)? Si el spread > edge, NO hay estrategia rentable.

Esto NO es solo sobre el momentum — es la **corrección de base de TODO el proyecto**: ningún EV es real sin precios ejecutables.

## 2. Inventario de datos (estado 2026-06-03)

| Dato | Estado | Nota |
|------|--------|------|
| Ventanas BTC 15m + outcomes (CLOB) | ✅ disco | autoridad |
| Precio BTC Binance 1m | ✅ disco | señal momentum |
| Trades Deribit (428MB) | ✅ disco | señal D (refutada) |
| Trayectoria pm_up (precio MEDIO) | ✅ disco | NO ejecutable |
| **ORDERBOOK (best_bid/ask/sizes)** | ❌ FALTA | 874M filas BTC 15m en HF |
| Ticks PM | ❌ falta | 21M filas (mecanismo contrarian, opcional) |

## 3. Restricción técnica (medida)

- Query filtrada por ventana individual = **43s/ventana** (DuckDB re-escanea los 874M cada vez) → 9231 ventanas = **~110h. INVIABLE.**
- Bajar orderbook completo = cientos de GB. INVIABLE.
- **Viable:** 1 escaneo de una muestra de días → minutos.

## 4. Lo cientifico (criterio)

Muestra **representativa y suficiente**, no n=1 ni todo:
- Varios días (distintos regímenes), distintas horas, distintos niveles de precio.
- Medir spread **estratificado por nivel de precio** (es más ancho cerca de 0.50, más angosto en extremos).
- Medir también **size** (best_ask_size) = capacity.
- Reportar **distribución** del spread, no un solo número.

## 5. Plan de ejecucion (pasos con prompts)

### PASO 1 — Descargar muestra de orderbook
**Prompt:** "Bajar el subset orderbook de `aliplayer1/polymarket-crypto-updown@<rev>` filtrado a crypto=BTC, timeframe=15-minute, para ~10-15 días representativos (ej. 1 semana de cada mes del período dic-abr). Guardar en `data/raw/orderbook_sample/`. Un solo escaneo por bloque de días. Registrar hash."
- Salida: `data/raw/orderbook_sample/*.parquet`
- Criterio: que cubra ≥10 días, ≥varios cientos de ventanas, con bid/ask/size.

### PASO 2 — Caracterizar el spread (descriptivo)
**Prompt:** "Sobre la muestra de orderbook, calcular el spread (best_ask − best_bid) estratificado por: (a) nivel de precio (mid en bins 0.1), (b) tiempo dentro de la ventana (t=0,60,120... s). Reportar mediana, media, p25, p75 de cada estrato. También best_ask_size (capacity) por estrato."
- Salida: tabla de spread por estrato.
- Pregunta que responde: ¿cuánto es el spread típico a t=60s, cerca de 0.50 (donde apostamos)?

### PASO 3 — Recalcular el EV del momentum con ASK real
**Prompt:** "Para las ventanas de la muestra que tienen orderbook, recalcular la estrategia momentum (señal = sign(BTC[ts_open]−BTC[ts_open−5min]) sobre Binance, anti-lookahead) pero entrando al **best_ask real** a t=60s (no al precio medio). Computar accuracy (no cambia) y EV neto = win·1 − ask − fee·ask. Comparar EV con precio-medio vs EV con ask-real."
- Salida: EV con ask real vs EV con precio medio.
- **Veredicto:** EV_ask > 0 → edge sobrevive; EV_ask ≤ 0 → el spread mata el edge.

### PASO 4 — Robustez y capacity
**Prompt:** "Si EV_ask > 0: (a) verificar capacity — ¿el best_ask_size aguanta el tamaño que querríamos apostar? (b) sensibilidad al fee exacto cerca de 0.5. (c) si la muestra da EV+, pre-registrar y validar en datos vírgenes (ETH/SOL o más días). Si EV_ask ≤ 0: documentar cierre — edge no sobrevive ejecución."

## 6. Hipotesis previa (honestidad)
El spread medido fue ~2.3pp en 1 ventana; el edge del momentum era ~1pp sobre break-even. **Predigo que el EV con ask real será ≤ 0** (el spread se come el edge). Pero hay que medirlo con muestra representativa — el spread puede ser menor en promedio o en ciertos estratos.

## 7. Que NO hacer
- NO bajar los 874M (inviable).
- NO query por ventana (110h).
- NO extrapolar de 1 ventana (n=1).
- NO usar el precio medio como si fuera ejecutable (el error que arrastrábamos).

## 8. Registro de por que llegamos aca
El momentum daba ~54-59% pero: (a) parte era lookahead/semi-tautología (el futuro puro es ~50%), (b) el EV+ que apareció usaba precio medio. Este plan cierra la duda con precios ejecutables reales. Ver [ESTUDIO_MOMENTUM.md](ESTUDIO_MOMENTUM.md) y [ESTADO_PROYECTO.md](ESTADO_PROYECTO.md).
