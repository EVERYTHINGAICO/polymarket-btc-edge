# Reference Consult Report

## Resultado general
BLOCKED

## Repos consultados
- RiveChen/deribit-historical-data
- BarendPotijk/deribit_historical_trades
- nostoz/deribit_volatility_download_and_visualize
- fshahy/dankbit
- bottama/cryptocurrency-derivatives-pricing-and-delta-neutral-volatility-trading

## Docs oficiales consultadas primero
- Deribit docs: `https://docs.deribit.com/`
- Polymarket docs: `https://docs.polymarket.com/`
- Polymarket CLOB intro: `https://docs.polymarket.com/developers/CLOB/introduction`

## Patrones reutilizados
### Deribit
- URL pública WebSocket v2: `wss://www.deribit.com/ws/api/v2`
- Modelo de suscripción pública por `public/subscribe`
- Enfoque de captura read-only de trades de opciones BTC
- Parsing conservador de trades con `instrument_name`, `direction`, `delta/greeks.delta`
- Retry/backoff simple y marcado explícito de bloqueo

### Polymarket
- Prioridad a docs oficiales CLOB/Gamma
- Confirmación de que desde este runtime los endpoints base probados responden `403`
- No se fijó endpoint inventado de ventana activa; queda bloqueado hasta confirmación humana/documental

## Comparación con `src/deribit_feed.py`
El feed actual ya está alineado con el patrón mínimo esperado para Deribit:
- usa WebSocket público v2
- usa `public/subscribe`
- usa canal `trades.BTC-OPTIONS.raw`
- clasifica call/put, buyer/seller y moneyness
- opera en modo solo lectura

## Bloqueos técnicos actuales
1. `websockets` no existe en el runtime Python.
2. `python3 -m pip` no existe.
3. `python3 -m venv` falla porque `ensurepip` no está disponible.
4. Endpoints base probados de Polymarket/Gamma devuelven `403` en este runtime.

## Solución concreta para dependencia faltante
Instalar en el host/runtime uno de estos caminos:

### Opción A
```bash
apt-get update && apt-get install -y python3-websockets python3-pip python3.11-venv
```

### Opción B
```bash
python3 -m ensurepip --upgrade
python3 -m pip install websockets
```

### Opción C
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Fallback posible
Si el runtime no puede instalar dependencias, correr `scripts/live_t1_deribit_capture.py` en otro host Python 3.11+ con `websockets` disponible y copiar de vuelta los reportes JSON/logs al paquete.
