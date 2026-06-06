---
doc_id: DECISION_FUENTES
rol: decision-diseño
estado: decidido (verificado con evidencia)
fase: EXP2-1
version: 1.1
creado: 2026-06-01
actualizado: 2026-06-01
uso: caso Harvard — qué repos usar para D y outcome, con criterios y riesgos
---

# DECISIÓN DE FUENTES — Método de caso (Harvard)

> **Estado:** Fase A. Decisión razonada sobre qué repositorios usar para recolectar los datos de Exp2.
> **Método:** caso Harvard — (1) hechos verificados, (2) la decisión, (3) criterios, (4) auditoría de las alternativas, (5) decisión recomendada y por qué, (6) riesgos + mitigación.
> **Verificación:** hechos confirmados contra HuggingFace/GitHub/Deribit docs el 2026-06-01 leyendo páginas y código fuente real (no nombres recordados). Lo que falta confirmar leyendo más código se marca **[verificar en Fase B]**.

---

## 1. La decisión a tomar

¿Qué fuentes usar para producir el **Research Dataset V1** (1 fila por ventana BTC 15m: señal **D** de Deribit unida a precio/outcome de Polymarket), respetando: **gratis**, **reproducible**, **sin lookahead**, y suficiente para construir la señal D EXACTA de Exp1 (`signed_pressure = sign(dir)·amount·delta_abs`, bucketeada por moneyness)?

El cuello de botella no es Polymarket (sobran datasets listos). Es **Deribit**: ¿de dónde sale el order flow de opciones BTC con lo necesario para D?

## 2. Criterios de evaluación

| # | Criterio | Por qué importa |
|---|----------|-----------------|
| C1 | **Order flow de trades** (timestamp, price, amount, **direction buyer/seller**) | Sin `direction` no hay `signed_pressure` → no hay D. **No-negociable.** |
| C2 | **Delta / moneyness** (directo o derivable de strike+IV+index+t) | D pondera por `delta_abs` y separa OTM/ATM/DOTM. |
| C3 | **Gratis** | Restricción dura del proyecto. |
| C4 | **Esfuerzo** (parquet listo vs colector vía API vs key paga) | Define cuánto tarda "recolectar". |
| C5 | **Reproducibilidad** (revision fija, licencia, hash) | Determinismo bit-exact. |
| C6 | **Cobertura BTC 15m / periodo** | Meta 5.000–20.000 ventanas, mínimo solape con Exp1. |
| C7 | **Intra-ventana** | Habilita Gate 3 (lead-lag) y Exp3. |

## 3. Hechos verificados — Polymarket (abundancia de parquet LISTOS)

| Repo | ✓ | Tamaño | Lic. | BTC 15m resueltas | C7 intra/orderbook | Veredicto |
|------|:---:|--------|------|:---:|:---:|-----------|
| **`aliplayer1/polymarket-crypto-updown`** | ✅ | 29.1 GB / 9.54B | MIT | **1.132** (de 9.231) | ✅ ticks(150M)+orderbook(9.31B) | **Fuente #1** (ver hallazgo) |
| `BrockMisner/polymarket-btc-updown` | ✅ | 12.7 GB / 3.9B | MIT | **205** (de 8.304) | ✅ ticks(124M)+orderbook(3.78B) | Backup (insuficiente hoy) |
| `SII-WANGZJ/Polymarket_data` | ✅ | ~163 GB / 4B+ | — | genérico | trades crudos | Escalado (no empezar aquí) |
| `manja316/polymarket-historical-data` (GH) | ✅ | full = **PAGO** ($9–29) | — | no confirm. | parcial | Descartado (pago) |

> **🚩 Hallazgo EXP2-1 (verificado con DuckDB):** en AMBOS datasets, ~8.099 ventanas BTC 15m tienen `resolution=-1` (unknown, idénticas en los dos → bloque de mercados viejos sin resolver). `aliplayer1` tiene **1.132 resueltas** (> umbral 1.000 de Exp1); `BrockMisner` solo **205**. Por eso **se invierte la preferencia: arrancar con `aliplayer1`**. Además, el outcome se puede **derivar** de spot vs strike/apertura (`ticks.spot_price_usdt`, `spot_prices`), recuperando ventanas `-1`. Detalle en [FUENTES_DATOS.md](FUENTES_DATOS.md).

## 4. Hechos verificados — Deribit (auditoría de las 8 fuentes que aportó Pedro)

Source de la señal D. Aquí está el trabajo real. Auditadas leyendo README + código fuente:

| # | Repo/fuente | ✓ | Qué da | C1 order flow | C2 delta/greeks | C3 gratis | Tipo |
|---|-------------|:---:|--------|:---:|:---:|:---:|------|
| 1 | **`BarendPotijk/deribit_historical_trades`** | ✅ código + API | trades históricos BTC/ETH/SOL/USDC vía `get_last_trades_by_currency_and_time`; conserva **todos** los campos de la API | ✅ **sí** (direction, amount, price, ts, instrument) | ✅ **CONFIRMADO**: la API trae `iv`+`index_price` por trade (verificado 2026-06-01); NO delta → derivar con BS | ✅ | Colector API |
| 2 | `schepal/deribit_data_collector` | ✅ código | **snapshot** de option chain | ❌ no (sin direction) | ✅ `mark_iv`, `open_interest`, `last_price` (no delta directo) | ✅ | Colector snapshot |
| 3 | `coinmetrics/terifi` | ✅ código | greeks históricos completos (**delta, gamma, vega, theta, rho**), IV, OI, precios por instrumento/expiry | ❌ no (agregado, sin direction) | ✅✅ **delta directo** | ❌ **requiere API key Coin Metrics (pago)** | Feed pago |
| 4 | `bottama/Deribit-Option-Data` | ✅ visto | contratos de opciones vía API pública → SQLite | parcial | precios | ✅ | Colector API |
| 5 | `bottama/cryptocurrency-derivatives-pricing-...` | ✅ visto | research vol trading / delta-neutral | ❌ | metodología BS | ✅ | Research/código |
| 6 | `nostoz/deribit_volatility_download_and_visualize` | ✅ visto | captura **orderbooks** de opciones + vol surface → parquet | ❌ (no histórico antiguo; captura en vivo) | superficie IV | ✅ | Colector en vivo |
| 7 | `alexagedah/implied-volatility-surface` | ✅ visto | construye IV surface / smile / skew / term structure | ❌ | metodología | ✅ | Research/código |
| 8 | `EthanFalcao/Defi_Options_Implied_Volatility` | ✅ visto | IV / vol surface / Black-Scholes sobre datos Deribit | ❌ | **metodología BS para derivar delta** | ✅ | Research/código |

**Hallazgo central — la asimetría:** ninguna fuente gratis da *en un solo lugar* order flow de trades **+** delta. Quien tiene delta directo (terifi) es **pago** y sin order flow. Quien tiene order flow (BarendPotijk) **no trae delta** → hay que **recomputarlo con Black-Scholes** desde `iv`+`strike`+`index_price`+`t_to_expiry` (metodología disponible en fuentes #5/#7/#8).

## 5. Decisión recomendada

### Polymarket
- **Fuente #1 (principal): `BrockMisner/polymarket-btc-updown`.** Mismos campos y licencia MIT que `aliplayer1` pero **<½ del tamaño (12.7 vs 29.1 GB)** por estar enfocado a BTC up/down → descarga más rápida, mismo poder. `aliplayer1` = espejo. `SII-WANGZJ` = escalado futuro.

### Deribit (la combinación que resuelve la asimetría, todo gratis)
- **#1 base: `BarendPotijk/deribit_historical_trades`** → order flow de opciones BTC (cumple C1, lo no-negociable).
- **#2 enriquecimiento de delta:** recomputar `delta` + `moneyness` por trade con **Black-Scholes**, usando la metodología de `EthanFalcao/Defi_Options_Implied_Volatility` (#8) y `alexagedah/implied-volatility-surface` (#7). Inputs: `iv`+`strike`+`index_price`+`t_to_expiry` del propio trade.
- **#3 validación cruzada de IV/OI:** `schepal/deribit_data_collector` (#2) para chequear que la IV/OI reconstruida sea sensata.
- **Opcional con presupuesto: `coinmetrics/terifi`** — si más adelante se quiere **delta de referencia (ground truth)** para validar el delta recomputado, vale pagar la key. No para V1.

### Lo que haría un quant desk (y es lo que hacemos)
No conectar 8 datasets el día 1. Construir `research_dataset_v1.parquet` = **BrockMisner (Polymarket BTC 15m) + BarendPotijk (Deribit trades) + delta recomputado (BS)**. Llegar a ~5.000–20.000 ventanas. Recién ahí buscar alfa. Escalar (`aliplayer1`/`SII-WANGZJ`) y refinar delta (`terifi`) son decisiones posteriores.

## 6. Riesgos y mitigación

| Riesgo | Impacto | Mitigación |
|--------|---------|-----------|
| `get_last_trades...` no trae `iv`/`index_price` por trade | No hay inputs para BS → no delta | **[Fase B]** confirmar leyendo respuesta real de la API; fallback: unir con chain snapshot de `schepal` por instrument+timestamp. |
| Delta recomputado ≠ delta real | Sesgo en ponderación de D | Validar una muestra contra `terifi` (pago, una vez) o contra greeks de Deribit; documentar error. |
| Colector API lento / rate limits | Recolección tarda | Bajar por bloques (`trade_seq`/tiempo), cachear JSONL→parquet, `verify_backfill_determinism`. |
| Datasets HF "se actualizan cada 3h" | Rompe reproducibilidad | **Fijar la `revision` (commit) del dataset HF** y registrar su hash en `backfill_provenance`. |
| Solape temporal con Exp1 | Doble-dipping | Marcar `overlaps_exp1` por fila; excluir del holdout confirmatorio. |
| Polymarket resuelve con Chainlink; D se ve en Deribit index | Desfase base | Es lo que mide Gate 4a; registrar ambos precios. |
| `prices` sin densidad intra-ventana | Gate 3 INSUFICIENTE | Aceptable (igual que Exp1 hoy); no inventar datos. |

## 7. Pendiente antes de descargar (Fase A2/B)

1. **Leer la respuesta real** de `get_last_trades_by_currency_and_time` (kind=option) → confirmar `iv`, `index_price`, `direction`, `amount` por trade.
2. **`DuckDB LIMIT 100`** sobre `BrockMisner` BTC/15m (`markets`, `prices`, `orderbook`) → nombres reales de columnas.
3. Fijar **revision** de los datasets HF y anotarla en provenance.
4. Confirmar metodología BS de `EthanFalcao`/`alexagedah` para el recompute de delta.
