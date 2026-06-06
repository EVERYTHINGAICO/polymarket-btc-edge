from __future__ import annotations

import io
import json
import socket
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.deribit_feed import BTC_OPTIONS_TRADES_CHANNEL, DERIBIT_PUBLIC_WS_URL, DeltaResolver, LiveDeribitCapture, MinimalWebSocketClient, TradeParseError, build_subscribe_request, classify_moneyness, collect_live_deribit_trades, extract_trades_from_message, format_trade_line, handle_non_trade_message, is_btc_option_trade, normalize_trade, process_message, subscribe_and_print_trades, summarize_message


def sample_trade(**overrides):
    trade = {'trade_id': 'abc123', 'timestamp': 1710000000000, 'instrument_name': 'BTC-27SEP24-65000-C', 'direction': 'buy', 'amount': 2.5, 'price': 0.031, 'greeks': {'delta': 0.11}}
    trade.update(overrides)
    return trade


class FakeWebSocket:
    def __init__(self, messages): self.messages = list(messages); self.sent_payloads = []
    async def send(self, payload: str) -> None: self.sent_payloads.append(payload)
    async def recv(self) -> str:
        if not self.messages: raise AssertionError('No more fake messages available')
        item = self.messages.pop(0)
        if isinstance(item, Exception): raise item
        return item


class FakeConnect:
    def __init__(self, websocket: FakeWebSocket): self.websocket = websocket
    async def __aenter__(self): return self.websocket
    async def __aexit__(self, exc_type, exc, tb): return False


class FakeWebsocketsModule:
    def __init__(self, sequence): self.sequence = list(sequence); self.calls = []
    def connect(self, url: str):
        self.calls.append(url)
        item = self.sequence.pop(0)
        if isinstance(item, Exception): raise item
        return FakeConnect(item)


class FakeStdlibClient:
    scripts: list[list[object]] = []
    created: list['FakeStdlibClient'] = []

    def __init__(self, url: str, timeout: float = 20.0, event_logger=None) -> None:
        self.url = url
        self.timeout = timeout
        self.event_logger = event_logger
        self.script = list(self.__class__.scripts.pop(0))
        self.sent_payloads: list[str] = []
        self.closed = False
        self.__class__.created.append(self)

    def connect(self) -> None:
        return None

    def send_text(self, text: str) -> None:
        self.sent_payloads.append(text)

    def recv_text(self) -> str:
        if not self.script:
            raise socket.timeout('timeout')
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


class DeribitFeedClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeStdlibClient.scripts = []
        FakeStdlibClient.created = []

    def test_detects_btc_option_trade(self):
        self.assertTrue(is_btc_option_trade(sample_trade()))
        self.assertFalse(is_btc_option_trade(sample_trade(instrument_name='ETH-27SEP24-3500-C')))
        self.assertFalse(is_btc_option_trade(sample_trade(instrument_name='BTC-PERPETUAL')))

    def test_classify_moneyness_buckets(self):
        self.assertEqual('DOTM', classify_moneyness(0.03)); self.assertEqual('OTM', classify_moneyness(0.20)); self.assertEqual('ATM', classify_moneyness(0.50)); self.assertEqual('IGNORED', classify_moneyness(0.01)); self.assertEqual('IGNORED', classify_moneyness(0.80))

    def test_normalize_trade_extracts_direction_type_and_delta(self):
        normalized = normalize_trade(sample_trade()); self.assertEqual('buyer', normalized.direction); self.assertEqual('call', normalized.option_type); self.assertAlmostEqual(0.11, normalized.delta_abs); self.assertEqual('DOTM', normalized.moneyness)

    def test_normalize_trade_handles_put_and_negative_delta(self):
        normalized = normalize_trade(sample_trade(instrument_name='BTC-27SEP24-55000-P', direction='sell', greeks={'delta': -0.42})); self.assertEqual('seller', normalized.direction); self.assertEqual('put', normalized.option_type); self.assertAlmostEqual(0.42, normalized.delta_abs); self.assertEqual('ATM', normalized.moneyness)

    def test_normalize_trade_requires_delta(self):
        with self.assertRaises(TradeParseError): normalize_trade(sample_trade(greeks={}))

    def test_delta_resolver_uses_trade_delta_when_present(self):
        resolver = DeltaResolver(fetch_json=lambda url: {'result': {'greeks': {'delta': 0.25}}})
        trade = resolver.resolve(sample_trade())
        self.assertEqual(1, resolver.metrics['delta_from_trade'])
        self.assertEqual(0, resolver.metrics['delta_from_ticker'])
        self.assertAlmostEqual(0.11, trade['greeks']['delta'])

    def test_delta_resolver_enriches_from_ticker(self):
        calls = []
        resolver = DeltaResolver(fetch_json=lambda url: calls.append(url) or {'result': {'greeks': {'delta': 0.25}}})
        trade = resolver.resolve(sample_trade(greeks={}))
        self.assertEqual(1, resolver.metrics['delta_from_ticker'])
        self.assertAlmostEqual(0.25, trade['greeks']['delta'])
        self.assertEqual(1, len(calls))

    def test_delta_resolver_reports_missing_after_enrichment(self):
        resolver = DeltaResolver(fetch_json=lambda url: {'result': {'greeks': {}}})
        trade = resolver.resolve(sample_trade(greeks={}))
        self.assertEqual(1, resolver.metrics['delta_missing_after_enrichment'])
        self.assertEqual({}, trade['greeks'])

    def test_delta_resolver_cache_avoids_repeat_fetch(self):
        calls = []
        resolver = DeltaResolver(fetch_json=lambda url: calls.append(url) or {'result': {'greeks': {'delta': 0.22}}}, ttl_seconds=60)
        resolver.resolve(sample_trade(greeks={}))
        resolver.resolve(sample_trade(greeks={}, trade_id='other'))
        self.assertEqual(1, len(calls))

    def test_format_trade_line_is_printable(self):
        line = format_trade_line(normalize_trade(sample_trade())); self.assertIn('instrument=BTC-27SEP24-65000-C', line); self.assertIn('direction=buyer', line); self.assertIn('moneyness=DOTM', line)

    def test_build_subscribe_request_uses_public_trade_channel(self):
        payload = build_subscribe_request(); self.assertEqual('public/subscribe', payload['method']); self.assertEqual([BTC_OPTIONS_TRADES_CHANNEL], payload['params']['channels'])

    def test_extract_trades_from_message_returns_trade_dicts(self):
        message = {'params': {'data': [sample_trade(), 'ignored', {'trade_id': 'x'}]}}; self.assertEqual(2, len(extract_trades_from_message(message)))

    def test_summarize_message_handles_ack_and_error(self):
        self.assertIn('subscription_ack', summarize_message({'result': {'status': 'ok'}})); self.assertEqual('error code=1001 message=bad request', summarize_message({'error': {'code': 1001, 'message': 'bad request'}}))

    def test_process_message_skips_unusable_trade_without_crashing(self):
        lines = process_message({'params': {'data': [sample_trade(greeks={})]}}); self.assertEqual(1, len(lines)); self.assertIn('skipped_trade', lines[0])

    def test_handle_non_trade_message_processes_test_request(self):
        sent: list[str] = []
        from collections import Counter
        counters = Counter()
        handled = handle_non_trade_message({'method': 'heartbeat', 'params': {'type': 'test_request'}}, counters, sent.append)
        self.assertTrue(handled)
        self.assertEqual(1, counters['heartbeats_received'])
        self.assertEqual(1, counters['test_requests_received'])
        self.assertEqual(1, counters['test_responses_sent'])
        self.assertEqual('public/test', json.loads(sent[0])['method'])

    def test_collect_live_deribit_trades_normalizes_trades_canonically(self):
        FakeStdlibClient.scripts = [[
            json.dumps({'method': 'heartbeat', 'params': {'type': 'test_request'}}),
            json.dumps({'params': {'data': [sample_trade()]}}),
            socket.timeout('timeout'),
        ]]
        capture = collect_live_deribit_trades(duration_seconds=0.01, websocket_factory=FakeStdlibClient)
        self.assertEqual(1, len(capture.trades))
        self.assertEqual('buyer', capture.trades[0].direction)
        self.assertGreaterEqual(capture.counts['heartbeats_received'], 1)
        self.assertGreaterEqual(capture.counts['test_responses_sent'], 1)

    def test_partial_timeout_does_not_abort_whole_capture(self):
        FakeStdlibClient.scripts = [[
            socket.timeout('timeout'),
            json.dumps({'params': {'data': [sample_trade()]}}),
        ]]
        capture = collect_live_deribit_trades(duration_seconds=0.01, websocket_factory=FakeStdlibClient)
        self.assertGreaterEqual(capture.counts['timeouts'], 1)
        self.assertEqual(1, capture.counts['classified_trades'])

    def test_retry_reconnect_bounded_and_metrics_recorded(self):
        FakeStdlibClient.scripts = [
            [ConnectionError('boom')],
            [json.dumps({'params': {'data': [sample_trade()]}})],
        ]
        capture = collect_live_deribit_trades(duration_seconds=0.01, websocket_factory=FakeStdlibClient)
        self.assertEqual(1, capture.counts['reconnects'])
        self.assertEqual(1, capture.counts['errors'])
        self.assertEqual(1, capture.counts['classified_trades'])

    def test_subscribe_and_print_trades_uses_websocket_read_only(self):
        fake_websocket = FakeWebSocket([json.dumps({'jsonrpc': '2.0', 'result': {'status': 'ok'}}), json.dumps({'params': {'data': [sample_trade()]}})])
        fake_module = FakeWebsocketsModule([fake_websocket])
        with patch('src.deribit_feed.get_websockets_module', return_value=fake_module):
            output = io.StringIO()
            with redirect_stdout(output):
                import asyncio; processed = asyncio.run(subscribe_and_print_trades(max_messages=2))
        self.assertEqual([DERIBIT_PUBLIC_WS_URL], fake_module.calls); self.assertEqual(2, processed); self.assertIn('subscription_ack', output.getvalue())

    def test_subscribe_and_print_trades_retries_after_connection_error(self):
        good_socket = FakeWebSocket([json.dumps({'params': {'data': [sample_trade()]}})])
        fake_module = FakeWebsocketsModule([RuntimeError('boom'), good_socket])
        with patch('src.deribit_feed.get_websockets_module', return_value=fake_module):
            output = io.StringIO()
            with redirect_stdout(output):
                import asyncio; processed = asyncio.run(subscribe_and_print_trades(max_messages=1, max_retries=1))
        self.assertEqual(1, processed); self.assertIn('retrying_deribit_feed', output.getvalue())


if __name__ == '__main__':
    unittest.main()
