"""One-shot bootstrap script: populate data/*.json from kiranico.

Run from the repo root:

    pip install -r requirements.txt
    python scripts/bootstrap_data.py           # all three games
    python scripts/bootstrap_data.py mhwilds   # one game

This is the script maintainers use after cloning the repo to refresh the
bundled data, or right before publishing a new release.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.run_update import main as scraper_main  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Populate data/*.json by scraping kiranico.")
    p.add_argument(
        "game",
        nargs="?",
        choices=["mhworld", "mhrise", "mhwilds"],
        help="Limit to a single game (default: all three).",
    )
    p.add_argument("--proxy", default="", help="HTTP proxy URL (optional).")
    p.add_argument("--concurrency", type=int, default=3, help="Max concurrent requests.")
    p.add_argument("--delay", type=float, default=0.1, help="Inter-request delay seconds.")
    args = p.parse_args()

    start = time.time()
    # Delegate to scraper.run_update.main() but with our parsed args.
    sys.argv = ["scraper.run_update"]
    if args.game:
        sys.argv += ["--game", args.game]
    sys.argv += ["--concurrency", str(args.concurrency), "--delay", str(args.delay)]
    if args.proxy:
        sys.argv += ["--proxy", args.proxy]

    scraper_main()
    elapsed = time.time() - start
    print(f"\nBootstrap finished in {elapsed:.1f}s")
    print("Data written to:")
    for p in sorted(Path("data").rglob("*.json")):
        size_kb = p.stat().st_size // 1024
        print(f"  - {p}  ({size_kb} KB)")


if __name__ == "__main__":
    main()