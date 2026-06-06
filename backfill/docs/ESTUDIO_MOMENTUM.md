---
doc_id: ESTUDIO_MOMENTUM
rol: bitacora
estado: estudio en profundidad (candidato a edge, NO confirmado)
fase: post-EXP2 (busqueda de edge)
version: 1.0
creado: 2026-06-02
uso: documentar y entender el fenomeno de momentum, para generar nuevas hipotesis
---

# ESTUDIO — La señal de momentum en Polymarket BTC 15min

> **Estatus:** candidato a edge, NO confirmado. El holdout BTC ya fue usado (~26 hipótesis), así que el número puede tener suerte. Pendiente de réplica independiente (ETH/SOL/live) — ver [REPORTE_PARA_EXP1_validar_momentum.md](../REPORTE_PARA_EXP1_validar_momentum.md).

## 1. La estrategia (especificación exacta, umbral fijado)

```
señal   = signo( precio_BTC[ts_open] − precio_BTC[ts_open − 5min] )   [Binance spot real]
apuesta = Up si señal>0, Down si señal<0   (TODAS las ventanas, umbral 0)
entrada = al precio del contrato (pm_up_price_open) tras ts_open
```
- ts_open = end_ts − 900. Anti-lookahead: la señal usa solo precio < ts_open.

## 2. Resultado (holdout BTC, n=2.769, sin filtro)
- **accuracy 54.21%**, p<0.001. Break-even taker (1.8%) ≈ 52.7% → margen ~1.5pp.
- Estructura monotónica (informativa, NO se usa para filtrar): sin umbral 54.2% → |mom|≥0.1% 59.6% (30% mercados) → |mom|≥0.2% 60.1% (9%).

## 3. EL MECANISMO (lo más importante — por qué "funcionaría")

**Hallazgo clave:** `corr(momentum, pm_open − 0.5) = −0.117` (NEGATIVA, p<0.001).

Esto significa: **cuando BTC viene subiendo, Polymarket cotiza el Up MÁS BARATO** (no más caro). El precio del mercado se mueve EN CONTRA del momentum reciente.

| Régimen | P(Up) realizado | precio_pm que cotiza | gap (mispricing) |
|---------|-----------------|----------------------|------------------|
| Momentum alcista (BTC subió) | 53.4% | 49.75% | **+3.6pp** (Up subvalorado) |
| Momentum bajista (BTC bajó) | 46.1% | 50.5% | **−4.4pp** (Down subvalorado) |

### Interpretación (hipótesis del mecanismo)
**Los apostadores de Polymarket parecen ser CONTRARIAN:** cuando BTC sube, compran Down (esperando reversión/"ya subió mucho"), empujando el precio de Up hacia abajo. Pero el precio real de BTC **continúa** (momentum de corto plazo). Resultado: Up gana más de lo que su precio barato implicaba → ahí está el gap.

**En una frase:** *los humanos apuestan reversión; el precio hace momentum.* El edge vive en esa discrepancia.

## 4. El escepticismo (por qué NO está confirmado)

1. **Cuando momentum y precio DISCREPAN, el momentum acierta solo 51% (train) / 53.6% (holdout).** Buena parte del 54% es el momentum coincidiendo con el precio (no info nueva). El edge incremental es fino.
2. **Holdout gastado:** ~26 hipótesis probadas sobre él → posible suerte por múltiples comparaciones.
3. **Margen fino:** 54.2% vs break-even 52.7% = 1.5pp. Sensible al fee exacto (máximo en 0.5) y al slippage no modelado.
4. **Falta capacity:** ¿cuánto tamaño aguanta antes de mover el precio?

## 5. Lo que el mecanismo ABRE (nuevas hipótesis a explorar)

Si el mecanismo (sesgo contrarian de los humanos) es real, sugiere ideas que NO hemos probado:

| # | Hipótesis nueva | Razonamiento |
|---|-----------------|--------------|
| M1 | **El gap es mayor cuando el momentum es más visible** (movimientos grandes/rápidos atraen más contrarians) | el sesgo humano se activa con movimientos notorios |
| M2 | **El sesgo es mayor en horas de más actividad humana** (vs bots nocturnos) | si son humanos contrarian, debería variar por hora |
| M3 | **Combinar con el order flow de Polymarket (ticks)** — si los humanos compran Down en momentum alcista, se ve en el flujo | confirmaría el mecanismo directamente |
| M4 | **El gap se cierra cerca del cierre** (los bots arbitran al final) → entrar temprano | timing de entrada |
| M5 | **Aplica a ETH/SOL** (mismo sesgo humano, distinto activo) | si es sesgo de comportamiento, es transversal |
| M6 | **Tamaño del gap predice la magnitud** del movimiento, no solo dirección | conecta con D→volatilidad |

## 6. Próximos pasos
1. **Validar el 54.2% en datos vírgenes** (ETH/SOL, live) — descartar suerte. [Reporte enviado a Exp1.]
2. **Si se confirma:** explorar M1-M6 para entender y reforzar el mecanismo.
3. **Verificar el mecanismo directamente:** bajar `ticks` de Polymarket y ver si el flujo humano es contrarian al momentum (probaría la teoría).
4. Cuantificar capacity, fee exacto, slippage antes de cualquier paper trading.

## 7. Por qué este candidato es distinto a los ~26 refutados
Sobrevivió todas las auditorías que mataron a los otros: Binance real (no índice), sin lookahead, entrada realista, persiste en horizontes, holdout con n grande, rentable como taker, **y tiene un mecanismo económico falsable** (sesgo contrarian). Los falsos positivos anteriores no tenían mecanismo — eran artefactos. Este tiene una historia comprobable. Eso no lo hace cierto, pero lo hace **digno de estudio serio**.
