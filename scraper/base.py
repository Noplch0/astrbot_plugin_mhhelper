"""Shared HTTP / retry / rate-limit helpers for kiranico scrapers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger("astrbot-mhhelper.scraper")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def make_client(proxy: str | None = None, timeout: float = 30.0) -> httpx.AsyncClient:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "headers": headers,
        "follow_redirects": True,
    }
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.5,
) -> str:
    """GET with exponential backoff. Returns text or raises."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 410):
                raise FileNotFoundError(f"{r.status_code} {url}")
            # other codes - retry
            log.warning("HTTP %s for %s (attempt %s)", r.status_code, url, attempt + 1)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Fetch error for %s (attempt %s): %s", url, attempt + 1, exc)
        await asyncio.sleep(backoff ** attempt)
    raise RuntimeError(f"Failed after {retries} attempts: {url}") from last_exc


async def gather_with_limit(
    coros: list,
    limit: int = 4,
    delay: float = 0.1,
) -> list:
    """Run coroutines with concurrency cap and small inter-request delay."""
    sem = asyncio.Semaphore(limit)

    async def _wrapped(coro):
        async with sem:
            try:
                res = await coro
            except Exception:
                log.exception("coro failed")
                return None
            await asyncio.sleep(delay)
            return res

    return await asyncio.gather(*[_wrapped(c) for c in coros])