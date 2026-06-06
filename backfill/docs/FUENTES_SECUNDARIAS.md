---
doc_id: FUENTES_SECUNDARIAS
rol: decision-diseño
estado: decidido (verificado)
fase: EXP2-1
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: caso de las 4 fuentes extra — cuáles van activas en V1 y cuáles solo se documentan
---

# FUENTES SECUNDARIAS — método de caso (uso activo vs documentar)

> **Estado:** Fase EXP2-1, verificado el 2026-06-01. Tras cerrar las fuentes primarias ([DECISION_FUENTES.md](DECISION_FUENTES.md)), se exploraron 4 categorías extra a pedido de Pedro. Cada una se clasifica con criterio de caso: **¿se usa ACTIVAMENTE en V1, o solo se documenta como opción?**

## Resumen de la decisión

| Categoría | Fuente verificada | ¿Da lo que falta? | Costo/acceso | **Decisión** |
|-----------|-------------------|-------------------|--------------|--------------|
| Outcome-autoridad (primario) | **CLOB** `clob.polymarket.com/markets/<cid>` → `winner` | ✅ resolución oficial | gratis, read-only | **ACTIVA (primaria)** |
| Outcome-autoridad (backup) | Polymarket **data-api** `/trades` + **Gamma** `?clob_token_ids=` | ✅ cruce/triangulación | gratis | **ACTIVA (validación)** |
| Spot BTC referencia | **Binance** klines 1m (`api.binance.com`) | ✅ mov/vol por ventana, Gate 4a | gratis, sin key | **ACTIVA** |
| Deribit dataset listo | **Tardis.dev** | ⚠️ trades completos = **PAGO**; gratis solo chain día-1/mes | freemium | **DOCUMENTAR** (no V1) |
| Período más largo | btc-updown-15m **no existe antes de ~ago-2025** | ❌ límite del producto, no de la fuente | — | **DOCUMENTAR** (no hay más que recuperar) |

---

## 1. Backup del outcome-autoridad → ACTIVA (validación)

Verificado 2026-06-01 que, además de CLOB (`winner`), hay 2 vías oficiales que dan el mismo dato:
- `https://data-api.polymarket.com/trades?market=<condition_id>` → trades reales con `conditionId` y `asset` (token ganador inferible del precio final on-chain).
- `https://gamma-api.polymarket.com/markets?clob_token_ids=<token_id>` → market con `umaResolutionStatus`/`outcomePrices` (autoridad gamma, la que usó Exp1).

**Uso:** CLOB `winner` = outcome primario. Cruzar una muestra contra data-api/Gamma para blindar; si discrepan, investigar. No es derivación de precio — las tres son resolución oficial del oráculo. Mitiga el riesgo de depender de un solo endpoint.

## 2. Spot BTC de referencia → ACTIVA

Verificado: `https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime=<ms>` devuelve OHLCV 1m histórico real, gratis, sin key. Además el subset `ticks` de Polymarket ya trae `spot_price_usdt` pegado a cada tick.

**Uso:** (a) `deribit_index`/`chainlink_close` vs spot para **Gate 4a** (offset base); (b) vol realizada por ventana (filtros exploratorios / Exp3); (c) **validación** del movimiento BTC de la ventana. NO se usa para decidir outcome (eso es CLOB autoridad). Exp1 usaba Chainlink como referencia; Binance 1m es el equivalente histórico gratis.

## 3. Deribit dataset listo (Tardis.dev) → DOCUMENTAR (no V1)

Tardis.dev tiene opciones Deribit desde 2019-03-30 (`trades`, `options_chain`, `incremental_book_L2`). **Pero:** el histórico completo de `trades` es **de pago**; gratis solo el primer día de cada mes y principalmente `options_chain` (no trades con dirección).

**Decisión:** NO para V1 (rompe la restricción "gratis" y no da order flow gratis). **Documentado como opción** si en el futuro hay presupuesto y se quiere un dataset trades premium normalizado, o como muestra de validación del colector propio (un día gratis vs nuestra descarga de BarendPotijk del mismo día → chequeo de fidelidad). El plan V1 sigue con **BarendPotijk vía API pública** ([DECISION_FUENTES.md](DECISION_FUENTES.md) §5).

## 4. Período más largo → DOCUMENTAR (no hay más que recuperar)

El producto **`btc-updown-15m` de Polymarket no existe antes de ~agosto 2025** (producto nuevo). Nuestro dataset arranca 2025-12-26, ya cerca del inicio real. No hay meses anteriores que "recuperar" de otra fuente — el límite es del producto, no de los datos.

**Implicación para el pre-registro:** el período disponible es acotado (~dic-2025 en adelante). Hay que asumir **riesgo de régimen único** (todo el dato puede caer en un solo régimen de mercado). Se documenta como limitación honesta del experimento, no como algo a "arreglar". Para más muestra: recuperar las ~8.099 ventanas `-1` vía CLOB (eso sí suma n), no extender hacia atrás.

## Fuentes descartadas (registro)

- `manja316/polymarket-historical-data` — full de pago.
- `coinmetrics/terifi` — delta directo pero API key de pago; solo si se quiere ground-truth de delta (validación puntual).
- PolymarketData.co / PolyBackTest — servicios comerciales de datos históricos; no gratis.
