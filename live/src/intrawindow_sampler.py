"""Sampler intra-ventana del midpoint de Polymarket (Fase 6.b).

Thread daemon que muestrea `pm_up_price` cada N segundos durante los 15 min
de la ventana y persiste cada punto en `observations_intrawindow`.

Read-only sobre Polymarket. Nunca lanza al caller.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from src.db import insert_intrawindow_sample
from src.polymarket_feed import midpoint_to_float

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_MAX_SECONDS = 900


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class IntrawindowSampler:
    def __init__(
        self,
        db_path,
        client,
        window_id: str,
        up_token_id: str,
        open_epoch_seconds: int,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        max_seconds: int = DEFAULT_MAX_SECONDS,
    ) -> None:
        self.db_path = db_path
        self.client = client
        self.window_id = window_id
        self.up_token_id = up_token_id
        self.open_epoch_seconds = int(open_epoch_seconds)
        self.interval_seconds = int(interval_seconds)
        self.max_seconds = int(max_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples_taken = 0
        self.errors: list[dict] = []

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name=f'IntrawindowSampler({self.window_id})')
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        next_sample_at = float(self.open_epoch_seconds)
        while not self._stop.is_set():
            now = time.time()
            t_seconds = int(now - self.open_epoch_seconds)
            if t_seconds > self.max_seconds:
                return
            if now < next_sample_at:
                remaining = next_sample_at - now
                if self._stop.wait(timeout=min(1.0, max(0.0, remaining))):
                    return
                continue
            self._take_one_sample(t_seconds)
            next_sample_at = float(self.open_epoch_seconds) + float((self.samples_taken + len(self.errors)) * self.interval_seconds)
            if next_sample_at <= now:
                next_sample_at = now + self.interval_seconds

    def _take_one_sample(self, t_seconds: int) -> None:
        try:
            payload = self.client.fetch_midpoint(self.up_token_id)
            price = midpoint_to_float(payload)
            sampled_at = _utc_now_iso()
            insert_intrawindow_sample(self.db_path, self.window_id, t_seconds, price, sampled_at)
            self.samples_taken += 1
        except Exception as exc:
            self.errors.append({'t_seconds': t_seconds, 'error': repr(exc)})
