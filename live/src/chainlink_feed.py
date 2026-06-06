"""Lector read-only del oráculo Chainlink BTC/USD en Polygon mainnet.

Referencia informativa para `chainlink_close`. No es autoridad de outcome.
Sin keys, sin signing, sin wallet — solo `eth_call` JSON-RPC.
"""

from __future__ import annotations

import json
import threading
import time
from queue import Empty, Queue
from urllib.error import URLError
from urllib.request import Request, urlopen

POLYGON_CHAINLINK_BTC_USD = '0xc907E116054Ad103354f2D350FD2514433D57F6f'
POLYGON_RPC_FALLBACKS: tuple[str, ...] = (
    'https://polygon.drpc.org',
    'https://polygon-bor-rpc.publicnode.com',
    'https://1rpc.io/matic',
    'https://polygon.gateway.tenderly.co',
)
LATEST_ROUND_DATA_SELECTOR = '0xfeaf968c'
CHAINLINK_DECIMALS = 8


def _decode_latest_round_answer(result_hex: str) -> int:
    """Decodifica el segundo word (answer, int256) de la respuesta de latestRoundData()."""
    cleaned = result_hex[2:] if result_hex.startswith('0x') else result_hex
    if len(cleaned) < 128:
        raise ValueError('eth_call result too short')
    answer_hex = cleaned[64:128]
    answer = int(answer_hex, 16)
    if answer >= 2 ** 255:
        answer -= 2 ** 256
    return answer


def _eth_call(rpc_url: str, to_address: str, data: str, timeout: int) -> str | None:
    result, _ = _eth_call_with_diag(rpc_url, to_address, data, timeout)
    return result


def _eth_call_with_diag(rpc_url: str, to_address: str, data: str, timeout: float) -> tuple[str | None, str | None]:
    """Como _eth_call pero devuelve también el tipo/detalle de error si falla."""
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'eth_call',
        'params': [{'to': to_address, 'data': data}, 'latest'],
    }
    body = json.dumps(payload).encode('utf-8')
    request = Request(
        rpc_url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
    except URLError as exc:
        return None, f'URLError:{exc.reason!r}'
    except TimeoutError as exc:
        return None, f'TimeoutError:{exc!r}'
    except OSError as exc:
        return None, f'OSError:{exc!r}'
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f'JSONDecodeError:{exc!r}'
    if not isinstance(parsed, dict):
        return None, 'NotDict'
    if 'error' in parsed:
        return None, f'RPCError:{parsed["error"]!r}'
    result = parsed.get('result')
    if not isinstance(result, str) or not result.startswith('0x') or len(result) < 130:
        return None, f'InvalidResult:len={len(result) if isinstance(result, str) else None}'
    return result, None


def fetch_chainlink_btc_usd_close_fast(
    rpc_urls: tuple[str, ...] = POLYGON_RPC_FALLBACKS,
    timeout_seconds: float = 0.4,
    retries: int = 1,
    retry_backoff_seconds: float = 0.1,
) -> tuple[float | None, dict]:
    """Parallel fetch del precio Chainlink BTC/USD en Polygon.

    Lanza un thread por RPC simultáneamente; el primero que responda con éxito gana.
    Reintenta una vez si todos fallan. Total worst-case ≈ 0.9s.

    Devuelve (precio_o_None, diag_dict). diag tiene la lista de intentos por RPC.
    Nunca lanza al caller.
    """
    diag: dict = {'attempts': [], 'winning_rpc': None, 'started_at_utc': time.time()}

    for attempt in range(retries + 1):
        q: Queue = Queue()
        records: list[dict] = []
        records_lock = threading.Lock()
        attempt_done = threading.Event()

        def worker(rpc: str) -> None:
            t0 = time.perf_counter()
            raw, error = _eth_call_with_diag(rpc, POLYGON_CHAINLINK_BTC_USD, LATEST_ROUND_DATA_SELECTOR, timeout_seconds)
            elapsed = round(time.perf_counter() - t0, 4)
            record: dict = {'attempt': attempt, 'rpc': rpc, 'elapsed_seconds': elapsed, 'success': False}
            if error is not None:
                record['error'] = error
            if attempt_done.is_set():
                # Otro RPC ya ganó; solo registramos
                with records_lock:
                    records.append(record)
                return
            if raw is not None:
                try:
                    answer = _decode_latest_round_answer(raw)
                except (ValueError, IndexError) as exc:
                    record['decode_error'] = repr(exc)
                    with records_lock:
                        records.append(record)
                    return
                if answer > 0:
                    price = answer / (10 ** CHAINLINK_DECIMALS)
                    record['success'] = True
                    record['price'] = price
                    with records_lock:
                        records.append(record)
                    q.put((rpc, price))
                    return
            with records_lock:
                records.append(record)

        threads = [threading.Thread(target=worker, args=(rpc,), daemon=True) for rpc in rpc_urls]
        for t in threads:
            t.start()
        try:
            winning_rpc, price = q.get(timeout=timeout_seconds + 0.05)
            attempt_done.set()
            with records_lock:
                diag['attempts'].extend(records)
            diag['winning_rpc'] = winning_rpc
            diag['winning_attempt'] = attempt
            return price, diag
        except Empty:
            attempt_done.set()
        with records_lock:
            diag['attempts'].extend(records)
        if attempt < retries:
            time.sleep(retry_backoff_seconds)

    return None, diag


def fetch_chainlink_btc_usd_close(
    rpc_urls: tuple[str, ...] = POLYGON_RPC_FALLBACKS,
    timeout: int = 10,
) -> float | None:
    """Best-effort. Devuelve precio BTC/USD del oráculo Chainlink en Polygon.

    Nunca lanza al caller. Si todos los RPCs fallan o devuelven payload inválido, retorna None.
    """
    for rpc_url in rpc_urls:
        result = _eth_call(rpc_url, POLYGON_CHAINLINK_BTC_USD, LATEST_ROUND_DATA_SELECTOR, timeout)
        if result is None:
            continue
        try:
            answer = _decode_latest_round_answer(result)
        except (ValueError, IndexError):
            continue
        if answer <= 0:
            continue
        return answer / (10 ** CHAINLINK_DECIMALS)
    return None
