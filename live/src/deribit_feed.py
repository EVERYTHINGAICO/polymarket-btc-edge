"""Feed read-only de Deribit para Fase 1/5/T1 live."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DOTM_RANGE = (0.02, 0.125)
OTM_RANGE = (0.125, 0.375)
ATM_RANGE = (0.375, 0.625)
DERIBIT_PUBLIC_WS_URL = "wss://www.deribit.com/ws/api/v2"
BTC_OPTIONS_TRADES_CHANNEL = "trades.option.BTC.100ms"
DERIBIT_TICKER_URL_TEMPLATE = "https://www.deribit.com/api/v2/public/ticker?instrument_name={instrument_name}"
DERIBIT_PERPETUAL_TICKER_URL = "https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL"
HEARTBEAT_INTERVAL = 30


@dataclass(frozen=True)
class NormalizedTrade:
    instrument_name: str
    trade_id: str
    timestamp_ms: int
    direction: str
    option_type: str
    delta_abs: float
    moneyness: str
    amount: float
    price: float


@dataclass(frozen=True)
class LiveDeribitCapture:
    trades: list[NormalizedTrade]
    counts: dict[str, int]
    close_codes: list[int]
    close_reasons: list[str]
    heartbeat_enabled: bool
    heartbeat_interval: int


class TradeParseError(ValueError):
    pass


class MinimalWebSocketClient:
    def __init__(self, url: str, timeout: float = 20.0, event_logger: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.url = url
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.event_logger = event_logger

    def _log(self, **payload: Any) -> None:
        if self.event_logger is not None:
            self.event_logger(payload)

    def connect(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != 'wss':
            raise ValueError('Only wss:// URLs are supported')
        host = parsed.hostname or ''
        port = parsed.port or 443
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        raw_sock = socket.create_connection((host, port), timeout=self.timeout)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw_sock, server_hostname=host)
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f'GET {path} HTTP/1.1\r\n'
            f'Host: {host}\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            'Sec-WebSocket-Version: 13\r\n\r\n'
        )
        self.sock.sendall(request.encode())
        response = self._recv_http_headers()
        if '101' not in response.splitlines()[0]:
            raise ConnectionError(f'WebSocket handshake failed: {response.splitlines()[0]}')
        accept = self._header_value(response, 'sec-websocket-accept')
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if accept != expected:
            raise ConnectionError('Invalid Sec-WebSocket-Accept header')
        self._log(event='handshake_ok', ts=time.time())

    def _recv_http_headers(self) -> str:
        assert self.sock is not None
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode('utf-8', errors='replace')

    def _header_value(self, headers: str, name: str) -> str:
        prefix = name.lower() + ':'
        for line in headers.splitlines()[1:]:
            if line.lower().startswith(prefix):
                return line.split(':', 1)[1].strip()
        return ''

    def send_text(self, text: str) -> None:
        payload = text.encode('utf-8')
        frame = bytearray()
        frame.append(0x81)
        length = len(payload)
        if length < 126:
            frame.append(0x80 | length)
        elif length < (1 << 16):
            frame.append(0x80 | 126)
            frame.extend(struct.pack('!H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('!Q', length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        assert self.sock is not None
        self.sock.sendall(frame)
        self._log(event='send_text', ts=time.time(), bytes=len(payload), payload_preview=text[:120])

    def recv_text(self) -> str:
        while True:
            opcode, payload = self._recv_frame()
            self._log(event='recv_frame', ts=time.time(), opcode=opcode, payload_len=len(payload))
            if opcode == 0x1:
                return payload.decode('utf-8', errors='replace')
            if opcode == 0x8:
                raise ConnectionError('WebSocket closed by server')
            if opcode == 0x9:
                self._send_pong(payload)
                self._log(event='pong_sent', ts=time.time(), payload_len=len(payload))
                continue
            if opcode == 0xA:
                continue

    def _recv_exact(self, n: int) -> bytes:
        assert self.sock is not None
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError('Socket closed while reading frame')
            data += chunk
        return data

    def _recv_frame(self) -> tuple[int, bytes]:
        header = self._recv_exact(2)
        b1, b2 = header[0], header[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack('!H', self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b''
        payload = self._recv_exact(length) if length else b''
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def _send_pong(self, payload: bytes) -> None:
        frame = bytearray([0x8A])
        length = len(payload)
        if length < 126:
            frame.append(0x80 | length)
        elif length < (1 << 16):
            frame.append(0x80 | 126)
            frame.extend(struct.pack('!H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('!Q', length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        assert self.sock is not None
        self.sock.sendall(frame)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None


def get_websockets_module():
    import websockets
    return websockets


def fetch_json_url(url: str) -> dict[str, Any]:
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_deribit_index_price() -> float:
    payload = fetch_json_url(DERIBIT_PERPETUAL_TICKER_URL)
    result = payload.get('result') or {}
    for key in ('index_price', 'underlying_price', 'estimated_delivery_price'):
        value = result.get(key)
        if value is not None:
            return float(value)
    raise TradeParseError('Unable to resolve Deribit index price from public ticker payload')


def build_heartbeat_request() -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 2, "method": "public/set_heartbeat", "params": {"interval": HEARTBEAT_INTERVAL}}


def build_test_response() -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 3, "method": "public/test", "params": {}}


class DeltaResolver:
    def __init__(self, fetch_json: Callable[[str], dict[str, Any]] = fetch_json_url, ttl_seconds: float = 30.0) -> None:
        self.fetch_json = fetch_json
        self.ttl_seconds = ttl_seconds
        self.cache: dict[str, tuple[float, float]] = {}
        self.metrics = {
            "delta_from_trade": 0,
            "delta_from_ticker": 0,
            "delta_missing_after_enrichment": 0,
            "ticker_fetch_errors": 0,
        }

    def resolve(self, trade: dict[str, Any]) -> dict[str, Any]:
        if self._trade_has_delta(trade):
            self.metrics["delta_from_trade"] += 1
            return trade
        instrument_name = str(trade.get("instrument_name", ""))
        delta = self._get_cached_or_fetch_delta(instrument_name)
        if delta is None:
            self.metrics["delta_missing_after_enrichment"] += 1
            return trade
        enriched = dict(trade)
        greeks = dict(enriched.get("greeks") or {})
        greeks["delta"] = delta
        enriched["greeks"] = greeks
        self.metrics["delta_from_ticker"] += 1
        return enriched

    def _trade_has_delta(self, trade: dict[str, Any]) -> bool:
        greeks = trade.get("greeks") or {}
        return greeks.get("delta") is not None or trade.get("delta") is not None

    def _get_cached_or_fetch_delta(self, instrument_name: str) -> float | None:
        now = time.time()
        cached = self.cache.get(instrument_name)
        if cached is not None and (now - cached[0]) <= self.ttl_seconds:
            return cached[1]
        if not instrument_name:
            return None
        try:
            payload = self.fetch_json(DERIBIT_TICKER_URL_TEMPLATE.format(instrument_name=quote(instrument_name, safe="")))
        except Exception:
            self.metrics["ticker_fetch_errors"] += 1
            return None
        delta = (((payload.get("result") or {}).get("greeks") or {}).get("delta"))
        if delta is None:
            return None
        value = float(delta)
        self.cache[instrument_name] = (now, value)
        return value


def is_btc_option_trade(trade: dict[str, Any]) -> bool:
    instrument_name = str(trade.get("instrument_name", ""))
    return instrument_name.startswith("BTC-") and instrument_name.endswith(("-C", "-P"))


def option_type_from_instrument(instrument_name: str) -> str:
    if instrument_name.endswith("-C"):
        return "call"
    if instrument_name.endswith("-P"):
        return "put"
    raise TradeParseError(f"Unsupported instrument type: {instrument_name}")


def normalize_direction(direction: str) -> str:
    lowered = direction.strip().lower()
    if lowered == "buy":
        return "buyer"
    if lowered == "sell":
        return "seller"
    raise TradeParseError(f"Unsupported trade direction: {direction}")


def classify_moneyness(delta_abs: float) -> str:
    if DOTM_RANGE[0] < delta_abs <= DOTM_RANGE[1]:
        return "DOTM"
    if OTM_RANGE[0] < delta_abs <= OTM_RANGE[1]:
        return "OTM"
    if ATM_RANGE[0] < delta_abs <= ATM_RANGE[1]:
        return "ATM"
    return "IGNORED"


def extract_delta_abs(trade: dict[str, Any]) -> float:
    greeks = trade.get("greeks") or {}
    delta = greeks.get("delta", trade.get("delta"))
    if delta is None:
        raise TradeParseError("Trade is missing delta information")
    return abs(float(delta))


def normalize_trade(trade: dict[str, Any]) -> NormalizedTrade:
    if not is_btc_option_trade(trade):
        raise TradeParseError("Trade is not a BTC option trade")
    instrument_name = str(trade["instrument_name"])
    delta_abs = extract_delta_abs(trade)
    return NormalizedTrade(
        instrument_name,
        str(trade.get("trade_id", "")),
        int(trade["timestamp"]),
        normalize_direction(str(trade["direction"])),
        option_type_from_instrument(instrument_name),
        delta_abs,
        classify_moneyness(delta_abs),
        float(trade.get("amount", trade.get("contracts", 0.0))),
        float(trade.get("price", 0.0)),
    )


def format_trade_line(trade: NormalizedTrade) -> str:
    return f"trade_id={trade.trade_id or '-'} instrument={trade.instrument_name} direction={trade.direction} type={trade.option_type} moneyness={trade.moneyness} delta_abs={trade.delta_abs:.6f} amount={trade.amount:.6f} price={trade.price:.6f}"


def build_subscribe_request(channels: Iterable[str] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 1, "method": "public/subscribe", "params": {"channels": list(channels or [BTC_OPTIONS_TRADES_CHANNEL])}}


def extract_trades_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    data = (message.get("params") or {}).get("data")
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def summarize_message(message: dict[str, Any]) -> str | None:
    if isinstance(message.get("error"), dict):
        error = message["error"]
        return f"error code={error.get('code', 'unknown')} message={error.get('message', 'unspecified error')}"
    if message.get("method") == "subscription":
        trades = extract_trades_from_message(message)
        if trades:
            return None
        channel = (message.get("params") or {}).get("channel", "unknown")
        return f"subscription channel={channel} without trade payload"
    if message.get("method") == 'heartbeat':
        msg_type = ((message.get("params") or {}).get("type"))
        return f"heartbeat type={msg_type or 'unknown'}"
    if "result" in message:
        return f"subscription_ack result={message['result']}"
    return "ignored_message"


def process_message(message: dict[str, Any]) -> list[str]:
    trades = extract_trades_from_message(message)
    if not trades:
        summary = summarize_message(message)
        return [summary] if summary else []
    lines = []
    for trade in trades:
        try:
            lines.append(format_trade_line(normalize_trade(trade)))
        except TradeParseError as exc:
            lines.append(f"skipped_trade reason={exc}")
    return lines


def handle_non_trade_message(message: dict[str, Any], counts: Counter, send_text: Callable[[str], None]) -> bool:
    if message.get('method') == 'heartbeat':
        counts['heartbeats_received'] += 1
        msg_type = ((message.get('params') or {}).get('type'))
        if msg_type == 'test_request':
            counts['test_requests_received'] += 1
            send_text(json.dumps(build_test_response()))
            counts['test_responses_sent'] += 1
        return True
    return False


def stream_deribit_trades(
    *,
    on_trade: Callable[['NormalizedTrade'], None],
    stop_event,
    url: str = DERIBIT_PUBLIC_WS_URL,
    channels: Iterable[str] | None = None,
    per_read_timeout_seconds: float = 10.0,
    reconnect_backoff_seconds: float = 5.0,
    websocket_factory: Callable[..., MinimalWebSocketClient] = MinimalWebSocketClient,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Stream Deribit trades indefinidamente vía callback.

    Sigue conectado hasta que `stop_event.is_set()` sea True. En caso de error,
    espera `reconnect_backoff_seconds` y reintenta. Cada trade clasificado
    se entrega a `on_trade(trade)` — el callback debe ser rápido y no lanzar.

    Devuelve counts agregados cuando el loop termina (stop solicitado).
    """
    resolver = DeltaResolver()
    counts: Counter = Counter()
    close_codes: list[int] = []
    close_reasons: list[str] = []

    def event_logger(payload: dict[str, Any]) -> None:
        event = payload.get('event')
        if event == 'close_frame' and payload.get('close_code') is not None:
            close_codes.append(int(payload['close_code']))
            close_reasons.append(str(payload.get('close_reason', '')))

    while not stop_event.is_set():
        try:
            client = websocket_factory(url, timeout=per_read_timeout_seconds, event_logger=event_logger)
            client.connect()
            client.send_text(json.dumps(build_heartbeat_request()))
            client.send_text(json.dumps(build_subscribe_request(channels)))
            while not stop_event.is_set():
                try:
                    raw_message = client.recv_text()
                except socket.timeout:
                    counts['timeouts'] += 1
                    continue
                counts['messages'] += 1
                message = json.loads(raw_message)
                if handle_non_trade_message(message, counts, client.send_text):
                    continue
                trade_payloads = extract_trades_from_message(message)
                if not trade_payloads:
                    continue
                for trade_payload in trade_payloads:
                    counts['raw_trades'] += 1
                    enriched = resolver.resolve(trade_payload)
                    try:
                        trade = normalize_trade(enriched)
                        counts['classified_trades'] += 1
                        try:
                            on_trade(trade)
                        except Exception:
                            counts['callback_errors'] += 1
                    except TradeParseError:
                        counts['skipped_trades'] += 1
            try:
                client.close()
            except Exception:
                pass
        except Exception:
            counts['errors'] += 1
            if stop_event.is_set():
                break
            counts['reconnects'] += 1
            sleep_fn(reconnect_backoff_seconds)
            continue

    counts['delta_from_trade'] = resolver.metrics['delta_from_trade']
    counts['delta_from_ticker'] = resolver.metrics['delta_from_ticker']
    counts['delta_missing_after_enrichment'] = resolver.metrics['delta_missing_after_enrichment']
    counts['ticker_fetch_errors'] = resolver.metrics['ticker_fetch_errors']
    return {
        'counts': dict(counts),
        'close_codes': close_codes,
        'close_reasons': close_reasons,
    }


def collect_live_deribit_trades(
    *,
    duration_seconds: float,
    url: str = DERIBIT_PUBLIC_WS_URL,
    channels: Iterable[str] | None = None,
    per_read_timeout_seconds: float = 10.0,
    max_reconnects: int = 2,
    websocket_factory: Callable[..., MinimalWebSocketClient] = MinimalWebSocketClient,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> LiveDeribitCapture:
    resolver = DeltaResolver()
    trades: list[NormalizedTrade] = []
    counts: Counter = Counter()
    close_codes: list[int] = []
    close_reasons: list[str] = []
    started = time.time()
    deadline = started + max(0.0, duration_seconds)
    reconnects = 0
    heartbeat_enabled = True

    def event_logger(payload: dict[str, Any]) -> None:
        event = payload.get('event')
        if event == 'close_frame' and payload.get('close_code') is not None:
            close_codes.append(int(payload['close_code']))
            close_reasons.append(str(payload.get('close_reason', '')))

    while time.time() < deadline:
        try:
            remaining = max(1.0, min(per_read_timeout_seconds, deadline - time.time()))
            client = websocket_factory(url, timeout=max(remaining, per_read_timeout_seconds), event_logger=event_logger)
            client.connect()
            client.send_text(json.dumps(build_heartbeat_request()))
            client.send_text(json.dumps(build_subscribe_request(channels)))
            while time.time() < deadline:
                try:
                    raw_message = client.recv_text()
                except socket.timeout:
                    counts['timeouts'] += 1
                    continue
                counts['messages'] += 1
                message = json.loads(raw_message)
                if handle_non_trade_message(message, counts, client.send_text):
                    continue
                trade_payloads = extract_trades_from_message(message)
                if not trade_payloads:
                    continue
                for trade_payload in trade_payloads:
                    counts['raw_trades'] += 1
                    enriched = resolver.resolve(trade_payload)
                    try:
                        trade = normalize_trade(enriched)
                        trades.append(trade)
                        counts['classified_trades'] += 1
                    except TradeParseError:
                        counts['skipped_trades'] += 1
                if time.time() >= deadline:
                    break
            client.close()
            break
        except Exception:
            counts['errors'] += 1
            if reconnects >= max_reconnects:
                break
            reconnects += 1
            counts['reconnects'] = reconnects
            sleep_fn(0)
            continue

    counts['reconnects'] = reconnects
    counts['delta_from_trade'] = resolver.metrics['delta_from_trade']
    counts['delta_from_ticker'] = resolver.metrics['delta_from_ticker']
    counts['delta_missing_after_enrichment'] = resolver.metrics['delta_missing_after_enrichment']
    counts['ticker_fetch_errors'] = resolver.metrics['ticker_fetch_errors']
    return LiveDeribitCapture(
        trades=trades,
        counts=dict(counts),
        close_codes=close_codes,
        close_reasons=close_reasons,
        heartbeat_enabled=heartbeat_enabled,
        heartbeat_interval=HEARTBEAT_INTERVAL,
    )


def deribit_ws_healthcheck(url: str = DERIBIT_PUBLIC_WS_URL) -> dict[str, Any]:
    client = MinimalWebSocketClient(url)
    try:
        client.connect()
        client.send_text(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'public/test', 'params': {}}))
        message = json.loads(client.recv_text())
        return {'ok': 'result' in message, 'message': message}
    finally:
        client.close()


def iter_deribit_trade_messages(*, url: str = DERIBIT_PUBLIC_WS_URL, channels: Iterable[str] | None = None, duration_seconds: float | None = None) -> list[dict[str, Any]]:
    capture = collect_live_deribit_trades(duration_seconds=duration_seconds or 0, url=url, channels=channels)
    return [{'trade_id': trade.trade_id, 'instrument_name': trade.instrument_name} for trade in capture.trades]


def collect_normalized_trades(*, duration_seconds: float, url: str = DERIBIT_PUBLIC_WS_URL, channels: Iterable[str] | None = None) -> tuple[list[NormalizedTrade], dict[str, int]]:
    capture = collect_live_deribit_trades(duration_seconds=duration_seconds, url=url, channels=channels)
    return capture.trades, capture.counts


async def subscribe_and_print_trades(*, url: str = DERIBIT_PUBLIC_WS_URL, channels: Iterable[str] | None = None, max_messages: int | None = None, max_retries: int = 0) -> int:
    processed = 0
    attempt = 0
    while True:
        try:
            websockets = get_websockets_module()
            async with websockets.connect(url) as websocket:
                await websocket.send(json.dumps(build_subscribe_request(channels)))
                while max_messages is None or processed < max_messages:
                    raw_message = await websocket.recv()
                    message = json.loads(raw_message)
                    lines = process_message(message)
                    if not lines:
                        continue
                    for line in lines:
                        print(line)
                    processed += 1
                return processed
        except Exception as exc:
            if attempt >= max_retries:
                raise
            print(f"retrying_deribit_feed attempt={attempt + 1} reason={exc}")
            attempt += 1
            await asyncio.sleep(0)


def main() -> int:
    asyncio.run(subscribe_and_print_trades())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
