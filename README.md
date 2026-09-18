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

插件的所有功能都收在一个 **AstrBot 指令组** `/mh` 下,统一格式:

```
/mh <子命令> [名字] [作品]
```

**怪物**

| 命令 | 说明 |
|---|---|
| `/mh 怪物列表 [作品]` | 列出该作大型怪物 |
| `/mh 怪物 <名字> [作品]` | 怪物基础信息(种类 / HR 点数 / HP) |
| `/mh 肉质 <名字> [作品]` | 肉质表(斩 / 打 / 弹 / 火水雷冰龙 / 麻) |
| `/mh 弱点 <名字> [作品]` | 属性弱点与状态异常累积 |
| `/mh 素材 <名字> [作品]` | 剥取 / 破坏 / 目标报酬 |

**技能**

| 命令 | 说明 |
|---|---|
| `/mh 技能列表 [作品]` | 列出该作技能 |
| `/mh 技能 <名字> [作品]` | 技能各等级效果 |

**其他**

| 命令 | 说明 |
|---|---|
| `/mh 作品` | 列出已启用的作品 |
| `/mh 更新 [作品]` | 管理员: 在线刷新数据 |
| `/mh 帮助` | 显示完整帮助 |

每个子命令都注册了英文 / 简写别名: `help` `monsters` `monster` `meat` `weak`
`rewards` `skills` `skill` `games` `update`,以及 `肉` `属性` `报酬` `掉落` `刷新` 等中文简写。
`/mh meat Rathian` 等价于 `/mh 肉质 Rathian`。

`作品` 可省略;省略时按"该用户上次使用 → 配置默认作品"解析。作品标识支持:
`mhworld / world / 世界 / iceborne`、`mhrise / rise / 崛起 / sunbreak`、`mhwilds / wilds / 荒野`。
指令组本身也有别名 `/怪物猎人`。

---

## 管理面板里的指令

插件只注册 **一个** AstrBot 指令组,因此管理面板 → 插件 → 指令管理 里只会看到一行
`mh`;点击展开即可看到上面的二级命令列表和各自的中文介绍,并可对单个子指令
**启用 / 禁用 / 重命名**。相比把每个功能都注册成独立顶层命令,面板清爽很多。

> 直接发送裸 `/mh`(不带子命令)时,AstrBot 会自动渲染出该指令组的树形结构,内容与
> 面板中的列表一致 —— 所以"帮助"既有 `/mh 帮助` 的排版版,也有 `/mh` 的速查版。

`/mh 更新` 标记为管理员指令,只有 `admins_id` 中的用户可触发,且需要
`allow_runtime_update` 为 `true`。

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
| `/mh 肉质 火龙` | 肉质查询,使用你的默认作品 |
| `/mh 肉质 火龙 mhrise` | 肉质查询,显式指定崛起 |
| `/mh meat Rathian wilds` | 英文别名查询,作品用英文标识 |
| `/mh 技能 攻击` | 模糊匹配"攻击"系列技能 |
| `/mh 怪物列表` | 列出上次使用作品的怪物 |
| `/mh 更新 mhwilds` | 管理员刷新 mhwilds 数据 |
| `/mh` | 渲染指令组树形结构(速查) |

> 注意子命令与参数之间需要空格:`/mh 肉质 火龙`。旧版的连写形式
> `/mh肉质`(v0.1.x)已不再支持,详见 `RELEASE_NOTES_v0.2.0.md`。

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
├── main.py                  ← AstrBot 指令组 mh 的注册与分发(@register)
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
├── scripts/
│   ├── bootstrap_data.py    ← 维护者全量刷新数据
│   └── _import_test.py      ← 本地冒烟测试(被 .gitignore 排除,不入库)
├── tests/
│   ├── fixtures/            ← 离线样本 JSON
│   ├── _astrbot_fake.py     ← AstrBot 注册/过滤器层的最小仿真
│   ├── test_command_group.py← 指令组结构 + 路由回归测试
│   └── test_*.py
└── .github/workflows/data-refresh.yml
```

---

## 开发与测试

```powershell
pip install -r requirements-dev.txt
pytest -q
```

测试位于 `tests/`,使用 `tests/fixtures/` 内的极简样本离线运行,不需要联网。

其中 `tests/test_command_group.py` 是专门锁住"面板里只有一个 `mh` 指令组"这条
需求的回归测试:它借助 `tests/_astrbot_fake.py`(按 AstrBot 真实语义实现的
指令组注册 / 过滤器 / 唤醒前缀仿真)加载 `main.py`,断言顶层指令数量、子指令
名称与别名表、树形结构、每条子指令的路由与参数解析。

另有一个可读性更好的本地冒烟脚本,会直接打印出指令树和逐条路由结果:

```powershell
python scripts/_import_test.py
```

退出码非 0 表示有断言失败。

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