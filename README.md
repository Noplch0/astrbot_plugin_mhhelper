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

**怪物**（基础信息 / 肉质 / 弱点 已合并成这一条）

| 命令 | 说明 |
|---|---|
| `/mh 怪物 <名字> [作品]` | 一条消息给出：怪物名 → 属性弱点（最强两项）→ 肉质表 → 异常累积 |

**技能**（永远发文本，不转图）

| 命令 | 说明 |
|---|---|
| `/mh 技能 <名字> [作品]` | 技能各等级效果（中文描述） |

**其他**

| 命令 | 说明 |
|---|---|
| `/mh 作品` | 列出已启用的作品 |
| `/mh 更新 [作品]` | 管理员: 在线刷新数据 |
| `/mh 帮助` | 显示完整帮助 |

`怪物` 的旧名字 `肉质` / `弱点` / `属性` / `meat` / `weak` 都保留为**别名**，
返回的是同一份合并报告，习惯输入照旧可用。其余别名：`help` `monster` `info`
`skill` `games` `update`，以及 `肉` `刷新` 等中文简写。

> v0.3.6 删掉了 `怪物列表` / `技能列表` / `素材` 三条子命令。

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

## 输出格式（表格怎么显示）

肉质表这类宽表格如果直接当纯文本发出去，在手机 QQ 里会错位得没法看。
v0.3.0 起格式化层统一产出 **markdown**，再由配置项 `output_mode` 决定怎么送出去：

| `output_mode` | 行为 | 适合 |
|---|---|---|
| `auto`（默认） | 按平台自动选：QQ 全系 → 图片；Telegram / 飞书 / Discord 等 → markdown | 绝大多数人 |
| `image` | 用 AstrBot 自带的**文转图**把结果渲染成一张图片卡片 | 想让表格最好看 |
| `markdown` | 直接发 markdown 原文 | 确认客户端会渲染 md |
| `text` | 退化成空格对齐的纯文本 | 兜底 / 不想要图片 |

> **为什么 QQ 要转图片？** QQ **个人号**（NapCat / aiocqhttp）只支持文字 / 图片 / 语音，
> 聊天框**不渲染 markdown**；直接发 `| 部位 | 斩 |` 会原样显示竖线，比现在还难看。
> 所以 QQ 上唯一能让表格好看的方案是把结果渲染成图片。QQ **官方机器人** 平台侧支持
> 自定义 markdown，但 AstrBot 适配器目前对外只暴露文字 / 图片。

`image` 模式调用 AstrBot 的 `Star.html_render()`。如果宿主机没装好文转图
（缺 Playwright / 渲染服务不可用），插件会自动**回退成纯文本**，不会让查询失败。

> **图片为什么清晰、而且铺满整张？** AstrBot 的文转图默认「按 `full_page` 截整页」，
> 视口约 **800×615**，而且默认是 **JPEG `quality=40`** —— 所以卡片模板必须铺满画布、
> 字号也得够大，否则截图里内容会缩在左上角而且发糊（v0.3.2 及以前就是这样）。
> v0.3.3 起：
>
> - 卡片用 `width: max-content; min-width: 100%`（宽表格能撑开卡片、短内容也铺满画布），
>   `min-height: calc(100vh - 50px)` 纵向填满视口，内容短时纵向居中；
> - **`body` 也要 `width: max-content; min-width: 100%`**：卡片被宽表格撑开时 body 必须
>   跟着一起长，否则卡片会向右溢出把右边距吃掉（表现为"左侧留白比右侧长"，且只在
>   表格较宽的怪物上出现）；
> - 正文字号 **24px**（AstrBot 官方 `base.html` 的基准是 25px，之前只有 15px）；
> - 通过 `options={"quality": 92}` 覆盖默认的 40。

> **卡片顶部的怪物图标**（v0.3.5 起）：`image` 模式下，卡片顶部会居中显示该怪物的
> 图鉴图标，下面的怪物名也居中。图标只出现在图片里 —— `text` / `markdown` 输出
> **完全不变**。图标取自 kiranico（见「数据来源与归属」），URL 随数据一起提交，
> 加载失败时（图挂了 / 端点取不到）会直接隐藏，卡片退化成「只有居中的怪物名」。

> **技能查询永远发文本**：技能只有几行字，转图只会更难读 —— 所以无论
> `output_mode` 选什么都发纯文本（v0.3.7 起）。

> **文本版与图片版结构一致**：`/mh 怪物` 的合并报告在两种模式下顺序完全相同 ——
> 怪物名（图片版另加居中图标）→ 属性弱点（最强两项）→ 肉质表 → 异常累积
> （横向表格）。文本版只是把同一份 markdown 降级成空格对齐的纯文本。
>
> 老版本 AstrBot 的 `html_render` 没有 `options` 形参，插件会捕获 `TypeError` 后
> **改用默认参数重试一次**，所以不会因为传参而丢掉图片模式。

---

## 运行期数据放在哪

插件唯一的运行期状态是「每个用户上次查询的作品」。按 AstrBot 官方规范，它写在
**AstrBot 自己的数据目录**里，而不是插件目录内：

```
<AstrBot>/data/plugin_data/astrbot_plugin_mhhelper/user_last_game.json
```

取路径用的是官方 API（[插件存储规范](https://docs.astrbot.app/dev/star/guides/storage.html)）：

```python
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_mhhelper"
```

> **为什么不能写在插件目录里？** AstrBot 更新 / 重装插件时会整体替换插件目录，
> 写在那儿的用户数据会跟着一起没。v0.3.1 起把状态挪到了 AstrBot 的 `data/` 下。
> （注意区分：仓库根目录也有个 `data/`，那是随仓库提交的**静态游戏数据**，两者无关。）

三级降级，保证任何部署形态下插件都能启动：

| 顺序 | 解析方式 | 何时生效 |
|---|---|---|
| 1 | `get_astrbot_data_path() / "plugin_data" / <插件名>` | 官方 API 可用（正常情况） |
| 2 | 从插件路径反推：插件在 `<root>/data/plugins/<插件名>` → `<root>/data/plugin_data/<插件名>` | AstrBot 版本较老、没有该 API |
| 3 | 退回插件目录下的 `plugin_data/`（同时打 WARNING） | 上面都不行，只求插件别挂 |

从 v0.3.0 升上来时，插件目录里那份旧 `plugin_data/user_last_game.json` 会被自动
读取、写到新位置，然后删掉旧文件（空目录一并清理），用户无感。

---

## 更新插件后为什么还在跑旧代码

AstrBot 加载插件用的是 `data.plugins.<插件目录名>.main` 这个名字，重载 / 更新插件时
它只清理 `sys.modules` 里**以 `data.plugins.<插件目录名>` 开头**的条目（见
`astrbot/core/star/star_manager.py` 的 `_purge_modules`）。

而本插件的子包是用**裸顶层名**导入的（`core.formatter`、`scraper.common`），这个
前缀根本匹配不到它们。于是更新插件后，进程内存里还留着上一个版本的子模块，新的
`main.py` 会把它们绑上去 —— 表现就是**报错内容和磁盘上的文件完全对不上**，例如：

```
cannot import name 'light_table' from 'core.formatter'
(/AstrBot/data/plugins/astrbot_plugin_mhhelper/core/formatter.py)
```

而磁盘上那个 `formatter.py` 里明明定义了 `light_table`。

v0.3.2 起 `main.py` 会在导入任何子模块**之前**把这些陈旧条目从 `sys.modules` 摘掉
（同时也处理了「别的插件先占了 `core` 这个名字」的情况），因此点一次「重载插件」
即可生效，**不需要**重启 AstrBot。日志里能看到：

```
[astrbot_plugin_mhhelper] dropped 4 stale module(s) left over from a previous load:
core, core.data_loader, core.errors, core.formatter
```

> `main.py` 顶部的 `_INTERNAL_PACKAGES` 必须列全插件自己的顶层包，否则新加的子包不会
> 被清理 —— `tests/test_import_bootstrap.py` 会强制这件事。

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
| `output_mode` | `auto` | 结果输出方式：`auto` / `text` / `markdown` / `image`，见上一节 |
| `proxy` | `""` | 抓取 kiranico 时使用的代理 URL |
| `max_rows_per_message` | `30` | 单条消息最多行数，超出后截断 |
| `allow_runtime_update` | `true` | 是否允许 `/mh 更新` 在线刷新 |

> v0.3.5 起删掉了 `with_icon`（一个从没被读取过的死配置）。怪物图标现在只在
> `image` 模式下自动出现在卡片顶部，不需要也无法单独开关。

---

## 数据来源与归属

所有数据来自 [kiranico.com](https://kiranico.com) 三个子域:

- `mhworld.kiranico.com`(MHWorld / Iceborne,英语页面,**无中文**)
- `mhrise.kiranico.com`(MHRise / Sunbreak,英语页面,**无中文**)
- `mhwilds.kiranico.com`(MHWilds,**含中文**)

**怪物图标**与**中文名**同样来自这三个站点的 zh 列表页（采集规则见
`scraper/listing.py`），随 `data/monsters/*.json`、`data/skills/*.json` 一起提交，
所以**查询时不需要联网**；真正去取图的是 AstrBot 的文转图端点。三个站点的列表页
结构各不相同，各自的地址是：

| 作品 | 列表页（怪物） | 列表页（技能） |
|---|---|---|
| 荒野 | `https://mhwilds.kiranico.com/zh/data/monsters` | —（页面即中文） |
| 崛起 | `https://mhrise.kiranico.com/zh/data/monsters?view=lg` | `https://mhrise.kiranico.com/zh/data/skills` |
| 世界 | `https://mhworld.kiranico.com/zh/monsters` | `https://mhworld.kiranico.com/zh/skilltrees` |

MHWorld 和 MHRise 的**详情页**只有英文，但上面这些 zh 列表页有完整中文名，所以本插件
对三作都显示中文名（括号里附英文原名）；技能的各等级效果描述也已从 zh 详情页采集。数据里若某条只有英文名，显示时会退回英文名；
**绝不会把内部 id（如 `1301934382` / `KpViL`）当作名字显示**。

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
│   ├── formatter.py         ← 数据 → markdown(标题 / 列表 / GFM 表格)
│   ├── render.py            ← markdown → HTML 卡片 / 纯文本 + 输出模式决策
│   └── errors.py
├── scraper/                 ← 抓取工具链(维护者用)
│   ├── base.py
│   ├── kiranico.py
│   ├── common.py            ← 三作的抓取器
│   ├── listing.py           ← 三站列表页的图标 / 中文名解析(纯正则,测试可离线跑)
│   ├── normalize.py
│   └── run_update.py
├── data/                    ← 全量静态 JSON(随仓库提交，与 AstrBot 的 data/ 无关)
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
│   ├── _import_test.py      ← 本地冒烟测试(被 .gitignore 排除,不入库)
│   └── _card_preview.py     ← 打印 markdown / 纯文本并生成卡片 HTML 预览(同样不入库)
├── tests/
│   ├── fixtures/            ← 离线样本 JSON
│   ├── _astrbot_fake.py     ← AstrBot 注册/过滤器层的最小仿真
│   ├── test_command_group.py← 指令组结构 + 路由 + 输出模式回归测试
│   ├── test_formatter.py    ← markdown 契约
│   ├── test_render.py       ← markdown 降级 / 模式决策 / light_table 导入兼容
│   ├── test_state_dir.py    ← 运行期状态目录解析 + 旧数据迁移
│   ├── test_import_bootstrap.py ← 子模块淘汰规则（插件更新后仍用旧代码的根因）
│   ├── test_listing.py      ← 三站图标 / 中文名解析规则（含各站的反例）
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

`tests/test_state_dir.py` 锁住运行期状态的存放位置:官方 API 优先级、路径反推
降级、最后退路，以及旧 `plugin_data/user_last_game.json` 的读取与迁移。
`tests/test_render.py` 另外锁住了 `light_table` 的双名导入兼容。
`tests/test_import_bootstrap.py` 锁住下面「更新后仍在用旧代码」那节讲的子模块淘汰
规则，并且会强制 `main.py` 里新出现的顶层包必须登记到 `_INTERNAL_PACKAGES`。

另有一个可读性更好的本地冒烟脚本,会直接打印出指令树和逐条路由结果:

```powershell
python scripts/_import_test.py
```

想看真实数据经过新格式化后的样子(markdown / 纯文本摘录,并生成一张卡片预览 HTML):

```powershell
python scripts/_card_preview.py
```

退出码非 0 表示有断言失败。

---

## 已知限制

- **MHWorld / MHRise 无中文**:kiranico 这两个子域不提供中文页面,怪物与技能名字显示为英文(可在代码中加 `aliases` 字段维护中文别名)。
- **数据陈旧**:游戏更新时仓库内置数据会过时,通过 `/mh 更新` 或维护者重新 bootstrap 刷新。
- **大表格截断**:肉质/报酬表超过 `max_rows_per_message` 会截断,显示部分。
- **文转图依赖 AstrBot**:`image` 模式需要宿主机的 AstrBot 文转图可用(Playwright 或渲染服务)。不可用时自动回退纯文本,表格会退化成空格对齐。
- **图片模式不适合复制**:`image` 模式发的是图片,用户没法直接选中文字复制;需要复制时把 `output_mode` 调成 `text` 或 `markdown`。
- **升级后建议点一次「重载插件」**:v0.3.2 起插件会自己清理上一版残留在内存里的子模块,
  但保险起见升级后仍然点一下「重载插件」最稳妥(见上一节)。

---

## 致谢

数据源: [kiranico.com](https://kiranico.com) — 怪物猎人系列最完整的数据库。
设计参考: [ncatbot-monsterhunter](https://github.com/aaaaas811/ncatbot-monsterhunter)、社区野生爬虫脚本。
插件框架: [AstrBot](https://github.com/Soulter/AstrBot)。