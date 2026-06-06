---
doc_id: SANDBOX_CTF_RESOLUCION
rol: bitacora / mapa del sistema
estado: estudio read-only del protocolo (settlement + resolucion)
fase: estudio de mecanismo (exploits, sandbox)
version: 1.0
creado: 2026-06-05
uso: mapa verificado on-chain del CTF (settlement) y la resolucion Chainlink de los BTC 15-min. Todo READ-ONLY.
---

# SANDBOX — Settlement (CTF) y Resolucion de los BTC 15-min (verificado on-chain)

> Estudio READ-ONLY (eth_call/getLogs de lectura). NO se firma, NO se opera, NO se tocan fondos. Scripts en `sandbox/`. RPC: publicnode/drpc/onfinality (gratis). Objetivo: entender el mecanismo, no atacarlo.

## 1. Direcciones verificadas (Polygon, de Polygonscan)

| Contrato | Address |
|---|---|
| Conditional Tokens (CTF, Gnosis) | `0x4d97dcd97ec945f40cf65f87097ace5ea0476045` |
| CTF Exchange | `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e` |
| NegRisk CTF Exchange | `0xc5d563a36ae78145c45a50134d48a1215220f80a` |
| NegRisk Adapter | `0xd91e80cf2e7be2e162c6513ced06f1dd0da35296` |
| **Resolver BTC 15-min (oraculo)** | **`0x58e1745bEdda7312C4CDdb72618923da1B90EfDE`** |
| USDC (colateral) | `0x2791bca1f2de4661ed88a30c99a7a9449aa84174` |

## 2. Settlement (CTF) — verificado en mercados reales

El CTF (estandar Gnosis) tokeniza cada outcome como ERC1155. Mecanica leida on-chain para 3 mercados reales (`sandbox/read_ctf.js`):

| Mercado | payoutNumerators on-chain | denom | slots | nuestro outcome |
|---|---|---|---|---|
| Dec26 7:30-7:45 | `[1, 0]` | 1 | 2 | Up ✓ |
| Feb21 9:45-10:00 | `[0, 1]` | 1 | 2 | Down ✓ |
| Feb21 9:30-9:45 | `[1, 0]` | 1 | 2 | Up ✓ |

- **Condicion binaria** (2 slots). `payoutDenominator=1`. `payoutNumerators` = vector one-hot. **Indice 0 = Up, indice 1 = Down.** El ganador redime 1/1 = **$1** (`redeemPositions`).
- **Cross-check:** la resolucion on-chain coincide EXACTO con nuestros outcomes del CLOB → valida todo el pipeline contra la verdad de la blockchain.
- Set completo: `splitPosition` (USDC → 1 Up + 1 Down) / `mergePositions` (inverso). Esto es el arb de sets que backtesteamos.

## 3. Parametros del mercado (CLOB API, read-only)

- `minimum_tick_size = 0.01` (precios en centavos), `minimum_order_size = 5`.
- **`maker_base_fee = 0`, `taker_base_fee = 0`** → estos mercados son **fee 0** (corrige el supuesto previo de 1,8%; el 1,8% era de otro contexto/mercados).
- **`rewards = {rates:null, min_size:0, max_spread:0}`** → **los BTC 15-min NO tienen liquidity rewards configurados.** El farming de rewards NO es posible aqui (vive en mercados calmos/largos, como dijo el postmortem).

## 4. Resolucion — Chainlink, deterministica

- Estos mercados resuelven via **Chainlink Data Streams + Chainlink Automation** (NO UMA; UMA es para mercados subjetivos).
- El resolver `0x58e1745b…` (contrato de 4.295 bytes) reporta el payout al CTF. **Confirmado deterministicamente:** `getConditionId(0x58e1745b…, questionId, 2)` == el conditionId real del mercado.
- **Latencia de resolucion:** el evento `ConditionResolution` ocurrio en el bloque 80838556, **~57 s despues del cierre** (end_ts) → Chainlink Automation liquida en ~1 min.

## 5. Implicacion para la tesis de "exploits"

Fuimos a buscar un quirk de sistema explotable en los BTC 15-min. El sistema, leido on-chain, es **limpio y determinista:**
- Settlement = CTF estandar Gnosis (auditado, sin quirk).
- Resolucion = precio Chainlink + automation (sin disputa, sin ambiguedad — a diferencia de UMA).
- Fee 0, sin rewards.

→ **No hay "exploit de resolucion" que encontrar en estos mercados.** Lo unico cerca del cierre es un edge de **latencia** (leer el precio Chainlink antes de que el contrato repricee en esos ~57 s) — que es **carrera de infraestructura (HFT), no un bug de contrato.** Confirma la tesis de todo el proyecto: el edge es velocidad/MM, no un quirk descargable. Y los rewards (lo que sostiene a los MM) **no estan en estos mercados** → por eso son terreno de bots de latencia, no de farmers.

## 6. Reproducibilidad
- `sandbox/read_ctf.js` — lee payoutNumerators/denominator/slots de un conditionId.
- `sandbox/find_oracle.js` + inline — localiza el resolver via getLogs (onfinality) y lo confirma via getConditionId.
- Todo read-only; RPCs gratis (publicnode no soporta getLogs; onfinality si; drpc soporta calls puras).
