# astrbot_plugin_mhhelper — 怪物猎人辅助插件

AstrBot 插件,提供 **怪物猎人:世界(MHWorld)、怪物猎人:崛起(MHRise)、怪物猎人:荒野(MHWilds)** 三作的大型怪物肉质 / 弱点 / 报酬 / 技能数值查询。

数据源:[kiranico.com](https://kiranico.com),打包时**全量数据随仓库提交**,安装后**零网络依赖**即可用。

---

## 一键安装

AstrBot 管理界面 → 插件管理 → 通过仓库链接安装,粘贴本仓库的 GitHub URL:

```
https://github.com/Noplch0/astrbot_plugin_mhhelper
```

AstrBot 会自动 git clone → 把仓库根拷贝到 `data/plugins/astrbot_plugin_mhhelper/` → 加载 `main.py`。

> 仓库名 `astrbot_plugin_mhhelper` 与 `metadata.yaml` 中的 `name` 一致,这是 AstrBot 加载机制的硬约束,改名后需要同步修改 `metadata.yaml`。

---

## 命令速查

```
/mh 怪物列表 [game]   列出该作大型怪物
/mh 怪物 <名> [game]   怪物基础信息(种类/HR点/HP)
/mh 肉质 <名> [game]   肉质表(斩/打/弹/火/水/雷/冰/龙/麻)
/mh 弱点 <名> [game]   属性弱点与状态异常累积
/mh 素材 <名> [game]   剥取/破坏/目标报酬
/mh 技能列表 [game]    列出该作技能
/mh 技能 <名> [game]   技能各等级效果
/mh 作品               列出已启用作品
/mh 更新 [game]        管理员:在线刷新数据
/mh 帮助               帮助
```

`game` 可省略;省略时按"上次使用 → 默认 mhwilds"。作品标识支持:`mhworld / world / 世界`、`mhrise / rise / 崛起`、`mhwilds / wilds / 荒野`。

支持中英文别名混用,例如 `/mh 肉质 雌火龙`、`/mh meat Rathian`、`/mh 肉质 雷颚龙 mhrise`。

---

## 维护者:更新数据

游戏更新后(尤其是 MHWilds 持续更新),刷新本仓库的 `data/`:

```powershell
git clone https://github.com/Noplch0/astrbot_plugin_mhhelper
cd astrbot_plugin_mhhelper
pip install -r requirements-dev.txt

# 全量刷新
python scripts/bootstrap_data.py

# 或仅刷新单作
python scripts/bootstrap_data.py mhwilds

# 提交
git add data/
git commit -m "data: refresh $(Get-Date -Format yyyy-MM-dd)"
git push
```

> **首次 bootstrap 需能直连 kiranico**。如果你的网络环境受限,可配置代理:
> `python scripts/bootstrap_data.py --proxy http://127.0.0.1:7890`。

> GitHub Actions 已经配置了每周一 06:00 UTC 自动跑抓取脚本生成 draft PR(`.github/workflows/data-refresh.yml`)。你只需要 review 后 merge。

---

## 命令解析示例

| 用户输入 | 解析为 |
|---|---|
| `/mh 肉质 火龙` | 肉质查询,默认 mhwilds |
| `/mh 肉质 火龙 mhrise` | 肉质查询,显式指定崛起 |
| `/mh meat Rathian wilds` | 英文别名查询,作品用英文标识 |
| `/mh 技能 攻击 boost` | 模糊匹配"攻击 boost"系列技能 |
| `/mh 怪物列表` | 列出 mhwilds 怪物 |
| `/mh 更新 mhwilds` | 管理员刷新 mhwilds 数据 |

---

## 配置项 (`_conf_schema.json`)

| 项 | 默认 | 说明 |
|---|---|---|
| `default_game` | `mhwilds` | 未指定 game 时的默认作品 |
| `enable_world` / `enable_rise` / `enable_wilds` | `true` | 启用对应作品 |
| `with_icon` | `false` | 是否在结果附带怪物图鉴图标 |
| `proxy` | `""` | 抓取 kiranico 时使用的代理 URL |
| `max_rows_per_message` | `30` | 单条消息最多行数,超出后截断 |
| `allow_runtime_update` | `true` | 是否允许 `/mh update` 在线刷新 |

---

## 数据来源与归属

所有数据来自 [kiranico.com](https://kiranico.com) 三个子域:

- `mhworld.kiranico.com`(MHWorld / Iceborne,英语页面,**无中文**)
- `mhrise.kiranico.com`(MHRise / Sunbreak,英语页面,**无中文**)
- `mhwilds.kiranico.com`(MHWilds,**含中文**)

MHWorld 和 MHRise 的怪物 / 技能名字在 kiranico 上仅提供英文/日文,本插件默认显示英文名(可在插件内手动添加中文别名)。MHWilds 的中文直接来自 kiranico。

数据版权归 kiranico.com 所有,本仓库仅做聚合与便捷查询。

---

## 项目结构

```
astrbot_plugin_mhhelper/
├── metadata.yaml            ← AstrBot 插件清单(关键)
├── main.py                  ← 命令分发入口(@register)
├── _conf_schema.json        ← 配置 schema
├── requirements.txt         ← 运行期依赖(httpx / bs4 / lxml)
├── requirements-dev.txt     ← 开发期额外依赖(jieba / pytest)
├── README.md
├── core/                    ← 业务逻辑
│   ├── data_loader.py
│   ├── monster_index.py
│   ├── skill_index.py
│   ├── formatter.py
│   └── errors.py
├── scraper/                 ← 抓取工具链(维护者用)
│   ├── base.py
│   ├── kiranico.py
│   ├── common.py            ← 三作的抓取器
│   ├── normalize.py
│   └── run_update.py
├── data/                    ← 全量静态 JSON(随仓库提交)
│   ├── meta.json
│   ├── monsters/
│   │   ├── mhworld.json
│   │   ├── mhrise.json
│   │   └── mhwilds.json
│   └── skills/
│       ├── mhworld.json
│       ├── mhrise.json
│       └── mhwilds.json
├── scripts/bootstrap_data.py
├── tests/
└── .github/workflows/data-refresh.yml
```

---

## 开发与测试

```powershell
pip install -r requirements-dev.txt
pytest -q
```

测试位于 `tests/`,使用 `tests/fixtures/` 内的极简样本离线运行,不需要联网。

---

## 已知限制

- **MHWorld / MHRise 无中文**:kiranico 这两个子域不提供中文页面,怪物与技能名字显示为英文(可在代码中加 `aliases` 字段维护中文别名)。
- **数据陈旧**:游戏更新时仓库内置数据会过时,通过 `/mh 更新` 或维护者重新 bootstrap 刷新。
- **大表格截断**:肉质/报酬表超过 `max_rows_per_message` 会截断,显示部分。
- **图片未发送**:为兼容多数 IM 适配器,默认不发送图标(`with_icon=false`)。

---

## 致谢

数据源: [kiranico.com](https://kiranico.com) — 怪物猎人系列最完整的数据库。
设计参考: [ncatbot-monsterhunter](https://github.com/aaaaas811/ncatbot-monsterhunter)、社区野生爬虫脚本。
插件框架: [AstrBot](https://github.com/Soulter/AstrBot)。