"""Optional post-processing helpers shared across scrapers."""
from __future__ import annotations

from typing import Any


def trim_rewards(rewards: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Strip empty / unknown categories."""
    return {k: v for k, v in rewards.items() if v}


def normalize_ailments(ailments: dict[str, int]) -> dict[str, int]:
    """Map raw names to canonical Chinese names."""
    mapping = {
        "Poison": "毒",
        "Sleep": "睡眠",
        "Paralysis": "麻痹",
        "Stun": "昏厥",
        "Blast": "爆破异常",
        "Exhaust": "减气",
        "Fireblight": "火异常",
        "Waterblight": "水异常",
        "Thunderblight": "雷异常",
        "Iceblight": "冰异常",
        "Dragonblight": "龙异常",
    }
    out: dict[str, int] = {}
    for k, v in ailments.items():
        key = mapping.get(k, k)
        out[key] = v
    return out