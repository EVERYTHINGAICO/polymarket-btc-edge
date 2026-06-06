"""EXP2-4 — Configuración de fuentes de datos con REVISIONS FIJADAS.

Determinismo: los datasets HF se refrescan ~cada 3h. Sin fijar la revision
(commit SHA), dos corridas bajarían datos distintos y se rompería la
reproducibilidad bit-exact. Aquí se congela el commit exacto a usar.

Cualquier cambio de revision es una decisión registrable (cambia el input_hash).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HFSource:
    repo_id: str
    revision: str          # commit SHA fijo (NO 'main')
    revision_date_utc: str  # informativo


# Polymarket — fuente primaria (precios/ventanas/outcome de respaldo).
# Revision fijada el 2026-06-01 (ver docs/DECISION_FUENTES.md).
POLYMARKET = HFSource(
    repo_id="aliplayer1/polymarket-crypto-updown",
    revision="ba1ad37cbcdd720cced20f1cdc97c2cf347cad6c",
    revision_date_utc="2026-04-26T18:05:40Z",
)

# Filtro canónico del experimento.
CRYPTO = "BTC"
TIMEFRAME = "15-minute"

# Rutas dentro del repo (layout real verificado: markets es archivo único).
def hf_path(source: HFSource, subset_file_or_glob: str) -> str:
    """Construye una ruta hf:// fijada a la revision (con @sha)."""
    return f"hf://datasets/{source.repo_id}@{source.revision}/data/{subset_file_or_glob}"


# Outcome autoridad (NO derivar del precio): CLOB API por condition_id.
POLYMARKET_CLOB_MARKET_URL = "https://clob.polymarket.com/markets/{condition_id}"

# Deribit order flow (para D) — API pública, sin keys, read-only.
# CRITICO: usar history.deribit.com (retencion profunda), NO www.deribit.com
# (www solo retiene ~1 dia; history tiene el historico de opciones expiradas).
# Verificado 2026-06-01: trades de abril-2026 disponibles con direction/iv/index_price.
DERIBIT_TRADES_URL = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"

# Spot BTC de referencia (Gate 4a / vol).
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
