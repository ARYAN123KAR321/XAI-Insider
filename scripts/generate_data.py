"""Generate a synthetic dataset to disk.

Usage: python scripts/generate_data.py --seed 42 --days 7 [--out data/generated/custom]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.config.settings import get_settings
from app.simulator.generator import GenConfig, Generator, write_dataset


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--out", type=str, default=None)
    args = p.parse_args()

    settings = get_settings()
    result = Generator(GenConfig(seed=args.seed, days=args.days)).run()
    out_dir = Path(args.out) if args.out else \
        settings.generated_dir / result["manifest"]["dataset_name"]
    paths = write_dataset(out_dir, result)
    print(f"Dataset written to {out_dir}")
    for fam, path in paths.items():
        print(f"  {fam:>15}: {path}")
    print(f"Scenarios: {[s['scenario_id'] for s in result['manifest']['scenarios']]}")


if __name__ == "__main__":
    main()