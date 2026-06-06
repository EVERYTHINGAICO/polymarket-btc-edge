---
doc_id: PLAN_DATOS_TICK
rol: protocolo
estado: plan (pre-ejecucion)
fase: re-adquisicion de datos finos (Exp4 / microestructura)
version: 1.0
creado: 2026-06-03
uso: plan maestro para adquirir y ordenar datos tick-by-tick completos, base de la nueva fase
---

# PLAN MAESTRO — Adquisición de datos tick-by-tick

## 1. Por que (el diagnostico que nos trajo aca)

Con datos GRUESOS (velas BTC 1min, precio contrato medio cada ~10s) probamos ~28 hipótesis → mercado eficiente, ningún edge. **Conclusión:** nuestros datos no tienen la granularidad para ver lo que los bots explotan. Los bots ganan con **datos tick (ms) + velocidad**. Para tener chance de ver su edge, necesitamos datos finos.

## 2. Inventario: que tenemos vs que necesitamos

| Dato | Tenemos | Granularidad actual | Necesitamos |
|------|---------|---------------------|-------------|
| Ventanas + outcomes (CLOB) | ✅ | autoridad | OK |
| Precio BTC spot | ✅ Binance 1m | **1 minuto (grueso)** | **tick/segundo** |
| Precio contrato PM | ✅ medio cada 10s | **medio, no ejecutable** | **trades reales (ticks)** |
| Trades Deribit opciones | ✅ | tick | OK (señal D refutada) |
| **Ticks Polymarket** | ❌ | — | **5.615 trades/ventana, ms** |
| **Orderbook PM (bid/ask)** | ❌ | — | spread real (muestra) |
| **Futuros BTC** | ❌ | — | ¿lead sobre spot? |

## 3. Las fuentes a adquirir (en orden de prioridad)

### FUENTE A — Ticks de Polymarket (PRIORIDAD 1)
- **Qué:** subset `ticks` de `aliplayer1/polymarket-crypto-updown@ba1ad37c`, BTC 15-minute.
- **Tamaño:** 21.5M filas, ~3.835 markets. Manejable (~GB, como Deribit).
- **Campos clave:** `timestamp_ms, side, price, size_usdc, spot_price_usdt, spot_price_ts_ms, source, token_id, outcome`.
- **Por que es oro:** trae (1) cada trade real del contrato (precio ejecutable + lado + tamaño), (2) **spot BTC en ms pegado a cada tick** (`spot_price_usdt`) → momentum fino GRATIS, (3) flujo de órdenes (para el mecanismo de los bots).
- **Limpieza:** filtrar timestamps basura (vimos un MIN=1970, hay filas corruptas). Filtrar al período real dic-2025→abr-2026.

### FUENTE B — Orderbook de Polymarket (PRIORIDAD 2, MUESTRA)
- **Qué:** subset `orderbook` (best_bid/ask/sizes), BTC 15m.
- **Tamaño:** 874M filas = INVIABLE bajar todo. **Solo MUESTRA** (~10-15 días, 1 escaneo).
- **Por que:** el spread/ask real (lo que de verdad pagás) + capacity (sizes). Sin esto, ningún EV es ejecutable.
- **Nota:** query por ventana = 43s (re-escanea 874M). Hacer 1 escaneo de pocos días, NO por ventana.

### FUENTE C — Futuros BTC (PRIORIDAD 3, decisión de Pedro)
- **Qué:** Binance perpetuo BTCUSDT.P (klines o aggTrades) vía API de futuros.
- **Por que:** los futuros perpetuos suelen **adelantarse al spot** (más líquidos/rápidos). El lead futuros→spot→Polymarket podría ser donde está el edge de latencia.
- **Spot vs futuros (decisión):** el OUTCOME se resuelve con spot (Chainlink). Pero la SEÑAL podría venir antes del futuro. → tener AMBOS: spot (del tick PM, `spot_price_usdt`) + futuros (a bajar).
- **Granularidad:** aggTrades de Binance futuros = tick real (cada trade). O klines 1s.

## 4. Esquema canonico de datos finos (como ordenarlos)

```
data/raw/
  pm_ticks/            <- FUENTE A (ticks Polymarket por bloque/dia)
  orderbook_sample/    <- FUENTE B (muestra, pocos dias)
  binance_futures/     <- FUENTE C (perpetuo, tick o 1s)
data/interim/
  ticks_clean.parquet       <- ticks limpios (sin basura, periodo correcto)
  spot_fine.parquet         <- spot BTC en ms (extraido de los ticks)
  contract_trades.parquet   <- trades del contrato (precio ejecutable, lado, size)
```

## 5. Que permitiria analizar (las hipotesis que hoy NO podemos)

| Hipótesis nueva | Requiere | Por que ahora si |
|-----------------|----------|------------------|
| Momentum BTC en SEGUNDOS predice mov contrato | spot fino (FUENTE A) | velas 1min eran muy gruesas |
| Lead-lag futuros→spot→Polymarket | FUENTE C + A | no teniamos futuros ni spot fino |
| Flujo de ordenes del contrato (los bots compran Down en momentum?) | FUENTE A (side, size) | no teniamos trades reales |
| EV con precio EJECUTABLE real | FUENTE A (price) + B (ask) | usabamos precio medio |
| Capacity (cuanto tamaño aguanta) | FUENTE B (sizes) | no teniamos |

## 6. Pasos de ejecucion (cuando se apruebe)

1. **Bajar FUENTE A** (ticks PM) por bloques, con hash y limpieza de basura. Verificar cobertura real.
2. **Extraer spot fino** + trades del contrato del tick. Validar granularidad (ms).
3. **Bajar FUENTE B** (muestra orderbook) — 1 escaneo, medir spread real.
4. **Decidir FUENTE C** (futuros) — si Pedro quiere el ángulo lead-lag.
5. **Re-test las hipotesis** de §5, todas anti-lookahead estricto, train→holdout.

## 7. Reglas (heredadas, reforzadas tras 28 hipotesis)
- **Anti-lookahead estricto:** la señal solo usa info ANTES del momento de decisión. Verificar el timestamp de CADA fuente (open vs close, ms reales). Los 2 lookaheads que cometimos fueron por no verificar esto.
- **Precio EJECUTABLE, no medio:** usar ask/bid real (FUENTE B), nunca el precio medio.
- **Mismo conjunto al comparar:** A vs B sobre las mismas ventanas.
- **Holdout sellado:** no re-usarlo (el de BTC ya se gastó; con datos nuevos, sellar uno fresco).
- **Validar candidatos en virgenes** (ETH/SOL o forward) antes de creer.
- Determinismo: hash por artefacto.

## 8. Limpieza pendiente detectada
- Los `ticks` tienen timestamps basura (MIN=1970). Filtrar a `[dic-2025, abr-2026]` antes de usar.
- `ticks` cubren 3.835 markets (no 9.231) — declarar ese universo reducido.
