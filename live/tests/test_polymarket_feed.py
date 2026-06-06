from __future__ import annotations

import unittest

from src.polymarket_feed import (
    POLYMARKET_BASE_URL,
    PRICE_TO_BEAT_SOURCE,
    RESOLUTION_SOURCE,
    PolymarketParseError,
    MarketHealthcheck,
    PilotMarket,
    PolymarketReadOnlyClient,
    candidate_open_epochs,
    current_open_epoch,
    is_active_btc_updown_15m_market,
    is_window_not_closed,
    parse_active_window,
    parse_close_snapshot,
    parse_json_encoded_list,
    slug_from_open_epoch,
    ts_close_from_open_epoch,
    ts_close_from_ts_open,
    ts_open_from_slug,
    ts_open_from_slug_epoch,
)


class PolymarketFeedTests(unittest.TestCase):
    def test_parse_active_window_normalizes_types(self) -> None:
        snapshot = parse_active_window(
            {
                'window_id': 'win-001',
                'ts_open': '2026-05-25T06:15:00',
                'price_to_beat': '65000.5',
                'pm_up_price_open': '0.52',
            }
        )
        self.assertEqual('win-001', snapshot.window_id)
        self.assertEqual('2026-05-25T06:15:00Z', snapshot.ts_open)
        self.assertAlmostEqual(65000.5, snapshot.price_to_beat)
        self.assertAlmostEqual(0.52, snapshot.pm_up_price_open)

    def test_parse_close_snapshot_validates_outcome(self) -> None:
        snapshot = parse_close_snapshot(
            {
                'ts_close': '2026-05-25T06:30:00Z',
                'chainlink_close': 65010,
                'outcome': 'Up',
                'pm_up_price_close': 0.84,
            }
        )
        self.assertEqual('Up', snapshot.outcome)
        self.assertEqual('2026-05-25T06:30:00Z', snapshot.ts_close)

    def test_parse_close_snapshot_rejects_invalid_outcome(self) -> None:
        with self.assertRaises(PolymarketParseError):
            parse_close_snapshot(
                {
                    'ts_close': '2026-05-25T06:30:00Z',
                    'chainlink_close': 65010,
                    'outcome': 'Flat',
                    'pm_up_price_close': 0.84,
                }
            )

    def test_slug_epoch_maps_to_ts_open_utc(self) -> None:
        # OPEN epoch, not close — close is at open+900.
        self.assertEqual('2026-05-25T20:30:00Z', ts_open_from_slug_epoch(1779741000))
        self.assertEqual('2026-05-25T20:30:00Z', ts_open_from_slug('btc-updown-15m-1779741000'))

    def test_ts_close_is_15_minutes_after_ts_open(self) -> None:
        self.assertEqual('2026-05-25T20:45:00Z', ts_close_from_ts_open('2026-05-25T20:30:00Z'))
        self.assertEqual('2026-05-25T20:45:00Z', ts_close_from_open_epoch(1779741000))

    def test_dynamic_window_epoch_calculation_and_candidate_probe(self) -> None:
        now_epoch_seconds = 1779741299
        self.assertEqual(1779741000, current_open_epoch(now_epoch_seconds))
        self.assertEqual([1779740100, 1779741000, 1779741900], candidate_open_epochs(now_epoch_seconds))
        self.assertEqual('btc-updown-15m-1779741000', slug_from_open_epoch(1779741000))

    def test_parse_json_encoded_list_for_gamma_quirk(self) -> None:
        encoded = '["yes_token_id","no_token_id"]'
        self.assertEqual(['yes_token_id', 'no_token_id'], parse_json_encoded_list(encoded))

    def test_active_market_filter_accepts_live_candidate(self) -> None:
        payload = {
            'active': True,
            'closed': False,
            'slug': 'btc-updown-15m-1779741000',
            'markets': [
                {
                    'clobTokenIds': '["yes_token_id","no_token_id"]',
                    'acceptingOrders': True,
                }
            ],
        }
        self.assertTrue(is_active_btc_updown_15m_market(payload, now_epoch_seconds=1779741200))

    def test_active_market_filter_rejects_closed_or_tokenless_candidate(self) -> None:
        closed_payload = {
            'active': True,
            'closed': True,
            'slug': 'btc-updown-15m-1779741000',
            'markets': [{'clobTokenIds': '["yes","no"]'}],
        }
        empty_tokens_payload = {
            'active': True,
            'closed': False,
            'slug': 'btc-updown-15m-1779741000',
            'markets': [{'clobTokenIds': '[]', 'acceptingOrders': True}],
        }
        self.assertFalse(is_active_btc_updown_15m_market(closed_payload, now_epoch_seconds=1779741200))
        self.assertFalse(is_active_btc_updown_15m_market(empty_tokens_payload, now_epoch_seconds=1779741200))

    def test_is_window_not_closed_uses_epoch_seconds_only(self) -> None:
        self.assertTrue(is_window_not_closed(1779741000, 1779741200))
        self.assertFalse(is_window_not_closed(1779741000, 1779741900))

    def test_resolution_and_price_to_beat_sources_are_chainlink_strings(self) -> None:
        self.assertEqual('chainlink_btc_usd_polygon_oracle', RESOLUTION_SOURCE)
        self.assertEqual('chainlink', PRICE_TO_BEAT_SOURCE)

    def test_read_only_client_fetches_active_window(self) -> None:
        seen = []
        def fake_fetch(url: str):
            seen.append(url)
            return {
                'window_id': 'win-002',
                'ts_open': '2026-05-25T06:45:00Z',
                'price_to_beat': 65100,
                'pm_up_price_open': 0.49,
            }
        client = PolymarketReadOnlyClient(fetch_json=fake_fetch)
        snapshot = client.fetch_active_window()
        self.assertEqual(f'{POLYMARKET_BASE_URL}/active_window', seen[0])
        self.assertEqual('win-002', snapshot.window_id)

    def test_read_only_client_fetches_close_snapshot(self) -> None:
        seen = []
        def fake_fetch(url: str):
            seen.append(url)
            return {
                'ts_close': '2026-05-25T07:00:00Z',
                'chainlink_close': 65120,
                'outcome': 'Down',
                'pm_up_price_close': 0.12,
            }
        client = PolymarketReadOnlyClient(fetch_json=fake_fetch)
        snapshot = client.fetch_close_snapshot('win-002')
        self.assertEqual(f'{POLYMARKET_BASE_URL}/windows/win-002/close', seen[0])
        self.assertEqual('Down', snapshot.outcome)

    def test_healthcheck_market_parses_up_token_and_clob_endpoints(self) -> None:
        market = PilotMarket(
            slug='btc-updown-15m-1779826500',
            window_id='btc-updown-15m-1779826500',
            open_epoch_seconds=1779826500,
            ts_open='2026-05-26T20:15:00Z',
            ts_close='2026-05-26T20:30:00Z',
            active=True,
            closed=False,
            accepting_orders=True,
            up_token_id='up-token',
            down_token_id='down-token',
            price_to_beat=None,
            pm_up_price_open=0.42,
            end_date='2026-05-26T20:30:00Z',
            event_payload={'slug': 'btc-updown-15m-1779826500'},
            market_payload={
                'outcomes': '["Up", "Down"]',
                'clobTokenIds': '["up-token", "down-token"]',
                'acceptingOrders': True,
            },
        )
        client = PolymarketReadOnlyClient(fetch_json=lambda url: {'mid': '0.42'} if 'midpoint' in url else ({'price': '0.41'} if 'price' in url else {'bids': [], 'asks': []}))
        health = client.healthcheck_market(market)
        self.assertTrue(health.clob_token_ids_parse_ok)
        self.assertTrue(health.has_up_token)
        self.assertTrue(health.midpoint_ok)
        self.assertTrue(health.book_ok)
        self.assertTrue(health.price_buy_ok)
        self.assertTrue(health.price_sell_ok)
        self.assertEqual([], health.issues)


if __name__ == '__main__':
    unittest.main()
