"""Download the BTC 15m orderbook parquet locally.

Why:
  Remote DuckDB scans against hf:// repeatedly hit Hugging Face resolver rate
  limits. Download once, analyze locally.

Usage:
  py scripts/download_orderbook_part0.py

Optional:
  Set HF_TOKEN or HUGGING_FACE_HUB_TOKEN in the environment for higher limits.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from huggingface_hub import hf_hub_download

from src.data_sources.sources_config import POLYMARKET

REPO_ID = POLYMARKET.repo_id
REVISION = POLYMARKET.revision
REMOTE_PATH = "data/orderbook/crypto=BTC/timeframe=15-minute/part-0.parquet"
OUT_DIR = ROOT / "data" / "raw" / "orderbook"
OUT_PATH = OUT_DIR / "btc15m_orderbook_part0.parquet"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"))
    print(f"repo: {REPO_ID}@{REVISION[:12]}")
    print(f"remote: {REMOTE_PATH}")
    print(f"HF token present: {token_present}")
    print(f"out: {OUT_PATH}")

    if OUT_PATH.exists() and OUT_PATH.stat().st_size > 1_000_000_000:
        print("Local file already exists; skipping download.")
        print(f"size_bytes: {OUT_PATH.stat().st_size}")
        print(f"sha256: {file_sha256(OUT_PATH)}")
        return 0

    downloaded = hf_hub_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        revision=REVISION,
        filename=REMOTE_PATH,
        local_dir=(ROOT / ".hf_cache_orderbook").as_posix(),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    downloaded_path = Path(downloaded)
    print(f"downloaded_cache_path: {downloaded_path}")
    shutil.copy2(downloaded_path, OUT_PATH)
    print(f"size_bytes: {OUT_PATH.stat().st_size}")
    print(f"sha256: {file_sha256(OUT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
