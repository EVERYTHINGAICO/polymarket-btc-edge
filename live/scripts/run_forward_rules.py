"""Ejecuta SOLO las reglas forward congeladas en forward_rules_config.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.forward_rules import evaluate_forward_rules, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalua reglas forward congeladas, sin optimizacion.")
    parser.add_argument("--config", default="forward_rules_config.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    db_path = Path(args.db) if args.db else ROOT / str(config["data"]["db_path_relative"])
    result = evaluate_forward_rules(db_path, config)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
