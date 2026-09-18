# astrbot_plugin_mhhelper v0.1.0

Initial release of the Monster Hunter information plugin for AstrBot.

## Coverage

Three games bundled with **full data committed** (zero network dependency after install):

| Game | Monsters | Skills | Size |
|---|---:|---:|---:|
| Monster Hunter: Wilds (荒野) | 55 | 177 | ~560 KB |
| Monster Hunter Rise / Sunbreak (崛起) | 78 | 147 | ~2.0 MB |
| Monster Hunter: World (世界) | 95 | 203 | ~1.2 MB |

Total dataset: **~3.7 MB**.

## Commands

21 first-class AstrBot commands (each individually manageable in the admin UI):

- `/mh` — help
- `/mh肉质` / `/mh_meat` — meat / hit-zone table
- `/mh弱点` / `/mh_weak` — elemental weakness + ailments
- `/mh素材` / `/mh_rewards` — carve / break / reward materials
- `/mh怪物` / `/mh_monster` — monster basic info
- `/mh怪物列表` / `/mh_monsters` — list large monsters
- `/mh技能` / `/mh_skill` — skill level effects
- `/mh技能列表` / `/mh_skills` — list skills
- `/mh作品` / `/mh_games` — list enabled games
- `/mh更新` / `/mh_update` — admin: refresh data from kiranico

`game` argument is optional; defaults to the user's last-used game (or mhwilds). Game identifiers: `mhworld` / `mhrise` / `mhwilds`  (and 世界 / 崛起 / 荒野 etc.).

## Install

AstrBot admin UI → Plugin management → Install via URL → paste:

    https://github.com/Noplch0/astrbot_plugin_mhhelper

## Features

- Multi-language monster / skill lookup (Chinese + English + aliases)
- Fuzzy matching with candidate suggestions on miss
- Per-user "last game used" memory (persisted across restarts)
- Per-game enable/disable (`enable_world` / `enable_rise` / `enable_wilds`)
- Output formatted as plain text — no heavy ASCII borders, easy to read on QQ / 飞书 / Telegram

## Maintenance

Data can be refreshed by the maintainer via:

    pip install -r requirements-dev.txt
    python scripts/bootstrap_data.py            # all games
    python scripts/bootstrap_data.py mhwilds   # one game
    git add data && git commit && git push

GitHub Actions weekly auto-refresh workflow is included (`.github/workflows/data-refresh.yml`); it opens a draft PR every Monday for review.

## Tests

24 pytest cases covering: monster/skill lookup, formatter output, data loader, metadata.yaml.

    pip install -r requirements-dev.txt
    pytest -q

## License & Credits

- Data source: [kiranico.com](https://kiranico.com) (MHWorld / MHRise / MHWilds)
- Plugin framework: [AstrBot](https://github.com/Soulter/AstrBot)
- Inspiration: community plugins `ncatbot-monsterhunter`, `mhws_Wiki_Crawler`

## Known Limitations

- MHWorld and MHRise do not have Chinese names on kiranico — those monsters / skills display in English. Add `aliases` in the data file for Chinese shortcuts.
- mhwilds monster `name_en` is not yet populated (placeholder empty string). The English slug is available via the `id` field.
- Game data goes stale as kiranico updates; maintainers should refresh periodically via `/mh更新` or by re-running the scraper.