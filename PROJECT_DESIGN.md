# PROJECT_DESIGN.md — Documento de Autoridad

> Este documento es la **fuente de autoridad** del proyecto. Los agentes
> (planner, builder, reviewer, etc.) deben tratar todo lo aquí escrito como
> requisito vinculante. Cuando una propuesta arquitectónica contradiga este
> documento, gana este documento. Si algo no está especificado aquí, el agente
> debe **preguntar al arquitecto humano**, no improvisar.

-----

## 0. AUTORIDAD Y ALCANCE (leer primero)

**Arquitecto humano:** Pedro (decisor final de toda decisión de diseño).
**Rol de los agentes:** asistentes de implementación bajo gates. No deciden arquitectura.

### Regla de oro (NO NEGOCIABLE)

> **Este sistema REGISTRA, no OPERA.**
> No ejecuta órdenes. No mueve dinero. No firma transacciones. No guarda ni
> usa llaves privadas de trading. Solo *observa* mercados en vivo y *guarda*
> datos para análisis posterior. Cualquier tarea que implique ejecución,
> firma de transacciones, o manejo de fondos está **fuera de alcance** y debe
> ser RECHAZADA por el agente con una nota al arquitecto.

### Qué SÍ hace este proyecto (en una frase)

Recolecta, en vivo y sin arriesgar capital, los datos necesarios para responder
una sola pregunta de investigación:

> **¿La señal direccional D, construida del order flow de opciones de Deribit,
> predice el resultado de los mercados de 15 min “BTC Up or Down” de Polymarket
> MEJOR que el precio que el propio mercado ya tiene?**

Si la respuesta es sí → existe edge y se justifica construir un motor de ejecución (otro proyecto, fuera de alcance aquí).
Si la respuesta es no → se aprendió barato, sin perder dinero.

-----

## 1. CONTEXTO DE INVESTIGACIÓN (por qué existe esto)

Basado en: Alexander, C., Deng, J., Feng, J., & Wan, H. (2022).
*Net Buying Pressure and the Information in Bitcoin Option Trades*.
arXiv:2109.02776v2.

Ideas que el código materializa:

- **Señal direccional D** = (presión de compra en calls − presión de compra en puts) / 2,
  ponderada por el delta absoluto de cada opción, agregada sobre una ventana reciente.
- La señal direccional vive sobre todo en opciones **OTM y DOTM** (fuera del dinero).
- La señal se **degrada en ~1 hora**; por eso la ventana de 15 min es viable.
- ADVERTENCIA del propio paper: el desbalance crudo predice *volatilidad* con
  claridad pero *dirección* solo débilmente. Por eso hay que MEDIR, no asumir.

### Riesgo de base que el diseño debe respetar

La señal se observa en el índice de **Deribit**, pero los mercados de Polymarket
resuelven con el **stream BTC/USD de Chainlink**. NO son el mismo precio.
El logger DEBE registrar ambos para poder medir el desfase base entre fuentes.

-----

## 2. STACK TÉCNICO (congelado por el arquitecto)

|Componente        |Decisión                    |Motivo                                                            |
|------------------|----------------------------|------------------------------------------------------------------|
|Lenguaje          |**Python 3.11+**            |Fase de validación; iteración rápida. Rust queda FUERA de alcance.|
|Almacenamiento    |**SQLite** (un archivo)     |Sin servidor, portable, suficiente para esta escala.              |
|Cliente Deribit   |WebSocket público v2        |Feed de trades en vivo, gratuito, sin auth para datos públicos.   |
|Cliente Polymarket|API pública / CLOB read-only|Solo LECTURA de precios y order book.                             |
|Async runtime     |`asyncio` + `websockets`    |Manejar múltiples streams concurrentes.                           |
|Análisis posterior|`pandas`, `matplotlib`      |Notebooks separados, no en el path de recolección.                |
|Gestión de entorno|`venv` + `requirements.txt` |Reproducible.                                                     |

**Prohibido sin aprobación del arquitecto:** cualquier librería de trading/ejecución
(ccxt con llaves, web3 con signer, py-clob-client en modo escritura), cualquier
dependencia que requiera llave privada.

-----

## 3. OBJETIVO DE DATOS — qué fila se guarda y cuándo

El sistema gira en torno a **ventanas de 15 minutos** de Polymarket.

### En la APERTURA de cada ventana (t = inicio)

Registrar un snapshot con:

- `window_id` — identificador único de la ventana de Polymarket
- `ts_open` — timestamp UTC de apertura
- `price_to_beat` — precio BTC de referencia que Polymarket usa para la ventana
- `pm_up_price_open` — precio implícito del contrato “Up” en ese instante (0–1)
- `deribit_index_open` — precio del índice BTC de Deribit en ese instante
- **Señales D y V calculadas sobre 3 ventanas de flujo, separadas:**
  - `D_5m_otm_dotm`, `D_10m_otm_dotm`, `D_15m_otm_dotm`
  - `D_5m_atm`, `D_10m_atm`, `D_15m_atm`  (ATM separado a propósito)
  - `V_5m_otm_dotm`, `V_10m_otm_dotm`, `V_15m_otm_dotm` (volatilidad, para control)
- `n_trades_5m`, `n_trades_10m`, `n_trades_15m` — conteo de trades en cada ventana (para saber si hubo flujo suficiente)

### En el CIERRE de cada ventana (t = inicio + 15 min)

Actualizar la misma fila con:

- `ts_close`
- `deribit_index_close`
- `chainlink_close` — el precio que de verdad decide la resolución
- `outcome` — “Up” / “Down” (según la regla de Polymarket: close ≥ open → Up)
- `pm_up_price_close` — por si quieres ver cómo evolucionó el precio del contrato

> **Principio rector:** registrar CRUDO y SEPARADO. Las decisiones (qué ventana,
> qué moneyness, qué umbral) se toman DESPUÉS en análisis, no se hornean en la
> recolección. Esto evita encerrarse en una decisión prematura.

### Trayectoria intra-ventana (Fase 6.b, aprobado 2026-05-27)

Además del snapshot open/close, durante los 15 min de la ventana se muestrea
el midpoint del contrato Up cada 30 segundos y se guarda en la tabla auxiliar
`observations_intrawindow(window_id, t_seconds, pm_up_price, sampled_at_utc)`.
Esto habilita el análisis lead-lag del Gate 3 (§7.B) y el sanity de Gate 4
con precio realista de entrada. La frecuencia (30s default) puede ajustarse a
15s si el sanity post-piloto muestra resolución insuficiente.

Activación: opt-in vía flag `--with-trajectory` en `src.logger`. El modo sin
trayectoria queda como modo default fallback para auditoría.

-----

## 4. ESTRUCTURA DE CARPETAS (objetivo)

```
project/
├── PROJECT_DESIGN.md        <- este documento (autoridad, NO tocar sin arquitecto)
├── README.md                <- cómo correr
├── requirements.txt
├── .env.example             <- solo endpoints/config, NUNCA secretos reales
├── config.py                <- parámetros: deltas de moneyness, ventanas, etc.
├── src/
│   ├── deribit_feed.py      <- conecta WS Deribit, emite trades clasificados
│   ├── signal.py            <- calcula D y V sobre ventanas rodantes
│   ├── polymarket_feed.py   <- LECTURA: precios, price_to_beat, outcome
│   ├── logger.py            <- orquesta apertura/cierre de ventana, escribe SQLite
│   └── db.py                <- esquema SQLite, funciones de inserción/actualización
├── data/
│   └── observations.db      <- salida (gitignored)
├── notebooks/
│   └── analysis.ipynb       <- análisis posterior, FUERA del path de recolección
└── tests/
    └── ...
```

### Archivos que el agente NO debe tocar sin autorización explícita

- `PROJECT_DESIGN.md` (este archivo)
- `.env` real (si existe)
- cualquier archivo en `data/`

-----

## 5. DEFINICIÓN PRECISA DE LA SEÑAL (para signal.py)

Por cada trade de opción recibido de Deribit, clasificar:

- **lado**: buyer-initiated (B) o seller-initiated (S) — viene en el campo `direction` del trade.
- **tipo**: call (C) o put (P).
- **moneyness**: derivada del delta absoluto |Δ| de la opción:
  - DOTM: 0.02 < |Δ| ≤ 0.125
  - OTM:  0.125 < |Δ| ≤ 0.375
  - ATM:  0.375 < |Δ| ≤ 0.625
  - (ITM/DITM se ignoran en esta fase; el paper muestra que casi no tienen señal direccional)
- **peso**: volumen del trade × |Δ|.

Presión de compra neta por tipo, en una categoría k y ventana w:

```
A_C = Σ(buyer calls · |Δ|) − Σ(seller calls · |Δ|)
A_P = Σ(buyer puts  · |Δ|) − Σ(seller puts  · |Δ|)
```

Señales:

```
D = (A_C − A_P) / 2     # direccional   (la que importa para Up/Down)
V = (A_C + A_P) / 2     # volatilidad   (control, para contraste)
```

`OTM+DOTM` = sumar las contribuciones de ambas categorías antes de calcular A_C/A_P.
`ATM` = calcular por separado.

Las ventanas rodantes (5/10/15 min) se mantienen con un buffer por timestamp:
sumar lo que entra, expirar lo que sale de la ventana. O(1) amortizado por trade.

-----

## 6. PLAN POR FASES (gates — una a la vez)

> El agente avanza UNA fase por vez. No empieza la siguiente sin que el
> arquitecto apruebe el diff de la actual. Cada fase = commits pequeños con
> objetivo, archivos afectados, pruebas y riesgo.

- **Fase 0 — Scaffold:** estructura de carpetas, venv, requirements, db.py con
  esquema SQLite vacío, README mínimo. Sin lógica de red.
- **Fase 1 — Deribit feed (solo lectura/print):** conectar WS, suscribir a trades
  de opciones BTC, clasificar lado/tipo/moneyness, imprimir a consola. NO guardar aún.
- **Fase 2 — signal.py:** ventanas rodantes y cálculo de D/V. Tests con trades sintéticos.
- **Fase 3 — Polymarket feed (solo lectura):** obtener ventana activa de 15 min,
  price_to_beat, precio del contrato Up, y outcome al cierre. NO ejecutar nada.
- **Fase 4 — logger:** orquestar apertura/cierre de ventana, juntar señal + precios,
  escribir fila completa en SQLite.
- **Fase 5 — robustez:** reconexión de WS, manejo de huecos de datos, marcar
  ventanas con flujo insuficiente, log de errores.
- **Fase 5.V — VALIDACIÓN DEL SISTEMA (gate técnico):** ejecutar y aprobar T1–T5
  de la sección 7.A. Hasta pasar esto, la recolección “oficial” NO empieza y el
  análisis estadístico está prohibido. Entregable: reporte de cada prueba T1–T5.
- **Fase 6 — recolección oficial:** correr el sistema validado en vivo hasta
  acumular ~1,000 ventanas completas y confiables (≈ 10–14 días).
- **Fase 7 — VALIDACIÓN ESTADÍSTICA (gates 1–4):** notebook que ejecuta, en orden,
  los cuatro gates de la sección 7.B. SOLO lectura del .db. Cada gate produce su
  número, su test de significancia, y un veredicto AVANZA / FIN.

Cada fase termina con: diff, tests que pasan, y una línea de “riesgo introducido”.

-----

## 7. CÓMO SE PONE A PRUEBA TODO (el corazón del proyecto)

Hay DOS pruebas distintas y AMBAS son obligatorias. La estadística sin la
técnica no vale: **si el sistema recolecta datos rotos, la mejor matemática
del mundo produce una conclusión falsa.** Por eso la prueba técnica va PRIMERO.

-----

### 7.A — VALIDACIÓN DEL SISTEMA (¿el software es confiable?)

> Objetivo: garantizar que los datos guardados son fieles a la realidad ANTES
> de creer en cualquier análisis hecho sobre ellos. Esta validación se ejecuta
> durante las Fases 1–5 y debe pasar antes de iniciar la recolección “oficial”.

**T1 — Integridad de captura de Deribit.**

- Correr el feed 1 hora y comparar el conteo de trades recibidos contra el
  volumen público reportado por Deribit en esa hora (sanity check de orden de magnitud).
- Verificar que CERO trades quedan sin clasificar (todo trade tiene lado, tipo y moneyness).
- Métrica de salida: % de trades descartados y por qué. Si >2% se descarta sin
  razón clara → PARAR, hay un bug de parseo.

**T2 — Correctitud de la señal (test con datos sintéticos).**

- Inyectar trades fabricados a mano con resultado conocido: p.ej. 100 calls
  comprados y 0 puts → D debe salir grande y positivo; 50 calls y 50 puts
  comprados → D ≈ 0, V grande. Si la fórmula no devuelve esto, está mal.
- Verificar que la ventana rodante expira correctamente: un trade de hace 16 min
  NO debe contar en la ventana de 15 min.

**T3 — Fidelidad temporal (la más importante y la más ignorada).**

- Todos los timestamps en UTC, sin excepción. Un solo timestamp en hora local
  corrompe todo el alineamiento ventana-señal.
- Verificar que `ts_open` de la fila coincide (±pocos segundos) con la apertura
  real de la ventana de Polymarket. Un desfase aquí desalinea señal y resultado.

**T4 — Resiliencia (prueba de caídas).**

- Cortar la red a propósito a mitad de recolección. El sistema debe: reconectar,
  y MARCAR la ventana afectada como “datos incompletos” (no inventar ni rellenar).
- Una ventana con flujo insuficiente (`n_trades` por debajo de un mínimo) debe
  quedar marcada como no-confiable, NO descartada silenciosamente.
- Regla dura: **es mejor una fila marcada como “hueco” que una fila falsamente completa.**

**T5 — Persistencia.**

- Matar el proceso y reiniciarlo: las filas ya escritas en SQLite siguen ahí,
  intactas, y la recolección continúa sin duplicar ni corromper.

> **Gate técnico:** hasta que T1–T5 pasen, los datos NO son confiables y el
> análisis estadístico (7.B) está PROHIBIDO — daría conclusiones envenenadas.

-----

### 7.B — VALIDACIÓN ESTADÍSTICA (¿la señal tiene edge?)

> Cuatro gates SECUENCIALES. Si un gate falla, el proyecto se detiene ahí: no
> tiene sentido pasar al siguiente. Cada gate responde una pregunta de vida o muerte.

**Requisito previo — tamaño de muestra.**
Ninguna conclusión es válida con pocas ventanas. Mínimo **~1,000 ventanas
completas y confiables** (≈ 10–14 días a 96 ventanas/día) antes de interpretar
nada. Antes de eso, cualquier número es ruido.

**GATE 1 — ¿D le gana a la moneda?**

- Pregunta: de las ventanas donde `|D|` superó un umbral, ¿`sign(D)` coincidió
  con `outcome` en más del 50%?
- Cómo: accuracy direccional + test binomial (¿es el resultado distinto de 50%
  con significancia, no por azar?).
- Umbral de avance: accuracy claramente > 50% con p-valor bajo. Si es ≈50% → **FIN del proyecto.**

**GATE 2 — ¿D le gana al MERCADO? (el gate que de verdad decide el negocio)**

- Pregunta: cuando `pm_up_price_open` estaba cerca de 0.50 (mercado indeciso) y
  `|D|` era grande, ¿D acertó? Acertar cuando el mercado YA estaba a 0.58 no vale:
  el mercado ya lo sabía.
- Cómo: filtrar solo ventanas con precio del contrato en, p.ej., [0.45, 0.55].
  Sobre ESE subconjunto, medir accuracy de D. Comparar contra el “edge implícito”
  del precio (qué tan lejos de 0.50 estaba ya el mercado).
- Umbral de avance: D acierta significativamente en las ventanas donde el mercado
  estaba indeciso. Si D solo acierta cuando el precio ya lo decía → no hay edge → **FIN.**

**GATE 3 — ¿D se ADELANTA o es contemporánea?**

- Pregunta: ¿la señal aparece ANTES de que el precio del contrato se mueva, o al
  mismo tiempo? Si es simultánea, no alcanzas a apostar barato.
- Cómo: análisis lead-lag. Comparar D al inicio de la ventana contra cómo se movió
  `pm_up_price` DURANTE la ventana. Si el precio ya se movió en la dirección de D
  antes de que pudieras entrar, el edge es inalcanzable.
- Umbral de avance: existe una ventana temporal real donde D ya apunta pero el
  precio aún no se ajustó. Si no la hay → la señal es verdadera pero inútil → **FIN.**

**GATE 4 — ¿El edge sobrevive a la realidad (Chainlink + costos)?**

- Pregunta a) Chainlink: ¿el desfase entre `deribit_index_open` y `chainlink_close`
  es menor que el movimiento típico de la ventana? Si Deribit y Chainlink difieren
  más que el movimiento que predices, puedes acertar sobre Deribit y perder en Polymarket.
- Pregunta b) Costos: simular la apuesta con spread + slippage + fees reales de
  Polymarket. ¿El edge de los gates 1–3 sigue siendo positivo DESPUÉS de costos?
- Umbral de avance: edge neto positivo después de Chainlink y costos. Solo aquí
  se justifica pasar a dinero real (Nivel 2, otro proyecto). Si no sobrevive →
  rentable en papel, inviable en la vida real → **FIN.**

> **Resumen del protocolo:** sistema confiable (7.A) → D le gana a la moneda →
> D le gana al mercado indeciso → D se adelanta → sobrevive a Chainlink y costos.
> Pasar las CINCO etapas es la única condición que justifica arriesgar capital.

-----

## 8. SEGURIDAD / COMPLIANCE (gate permanente)

- Cero secretos en el repo. `.env.example` solo con endpoints públicos.
- Cero llaves privadas, cero firmantes, cero clientes en modo escritura.
- Las APIs usadas son de lectura pública. Si alguna requiere auth, el agente
  PARA y pregunta al arquitecto.
- Respetar rate limits de Deribit y Polymarket; backoff exponencial en reconexión.
- `data/` y `.env` van en `.gitignore`.

-----

## 9. COMANDOS (objetivo, a completar en README)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.logger        # arranca la recolección en vivo
# análisis: abrir notebooks/analysis.ipynb
```

-----

## 10. REPOSITORIOS DE REFERENCIA

Estos repos pueden consultarse para acelerar implementación, pero NO son autoridad
arquitectónica. Si contradicen PROJECT_DESIGN.md, gana PROJECT_DESIGN.md.

- RiveChen/deribit-historical-data: referencia para descarga histórica de trades Deribit.
- BarendPotijk/deribit_historical_trades: referencia alternativa para históricos Deribit.
- nostoz/deribit_volatility_download_and_visualize: referencia para snapshots live de order book y vol analytics.
- fshahy/dankbit: referencia futura para GEX/dealer positioning; fuera de alcance de Fase 1–7.
- bottama/cryptocurrency-derivatives-pricing-and-delta-neutral-volatility-trading: referencia de análisis académico de opciones Deribit.

Prohibido copiar módulos completos sin revisión. Todo código importado debe ser auditado,
aislado y adaptado a modo SOLO LECTURA.