---
doc_id: PLAN_BUSQUEDA_EDGE
rol: bitacora
estado: vivo (busqueda exploratoria de edge)
fase: post-EXP2 (replanteo)
version: 1.0
creado: 2026-06-02
uso: plan ordenado para probar TODOS los angulos de edge restantes + registro de los ya refutados
---

# PLAN — Búsqueda exhaustiva de edge (replanteo)

## Contexto
La tesis original (señal D de opciones predice dirección) está **refutada**. El mercado Polymarket BTC-15m es **eficiente para predicción** (~20 hipótesis probadas, todas ~50% sin bias). Replanteo: buscar edge NO-predictivo o en ángulos no tocados.

## Registro de hipótesis YA refutadas (no repetir)
| Hipótesis | Resultado | Por qué cayó |
|-----------|-----------|--------------|
| D direccional (delta/skew/vol/IV, todos horizontes) | ~48-50% | mercado eficiente |
| Mean-reversion precio BTC | 56.7%→50% | artefacto del index Deribit (verificado vs Binance) |
| Modelo ML no-lineal (todas features) | AUC 0.50 real | el 0.55 era el artefacto del index |
| Calibración condicional (hora, extremos) | bien calibrado | 1 anomalía < costos |
| EV/mispricing | pierde el fee | mercado eficiente |
| Latency lag Binance→PM | tautología | futuro real 49.5% |
| Reversión de rachas de outcome | train 59% → holdout 50% | sobreajuste; no pasó holdout |

## Hallazgo POSITIVO confirmado
- **D SÍ predice volatilidad**: corr(|D|, vol realizada)=+0.21, p<0.001. (No direccional → no explotable directo en Up/Down.)

## Lecciones de método (los falsos positivos que desenmascaramos)
1. **Lookahead**: usar trades DURANTE la ventana = 60% falso. Regla: features solo con info < momento de decisión.
2. **Artefacto del index Deribit**: su precio suavizado crea reversión espuria. Regla: backtest con spot REAL (Binance), nunca index.
3. **Tautología**: predecir el outcome con movimiento ya ocurrido. Regla: predecir solo el movimiento FUTURO al punto de decisión.
4. **Múltiples comparaciones**: probar N patrones → ~N×0.05 falsos positivos. Regla: pre-registrar UNO para el holdout.

---

## Los 4 ángulos restantes — plan de prueba

### Ángulo B — Dinámica de la trayectoria pm_up_price (microestructura propia)
**Datos:** ✅ ya tenemos (880k ticks de trayectoria). **No predice outcome — predice el propio precio del contrato.**
- **Test B1:** ¿el precio del contrato hace overshoot y revierte intra-ventana? (autocorrelación de los cambios de pm_up)
- **Test B2:** si pm_up se movió X en los últimos k seg, ¿revierte o sigue? (momentum/reversión del contrato)
- **Sin bias:** usar pm_up hasta T, predecir movimiento de pm_up [T, T+k].
- **Cuidado:** el spread del contrato; un movimiento de pm_up < spread no es explotable.

### Ángulo V — Construir sobre D→volatilidad
**Datos:** ✅ tenemos. **Idea:** D predice vol. ¿Hay mispricing cuando la vol esperada (de D/IV) difiere de lo que el precio Polymarket implica?
- **Test V1:** ventanas de alta vol-esperada (D/IV alto) → ¿el outcome es más "extremo" (lejos de 0.5)? → ¿el precio cerca de 0.5 está mal valorado ahí?
- **Test V2:** ¿la IV implícita de las opciones predice el rango de BTC mejor que lo que Polymarket asume?

### Ángulo S — Structural arbitrage (YES + NO < 1)
**Datos:** ❌ requiere bajar orderbook (best_ask de up y down). **El único edge confirmable sin competir en latencia fina.**
- **Test S1:** ¿ask_up + ask_down < 1 alguna vez? frecuencia, magnitud, duración.
- **Plan:** bajar subset orderbook (revision fija), filtrar BTC 15m, computar suma de asks por timestamp.

### Ángulo T — Flujo de órdenes de Polymarket (ticks)
**Datos:** ❌ requiere bajar `ticks` (trades individuales de PM). **Microestructura: ¿el flujo de órdenes del propio Polymarket anticipa su precio?**
- **Test T1:** desbalance de órdenes compra/venta en PM → ¿predice el siguiente movimiento de pm_up?
- **Cuidado:** esto compite con market-makers; puede requerir latencia.

## Orden de ejecución
1. **B y V primero** (datos en mano, sin descarga). Si alguno da edge robusto → validar holdout.
2. **S** (bajar orderbook) — el más concluyente para arbitraje.
3. **T** (bajar ticks) — el más cercano a HFT, menos apto para análisis.

## Regla de validación (para cualquier candidato)
Train exploratorio → si supera costos (>54%) y es robusto → backtest con costos → holdout sellado UNA vez → aceptar resultado.
