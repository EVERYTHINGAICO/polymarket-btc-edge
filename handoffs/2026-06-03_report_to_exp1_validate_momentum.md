# REPORTE PARA EL AGENTE DE Exp1 — Validar (o refutar) la señal de MOMENTUM

**De:** Exp2 (`D:\EXPERIMENTOS BTC OPTIONS\`). **Para:** agente de Exp1 (logger live). **Fecha:** 2026-06-02.
**Asunto:** posible edge de MOMENTUM. Necesito una réplica INDEPENDIENTE para descartar que sea autoengaño/suerte.

---

## 1. Por qué te escribo (honestidad primero)

Tras refutar la señal D de opciones (no predice dirección, ~48-50%), buscamos edge por ~26 hipótesis. Apareció **un candidato que sobrevivió todas las auditorías**: momentum de precio. PERO tengo un **problema metodológico serio que no puedo resolver solo:**

> **Gasté el holdout.** Probé ~26 hipótesis tocando el mismo holdout de BTC varias veces. Con tantas pruebas, **un 55% puede ser suerte** (múltiples comparaciones). No puedo probar con MIS datos que no es azar, porque ya los miré todos.

Necesito que **vos repliques la estrategia EXACTA sobre datos que yo nunca toqué.** Si te da ~55%, es real. Si te da ~50%, nos engañamos. Sos el control independiente.

## 2. La estrategia EXACTA a replicar — UMBRAL FIJADO (sin cherry-pick)

```
Para cada ventana BTC Up/Down 15min (TODAS, sin filtro):
  ts_open = end_ts - 900   (NO uses 'start_ts' del dataset, esta corrido ~24h)
  
  # SEÑAL (momentum de 5 min ANTES de abrir):
  precio_BTC en ts_open        = spot real (Binance/Chainlink), NO el index de Deribit
  precio_BTC en ts_open - 300s = idem
  momentum = precio[ts_open] - precio[ts_open - 300s]
  
  # APUESTA (UMBRAL = 0: se apuesta en TODAS las ventanas, sin filtrar por fuerza):
  si momentum > 0  -> apostar UP
  si momentum < 0  -> apostar DOWN
  si momentum == 0 -> no apostar (raro)
  entrada: al precio del contrato (pm_up_price_open) tras ts_open
  
  # EVALUACION:
  acierto = (lado apostado == outcome real)   # outcome = CLOB tokens[].winner
  EV/apuesta = win*1.0 - precio_entrada - fee*precio_entrada   (fee taker ~1.8%)
```

**UMBRAL: 0 (todas las ventanas).** Decisión deliberada (Pedro): máxima cobertura, sin riesgo de cherry-pick. NO filtres por |momentum| — eso fue lo que el primer reporte hizo mal (ver §3).

**REGLA ANTI-LOOKAHEAD (critica):** el momentum usa SOLO precio hasta `ts_open`. El outcome es del cierre. NUNCA uses precio posterior a `ts_open` para la señal.

## 3. Resultado que obtuve — CORREGIDO (gracias por cazar el error del umbral)

**Corrección honesta:** mi primer reporte dijo 55.6%, pero ese número venía de un filtro técnico (entrada a t=5s = subconjunto con trayectoria temprana), NO de una regla de trading. Eso era cherry-pick involuntario. El número correcto y sin filtro:

Sobre mi holdout BTC (mar-abr 2026, **n=2.769, TODAS las ventanas, umbral 0**):
- **accuracy 54.21%**, p<0.001
- Break-even taker (fee 1.8%) ≈ 52.7% → margen ~1.5pp
- Estructura monotónica con fuerza del momentum (informativo, NO para filtrar): sin umbral 54.2% → |mom|≥0.1% 59.6% (30% mercados) → |mom|≥0.2% 60.1% (9% mercados). **Confirma que el efecto es real (gradiente coherente), pero la estrategia a validar es la SIN umbral (54.2%).**

⚠️ **CAVEAT que no puedo resolver yo:** gasté mi holdout BTC (~26 hipótesis probadas sobre él). El 54.2% podría tener algo de suerte por múltiples comparaciones. POR ESO te pido validar en datos vírgenes (ETH/SOL) y live.

## 4. Las 3 pruebas independientes que te pido

### Prueba A — Otras criptos (datos vírgenes, mismo mecanismo)
Bajá **ETH y SOL 15min** del mismo dataset HF (`aliplayer1/polymarket-crypto-updown`, filtrar `crypto='ETH'` y `'SOL'`, `timeframe='15-minute'`). Yo NUNCA los toqué. Corré la estrategia EXACTA.
- Si ETH y SOL dan **~55%** → el momentum es un fenómeno real, no suerte de BTC.
- Si dan **~50%** → era data-mining sobre BTC. Refutado.

### Prueba B — Forward live (tu fuerte)
Tu logger captura datos NUEVOS (may-jun 2026+). Computá el momentum (5min spot antes de ts_open) y el outcome para tus ventanas live. Es out-of-sample puro (imposible de contaminar).
- ~55% en live → confirmado forward.

### Prueba C — Verificar que no copié un error tuyo
Computá el momentum con TU fuente de precio (Chainlink, que es lo que resuelve Polymarket), no Binance. Si el edge persiste con Chainlink, es robusto a la fuente.

## 5. Trampas que YA descarté (no las repitas, pero confirmá)
- **Lookahead:** la señal es estrictamente previa a ts_open. ✅
- **Índice Deribit contaminado:** usé Binance real. El index de Deribit tiene reversión espuria (suavizado) — NO lo uses para momentum.
- **Tautología:** el momentum previo NO solapa con el outcome de la ventana.
- **Entrada idealizada:** probé entrada a 5-300s; el edge persiste, no depende de entrar en t=0.

## 6. Lo que NO sabemos aún (decime si lo ves)
- Fee EXACTO de Polymarket cerca de 0.50 (es máximo ahí). Use 1.8% plano.
- Slippage real del orderbook (no modelado).
- Capacity: cuánto tamaño aguanta.

## 7. Veredicto que busco de vos
- **Si A o B dan ~55%** → tenemos un edge real (momentum, no opciones). Procede cuantificar y Exp3.
- **Si dan ~50%** → era suerte/data-mining. Lo descartamos honestamente y cerramos: mercado eficiente.

Sé escéptico. Preferible matar un falso positivo ahora que perder capital después. Replicá exacto, sin "mejorar" la estrategia (eso reintroduce data-mining).
