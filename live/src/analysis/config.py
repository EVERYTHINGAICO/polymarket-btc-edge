"""Carga del pre-registro analysis_config.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path('analysis_config.json')


@dataclass(frozen=True)
class AnalysisConfig:
    """Inmutable. Cualquier cambio requiere reload + bump de version."""
    raw: dict
    config_version: str
    frozen_at_utc: str

    def get(self, *path: str) -> Any:
        """Navega keys anidadas: config.get('gate1', 'D_threshold_abs')."""
        cur = self.raw
        for key in path:
            cur = cur[key]
        return cur


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AnalysisConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Pre-registro no encontrado: {p}. Sin pre-registro no se puede analizar.')
    raw = json.loads(p.read_text(encoding='utf-8'))
    return AnalysisConfig(
        raw=raw,
        config_version=raw['config_version'],
        frozen_at_utc=raw['frozen_at_utc'],
    )
