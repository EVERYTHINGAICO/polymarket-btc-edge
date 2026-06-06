---
doc_id: PROTOCOLO_BUSQUEDA_EDGE_ESTADISTICO
rol: protocolo
estado: vivo
fase: post-EXP2
version: 1.0
creado: 2026-06-02
uso: protocolo matemático para buscar edge con EV positivo sin autoengañarse
---

# Protocolo — búsqueda de edge estadístico con EV positivo

## 0. Objetivo

Encontrar una regla operativa en Polymarket BTC 15m que cumpla simultáneamente:

1. **EV neto positivo** tras costos realistas.
2. **Evidencia contra suerte** en muestra no usada para diseñar la regla.
3. **Definición ejecutable**: señal observable antes de la decisión, precio de entrada realista, salida definida, size/capacity estimable.

No buscamos correlaciones. Buscamos una desigualdad de valor esperado:

```text
E[PnL_neto | regla] > 0
```

## 1. Principio anti-autoengaño

Toda búsqueda se divide en tres zonas:

| Zona | Uso | Permitido |
|---|---|---|
| TRAIN exploratorio | descubrir candidatos | probar muchas ideas, pero NO declarar edge |
| VALIDATION interna | elegir UNA regla | comparar pocas variantes predefinidas |
| HOLDOUT sellado | prueba final | correr una vez, aceptar resultado |

Si se mira holdout para ajustar la regla, el test queda contaminado.

## 2. Unidad experimental

La unidad no será "snapshot" si hay miles por mercado, porque eso infla n artificialmente.

Unidad principal:

```text
market_id / ventana de 15m
```

Para microestructura intra-ventana se permiten subunidades temporales, pero el p-value final debe usar:

- agregación por mercado, o
- bootstrap por bloques de mercado/día,
- no conteo ingenuo de snapshots correlacionados.

## 3. Métrica principal

Para toda regla:

```text
PnL_neto_i = payoff_i - coste_entrada_i - fees_i - slippage_i
EV_neto = mean(PnL_neto_i)
```

El criterio de edge no es accuracy. Es:

```text
EV_neto > 0
```

Accuracy solo es auxiliar.

## 4. Tests estadísticos

Para una regla candidata:

1. One-sided t-test o bootstrap sobre `PnL_neto > 0`.
2. Block bootstrap por día/mercado.
3. Intervalo de confianza del EV.
4. Sensibilidad a costos:
   - fees base
   - fees conservadoras
   - slippage bajo/medio/alto
   - latencia 1s/3s/5s

Criterio mínimo para avanzar a holdout:

```text
n_markets >= 100
EV_neto_train > 0.005
p_train < 0.01
IC95(EV_neto_train) no cruza 0
EV sigue positivo con costos conservadores
```

Criterio mínimo para declarar edge:

```text
EV_neto_holdout > 0
p_holdout < 0.05
bootstrap_p_holdout < 0.05
```

## 5. Orden de hipótesis

### H1 — Arbitraje estructural de orderbook

Regla bruta:

```text
ask_up + ask_down < 1
```

EV bruto por par:

```text
gross_edge = 1 - (ask_up + ask_down)
```

EV conservador:

```text
net_edge = 1 - (ask_up + ask_down + fees + slippage)
```

Variables obligatorias:

- frecuencia por mercado
- duración de oportunidad
- capacity = `min(best_ask_size_up, best_ask_size_down)`
- margen bruto
- margen neto
- latencia simulada

Esta es la primera hipótesis porque es determinística si se llenan ambos lados.

### H2 — Market making / spread capture

Regla conceptual:

```text
capturar spread > adverse selection + fees
```

Medir:

- spread
- fill proxy
- movimiento adverso posterior
- inventario acumulado
- PnL mark-to-market

Esta es probablemente la clase de edge de muchos bots exitosos.

### H3 — Order flow de ticks

Regla conceptual:

```text
imbalance de compras/ventas predice movimiento próximo del contrato
```

Features:

- buy volume 10s/30s/60s
- sell volume 10s/30s/60s
- trade count burst
- large trade flag
- price impact

Target:

```text
mid/price move over next 30s/60s/120s
```

Debe superar spread/costos para ser edge.

### H4 — Volatilidad, no dirección

Ya observado:

```text
n_trades y |D| predicen volatilidad realizada
```

Esto solo vale si se convierte en una estructura operable:

- comprar ambos lados barato,
- vender liquidez cuando se espera movimiento,
- ajustar market making por volatilidad.

## 6. Qué NO volver a hacer

- No usar trades durante la ventana para predecir outcome.
- No contar snapshots correlacionados como observaciones independientes.
- No declarar edge por train.
- No optimizar umbrales mirando holdout.
- No usar `accuracy` si la entrada tiene precio desfavorable.
- No ignorar fees/spread/slippage.

## 7. Próximo experimento permitido

Primero H1 en orderbook.

Paso correcto:

1. Tomar una muestra piloto pequeña con orderbook cubierto.
2. Verificar que `ask_up + ask_down < 1` existe.
3. Estimar duración/capacity.
4. Si existe margen bruto suficiente, crear cache local del período cubierto.
5. Correr TRAIN.
6. Si TRAIN pasa criterio, congelar regla.
7. Correr HOLDOUT una vez.

No se corre holdout antes de congelar regla.
