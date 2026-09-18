"""CLI entry: refresh data/*.json from kiranico.

Usage:
    python -m scraper.run_update [--game mhwilds] [--proxy ...] [--concurrency 4] [--delay 0.1]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import make_client
from .common import SCRAPERS
from .normalize import normalize_ailments, trim_rewards

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


async def refresh_game(
    game: str,
    *,
    proxy: str | None = None,
    concurrency: int = 4,
    delay: float = 0.1,
    only: str | None = None,  # "monsters" | "skills" | None
) -> tuple[int, int]:
    scraper = SCRAPERS[game]()
    monsters_count = 0
    skills_count = 0
    async with make_client(proxy=proxy) as client:
        if only in (None, "monsters"):
            monsters = await scraper.list_monsters(client)
            log.info("[%s] %d monsters to fetch", game, len(monsters))
            sem = asyncio.Semaphore(concurrency)

            async def _fetch_mon(item):
                async with sem:
                    try:
                        m = await scraper.fetch_monster(client, item["id"], **({"slug": item.get("slug")} if item.get("slug") else {}))
                    except Exception as e:  # noqa: BLE001
                        log.warning("[%s] monster %s failed: %s", game, item["id"], e)
                        return None
                    if isinstance(m, dict):
                        m.setdefault("name_en", item.get("name") or "")
                        # 图标只存在于列表页（详情页没有），从 index item 带过来；
                        # 解析不到就留空，插件会跳过图标（而不是画一个破图）。
                        m["icon"] = item.get("icon") or m.get("icon") or ""
                    await asyncio.sleep(delay)
                    return m

            results = await asyncio.gather(*[_fetch_mon(it) for it in monsters])
            monsters_out = [m for m in results if m]
            monsters_count = len(monsters_out)
            for m in monsters_out:
                if isinstance(m.get("ailments"), dict):
                    m["ailments"] = normalize_ailments(m["ailments"])
                if isinstance(m.get("rewards"), dict):
                    m["rewards"] = trim_rewards(m["rewards"])
            _write_monsters(game, monsters_out)
        if only in (None, "skills"):
            skills = await scraper.list_skills(client)
            log.info("[%s] %d skills to fetch", game, len(skills))
            sem = asyncio.Semaphore(concurrency)

            async def _fetch_skill(item):
                async with sem:
                    try:
                        s = await scraper.fetch_skill(client, item["id"], **({"slug": item.get("slug")} if item.get("slug") else {}))
                    except Exception as e:  # noqa: BLE001
                        log.warning("[%s] skill %s failed: %s", game, item["id"], e)
                        return None
                    if isinstance(s, dict):
                        s.setdefault("name_en", item.get("name") or "")
                    await asyncio.sleep(delay)
                    return s

            results = await asyncio.gather(*[_fetch_skill(it) for it in skills])
            skills_out = [s for s in results if s]
            skills_count = len(skills_out)
            _write_skills(game, skills_out)
    return monsters_count, skills_count


def _write_monsters(game: str, items: list[dict[str, Any]]) -> None:
    out_dir = DATA_DIR / "monsters"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": datetime.now(timezone.utc).strftime("kiranico-%Y-%m-%d"),
        "source": _source_url(game, "monsters"),
        "monsters": items,
    }
    with (out_dir / f"{game}.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("[%s] wrote %s (%d monsters)", game, out_dir / f"{game}.json", len(items))


def _write_skills(game: str, items: list[dict[str, Any]]) -> None:
    out_dir = DATA_DIR / "skills"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": datetime.now(timezone.utc).strftime("kiranico-%Y-%m-%d"),
        "source": _source_url(game, "skills"),
        "skills": items,
    }
    with (out_dir / f"{game}.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("[%s] wrote %s (%d skills)", game, out_dir / f"{game}.json", len(items))


def _source_url(game: str, kind: str) -> str:
    if game == "mhwilds":
        return f"https://mhwilds.kiranico.com/zh/data/{kind}"
    if game == "mhrise":
        return f"https://mhrise.kiranico.com/data/{kind}"
    if game == "mhworld":
        return f"https://mhworld.kiranico.com/en/{'monsters' if kind == 'monsters' else 'skilltrees'}"
    return ""


def write_meta(updates: dict[str, dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta.update(updates)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    games = [args.game] if args.game else list(SCRAPERS.keys())
    started = time.time()
    for g in games:
        if g not in SCRAPERS:
            log.warning("Unknown game: %s (skipping)", g)
            continue
        t0 = time.time()
        try:
            monsters, skills = await refresh_game(
                g,
                proxy=args.proxy or None,
                concurrency=args.concurrency,
                delay=args.delay,
                only=args.only,
            )
            write_meta({g: {"monsters": monsters, "skills": skills, "seconds": round(time.time() - t0, 1)}})
        except Exception as e:  # noqa: BLE001
            log.exception("[%s] refresh failed: %s", g, e)
    log.info("Done in %.1fs", time.time() - started)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Refresh mhhelper data from kiranico.")
    p.add_argument("--game", choices=list(SCRAPERS.keys()), help="Limit to a single game.")
    p.add_argument("--proxy", default="", help="HTTP proxy URL (optional).")
    p.add_argument("--concurrency", type=int, default=4, help="Max concurrent requests per game.")
    p.add_argument("--delay", type=float, default=0.1, help="Inter-request delay seconds.")
    p.add_argument("--only", choices=["monsters", "skills"], help="Only refresh one kind.")
    args = p.parse_args()
    asyncio.run(main_async(args))


log = logging.getLogger("astrbot-mhhelper.scraper")

if __name__ == "__main__":
    main()