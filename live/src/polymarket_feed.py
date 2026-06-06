"""Cliente y utilidades read-only de Polymarket para Fase 3/T3/Fase 6 pilot."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

POLYMARKET_BASE_URL = 'https://clob.polymarket.com'
GAMMA_BASE_URL = 'https://gamma-api.polymarket.com'
RESOLUTION_SOURCE = 'chainlink_btc_usd_polygon_oracle'
PRICE_TO_BEAT_SOURCE = 'chainlink'
WINDOW_SECONDS = 900
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
}


@dataclass(frozen=True)
class ActiveWindowSnapshot:
    window_id: str
    ts_open: str
    price_to_beat: float | None
    pm_up_price_open: float | None


@dataclass(frozen=True)
class WindowCloseSnapshot:
    ts_close: str
    chainlink_close: float | None
    outcome: str | None
    pm_up_price_close: float | None


@dataclass(frozen=True)
class MarketHealthcheck:
    slug: str
    active: bool
    closed: bool
    accepting_orders: bool
    clob_token_ids_parse_ok: bool
    has_up_token: bool
    midpoint_ok: bool
    book_ok: bool
    price_buy_ok: bool
    price_sell_ok: bool
    issues: list[str]


@dataclass(frozen=True)
class PilotMarket:
    slug: str
    window_id: str
    open_epoch_seconds: int
    ts_open: str
    ts_close: str
    active: bool
    closed: bool
    accepting_orders: bool
    up_token_id: str
    down_token_id: str
    price_to_beat: float | None
    pm_up_price_open: float | None
    end_date: str | None
    event_payload: dict[str, Any]
    market_payload: dict[str, Any]


class PolymarketParseError(ValueError):
    pass


def normalize_iso_timestamp(value: str) -> str:
    text = value.strip()
    if text.endswith('Z'):
        return text
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def current_open_epoch(now_epoch_seconds: int | float) -> int:
    return int(math.floor(float(now_epoch_seconds) / WINDOW_SECONDS) * WINDOW_SECONDS)


def candidate_open_epochs(now_epoch_seconds: int | float) -> list[int]:
    open_epoch_seconds = current_open_epoch(now_epoch_seconds)
    return [open_epoch_seconds - WINDOW_SECONDS, open_epoch_seconds, open_epoch_seconds + WINDOW_SECONDS]


def slug_from_open_epoch(open_epoch_seconds: int | str) -> str:
    return f'btc-updown-15m-{int(open_epoch_seconds)}'


def ts_open_from_slug(slug: str) -> str:
    if not slug.startswith('btc-updown-15m-'):
        raise PolymarketParseError(f'Unsupported slug format: {slug}')
    return ts_open_from_slug_epoch(int(slug.rsplit('-', 1)[1]))


def ts_open_from_slug_epoch(epoch_seconds: int | str) -> str:
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).isoformat().replace('+00:00', 'Z')


def ts_close_from_open_epoch(open_epoch_seconds: int | str) -> str:
    return ts_open_from_slug_epoch(int(open_epoch_seconds) + WINDOW_SECONDS)


def ts_close_from_ts_open(ts_open: str, window_seconds: int = WINDOW_SECONDS) -> str:
    dt = datetime.fromisoformat(normalize_iso_timestamp(ts_open).replace('Z', '+00:00'))
    return (dt + timedelta(seconds=window_seconds)).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def is_window_not_closed(open_epoch_seconds: int | str, now_epoch_seconds: int | float) -> bool:
    close_epoch_seconds = int(open_epoch_seconds) + WINDOW_SECONDS
    return close_epoch_seconds > int(now_epoch_seconds)


def parse_json_encoded_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    raise PolymarketParseError('Expected JSON-encoded list or native list')


def market_accepting_orders(market: dict[str, Any]) -> bool:
    return bool(market.get('acceptingOrders', True))


def is_active_btc_updown_15m_market(event_payload: dict[str, Any], now_epoch_seconds: int | float) -> bool:
    if not bool(event_payload.get('active', False)):
        return False
    if bool(event_payload.get('closed', False)):
        return False
    markets = event_payload.get('markets') or []
    if not markets:
        return False
    market = markets[0]
    if not market_accepting_orders(market):
        return False
    token_ids = parse_json_encoded_list(market.get('clobTokenIds', []))
    if len(token_ids) < 2:
        return False
    slug = str(event_payload.get('slug', ''))
    if not slug.startswith('btc-updown-15m-'):
        return False
    open_epoch_seconds = int(slug.rsplit('-', 1)[1])
    return is_window_not_closed(open_epoch_seconds, now_epoch_seconds)


def parse_active_window(payload: dict[str, Any]) -> ActiveWindowSnapshot:
    try:
        return ActiveWindowSnapshot(
            window_id=str(payload['window_id']),
            ts_open=normalize_iso_timestamp(str(payload['ts_open'])),
            price_to_beat=float(payload['price_to_beat']) if payload.get('price_to_beat') is not None else None,
            pm_up_price_open=float(payload['pm_up_price_open']) if payload.get('pm_up_price_open') is not None else None,
        )
    except KeyError as exc:
        raise PolymarketParseError(f'Missing active window field: {exc.args[0]}') from exc


def parse_close_snapshot(payload: dict[str, Any]) -> WindowCloseSnapshot:
    outcome_raw = payload.get('outcome')
    outcome = None if outcome_raw is None else str(outcome_raw)
    if outcome not in {None, 'Up', 'Down'}:
        raise PolymarketParseError(f'Unsupported outcome: {outcome}')
    try:
        return WindowCloseSnapshot(
            ts_close=normalize_iso_timestamp(str(payload['ts_close'])),
            chainlink_close=float(payload['chainlink_close']) if payload.get('chainlink_close') is not None else None,
            outcome=outcome,
            pm_up_price_close=float(payload['pm_up_price_close']) if payload.get('pm_up_price_close') is not None else None,
        )
    except KeyError as exc:
        raise PolymarketParseError(f'Missing close snapshot field: {exc.args[0]}') from exc


def default_fetch_json(url: str) -> Any:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))


def parse_market_token_ids(market: dict[str, Any]) -> tuple[list[str], list[str]]:
    token_ids = [str(item) for item in parse_json_encoded_list(market.get('clobTokenIds', []))]
    outcomes = [str(item) for item in parse_json_encoded_list(market.get('outcomes', []))]
    return outcomes, token_ids


def up_down_token_map(market: dict[str, Any]) -> dict[str, str]:
    outcomes, token_ids = parse_market_token_ids(market)
    if len(outcomes) != len(token_ids):
        raise PolymarketParseError('Outcomes and token ids length mismatch')
    mapping = {outcome: token_id for outcome, token_id in zip(outcomes, token_ids, strict=True)}
    if 'Up' not in mapping or 'Down' not in mapping:
        raise PolymarketParseError('Missing Up/Down token mapping')
    return mapping


def midpoint_to_float(payload: dict[str, Any]) -> float | None:
    mid = payload.get('mid')
    return None if mid in {None, ''} else float(mid)


def clob_price_to_float(payload: dict[str, Any]) -> float | None:
    price = payload.get('price')
    return None if price in {None, ''} else float(price)


def maybe_price_to_beat(market: dict[str, Any], event_payload: dict[str, Any]) -> float | None:
    for source in (market, event_payload, event_payload.get('eventMetadata') or {}):
        for key in ('price_to_beat', 'priceToBeat'):
            value = source.get(key)
            if value not in {None, ''}:
                return float(value)
    return None


class PolymarketReadOnlyClient:
    def __init__(self, base_url: str = POLYMARKET_BASE_URL, gamma_base_url: str = GAMMA_BASE_URL, fetch_json: Callable[[str], Any] = default_fetch_json) -> None:
        self.base_url = base_url.rstrip('/')
        self.gamma_base_url = gamma_base_url.rstrip('/')
        self.fetch_json = fetch_json

    def fetch_active_window(self, path: str = '/active_window') -> ActiveWindowSnapshot:
        payload = self.fetch_json(f'{self.base_url}{path}')
        return parse_active_window(payload)

    def fetch_close_snapshot(self, window_id: str, path_template: str = '/windows/{window_id}/close') -> WindowCloseSnapshot:
        path = path_template.format(window_id=window_id)
        payload = self.fetch_json(f'{self.base_url}{path}')
        return parse_close_snapshot(payload)

    def fetch_event_by_slug(self, slug: str) -> dict[str, Any]:
        payload = self.fetch_json(f'{self.gamma_base_url}/events/slug/{slug}')
        if not isinstance(payload, dict):
            raise PolymarketParseError('Expected dict event payload from Gamma slug endpoint')
        return payload

    def fetch_markets(self, *, limit: int = 100) -> list[dict[str, Any]]:
        query = urlencode({'active': 'true', 'closed': 'false', 'order': 'end_date', 'ascending': 'true', 'limit': str(limit)})
        payload = self.fetch_json(f'{self.gamma_base_url}/markets?{query}')
        if not isinstance(payload, list):
            raise PolymarketParseError('Expected list payload from Gamma markets endpoint')
        return [item for item in payload if isinstance(item, dict)]

    def fetch_midpoint(self, token_id: str) -> dict[str, Any]:
        return self.fetch_json(f'{self.base_url}/midpoint?token_id={token_id}')

    def fetch_book(self, token_id: str) -> dict[str, Any]:
        return self.fetch_json(f'{self.base_url}/book?token_id={token_id}')

    def fetch_price(self, token_id: str, side: str) -> dict[str, Any]:
        return self.fetch_json(f'{self.base_url}/price?token_id={token_id}&side={side}')

    def discover_candidate_market(self, *, now_epoch_seconds: int | None = None) -> PilotMarket:
        now = int(time.time() if now_epoch_seconds is None else now_epoch_seconds)
        candidates = candidate_open_epochs(now)
        candidate_payloads: list[dict[str, Any]] = []
        for open_epoch in candidates:
            slug = slug_from_open_epoch(open_epoch)
            try:
                payload = self.fetch_event_by_slug(slug)
            except Exception:
                continue
            candidate_payloads.append(payload)
            if bool(payload.get('active', False)) and not bool(payload.get('closed', False)):
                return self._build_pilot_market(payload)
        markets = self.fetch_markets(limit=100)
        for market in markets:
            slug = str(market.get('slug', ''))
            if slug.startswith('btc-updown-15m-') and bool(market.get('active', False)) and not bool(market.get('closed', False)):
                return self._build_pilot_market({'slug': slug, 'active': market.get('active', False), 'closed': market.get('closed', False), 'markets': [market], 'endDate': market.get('endDate')})
        raise PolymarketParseError(f'No active BTC Up/Down 15m market found; checked {len(candidate_payloads)} slug candidates and fallback list')

    def fetch_market_by_open_epoch(self, open_epoch_seconds: int | str) -> PilotMarket:
        return self._build_pilot_market(self.fetch_event_by_slug(slug_from_open_epoch(open_epoch_seconds)))

    def _build_pilot_market(self, event_payload: dict[str, Any]) -> PilotMarket:
        slug = str(event_payload['slug'])
        market = (event_payload.get('markets') or [event_payload])[0]
        token_map = up_down_token_map(market)
        open_epoch_seconds = int(slug.rsplit('-', 1)[1])
        return PilotMarket(
            slug=slug,
            window_id=slug,
            open_epoch_seconds=open_epoch_seconds,
            ts_open=ts_open_from_slug_epoch(open_epoch_seconds),
            ts_close=ts_close_from_open_epoch(open_epoch_seconds),
            active=bool(event_payload.get('active', False)),
            closed=bool(event_payload.get('closed', False)),
            accepting_orders=market_accepting_orders(market),
            up_token_id=token_map['Up'],
            down_token_id=token_map['Down'],
            price_to_beat=maybe_price_to_beat(market, event_payload),
            pm_up_price_open=None,
            end_date=event_payload.get('endDate') or market.get('endDate'),
            event_payload=event_payload,
            market_payload=market,
        )

    def healthcheck_market(self, market: PilotMarket) -> MarketHealthcheck:
        issues: list[str] = []
        clob_token_ids_parse_ok = True
        has_up_token = True
        midpoint_ok = book_ok = price_buy_ok = price_sell_ok = False
        try:
            up_down_token_map(market.market_payload)
        except Exception:
            clob_token_ids_parse_ok = False
            has_up_token = False
            issues.append('clob_token_ids_parse_failed')
        if has_up_token:
            try:
                midpoint_ok = midpoint_to_float(self.fetch_midpoint(market.up_token_id)) is not None
            except Exception:
                issues.append('midpoint_failed')
            try:
                book = self.fetch_book(market.up_token_id)
                book_ok = isinstance(book.get('bids'), list) and isinstance(book.get('asks'), list)
            except Exception:
                issues.append('book_failed')
            try:
                price_buy_ok = clob_price_to_float(self.fetch_price(market.up_token_id, 'buy')) is not None
            except Exception:
                issues.append('price_buy_failed')
            try:
                price_sell_ok = clob_price_to_float(self.fetch_price(market.up_token_id, 'sell')) is not None
            except Exception:
                issues.append('price_sell_failed')
        if not market.active:
            issues.append('market_not_active')
        if market.closed:
            issues.append('market_closed')
        if not market.accepting_orders:
            issues.append('market_not_accepting_orders')
        return MarketHealthcheck(
            slug=market.slug,
            active=market.active,
            closed=market.closed,
            accepting_orders=market.accepting_orders,
            clob_token_ids_parse_ok=clob_token_ids_parse_ok,
            has_up_token=has_up_token,
            midpoint_ok=midpoint_ok,
            book_ok=book_ok,
            price_buy_ok=price_buy_ok,
            price_sell_ok=price_sell_ok,
            issues=issues,
        )


def _parse_outcome_prices(raw) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    if isinstance(raw, list):
        return raw
    return None


def _extract_market_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if 'outcomePrices' in payload or 'outcome_prices' in payload:
        return payload
    markets = payload.get('markets')
    if isinstance(markets, list) and markets and isinstance(markets[0], dict):
        return markets[0]
    return None


def _derive_outcome_from_payload(payload: dict[str, Any]) -> str | None:
    market = _extract_market_dict(payload)
    if market is None:
        return None
    outcomes_raw = market.get('outcomes') or payload.get('outcomes')
    prices_raw = market.get('outcomePrices') or market.get('outcome_prices') or payload.get('outcomePrices')
    outcomes = _parse_outcome_prices(outcomes_raw)
    prices = _parse_outcome_prices(prices_raw)
    if not outcomes or not prices or len(outcomes) != len(prices):
        return None

    def _is_winner(value) -> bool:
        try:
            return float(value) >= 0.999
        except (TypeError, ValueError):
            return False

    def _is_loser(value) -> bool:
        try:
            return float(value) <= 0.001
        except (TypeError, ValueError):
            return False

    winners = [str(o) for o, p in zip(outcomes, prices) if _is_winner(p)]
    losers = [str(o) for o, p in zip(outcomes, prices) if _is_loser(p)]
    if len(winners) != 1 or len(losers) != (len(outcomes) - 1):
        return None
    winner = winners[0]
    if winner not in {'Up', 'Down'}:
        return None
    return winner


def resolve_outcome_with_retries(
    client: 'PolymarketReadOnlyClient',
    slug: str,
    *,
    poll_intervals_seconds: tuple[int, ...] = (15, 30, 60, 90, 120, 120),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[str | None, dict[str, Any] | None]:
    """Polea Polymarket gamma hasta que `outcomePrices` indique un ganador claro.

    Devuelve ('Up'|'Down', payload) cuando resuelve, o (None, last_payload) si se agota el tiempo.
    Errores HTTP/timeout en cada intento se tratan como 'todavía no resuelto'.
    """
    last_payload: dict[str, Any] | None = None
    attempts = list(poll_intervals_seconds) + [0]
    for index, wait_seconds in enumerate(attempts):
        try:
            payload = client.fetch_event_by_slug(slug)
            if isinstance(payload, dict):
                last_payload = payload
                outcome = _derive_outcome_from_payload(payload)
                if outcome is not None:
                    return outcome, payload
        except Exception:
            pass
        if index < len(attempts) - 1 and wait_seconds > 0:
            sleep_fn(wait_seconds)
    return None, last_payload
