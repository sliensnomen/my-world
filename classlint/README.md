# classlint · 马克思主义政治经济学审计工具

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
作者写文本，工具建模型，模型展示结构，审计报出作者看不见的矛盾。

[项目文书](项目文书.md)（定位与三层架构） · [开发计划](开发计划.md) · [ROADMAP](ROADMAP.md)
姊妹项目：[canonlint](../README.md)（本工具的条目格式与 lint 架构来源）。**读卡代码两个引擎共用一份**：
id 语法、frontmatter 切分、契约词表、关系名归一化都在 [`store/parse.py`](../store/parse.py)，
`classlint.py` 只转发（`tests/test_store.py` 的结构锁 + 行为锁守着）。classlint 自己保留的
只有**判定**侧的东西：规则与它自己的字段政策（`depends_on` 这里收裸字符串，canonlint 要求
`{id, kind, critical}` 对象——这是两边协议的真实分歧，改任一边都要同时改两处文档）。

**合并的代价（写在这里，免得以后有人踩）**：`classlint/classlint.py` 现在会 `import store.parse`，
所以它**不再是一个能单独拷走的单文件脚本**——必须和仓库一起用，而且要**从仓库根**调用
（内部把自己所在目录的上一层塞进了 `sys.path`；拷到别处或 `pip install` 都拿不到 `store`）。
换来的是「同一份数据同一份判定」：id 语法、frontmatter 切分、关系名归一化不会再各漂一份。
另外那处真实分歧被收成了**一个开关**（`Entry.depends_on_requires_annotations`，canonlint 开、
classlint 关），不是两份建边代码——所以它改的时候只有一个地方要改。

**状态：生产关系层已完成（PE001–PE008 + `graph` + `--impact`）；流量层的四线数据模型（CL108）、守恒律（PE010–PE012 + `demand`/`population`）、交叉规则（PE006–PE008）与个人关系层（PE013/PE014 + 五种个人关系）已就绪；时间线（`moment`/`shift`，CL109）与视图（`view`/`fork`）已就绪，本版 PE 共 PE001–PE014。**
PE004/PE005 的定量回填尚未做——排期见 [ROADMAP.md](ROADMAP.md)。

## 用法

```bash
pip install pyyaml
# 从仓库根调用（路径写全，免得依赖当前目录在哪）
python3 classlint/classlint.py init ~/worlds/econ          # 初始化世界仓库（建 codex/ + classlint.yaml）
# ……在 codex/ 下写条目……
python3 classlint/classlint.py check ~/worlds/econ         # 读取全部条目，输出结构化数据
python3 classlint/classlint.py check ~/worlds/econ --json  # 机器可读输出
python3 classlint/classlint.py graph ~/worlds/econ --format dot   # 关系图（DOT 或 JSON）
python3 classlint/classlint.py view ~/worlds/econ                 # 关系图 + 时间线视图（<repo>/view.html，自包含）
python3 classlint/classlint.py fork ~/worlds/econ alt-history     # 反事实推演：把当前世界开成一条 Git 分支
```

退出码：`0` 正常；`1` 条目存在错误；`2` 用法/环境错误（含指错目录与非法 `WGP_JUDGE_BACKEND`）；`3` 判定通过，但有 PE 规则被 `rules: off` 关掉——「通过」只覆盖仍开着的规则，确认是有意关闭的加 `--accept-disabled-rules` 才回到 0（见 [PROTOCOL.md](PROTOCOL.md) §4）。

判定默认由 Registry 的 `core-cl` 与 `pe` 两个 Pack 执行：CL100–CL109 逐规则注册，扫描/建索引与判定分离，PE 保持编号顺序和 `rules: off` 语义。紧急回退使用 `WGP_JUDGE_BACKEND=legacy python3 classlint/classlint.py check <仓库>`；legacy 仍保留，尚未到发布周期后的删除签核阶段。

### 视图与反事实推演（Sprint 9）

`view` 生成一个**自包含 HTML**（默认 `<repo>/view.html`，`--out` 可改路径）：两页签——**关系图**（节点 = 条目，边 = 七种生产关系 + 个人关系）与**时间线**（`moment` 点上事件、`shift` 结构变迁区间）。没有外链、没有 CDN，世界目录拷到离线机器也能双击打开；渲染用原生 SVG，不引 D3/Cytoscape（视图数据在 `<script id="view-data">` 里，想换库/接前端直接读它）。

`fork` 把世界当前状态开成一条 Git 分支——**反事实推演就是 Git 分支**：

```bash
python3 classlint/classlint.py fork ~/worlds/econ alt-history   # 在 alt-history 里改设定、看世界怎么塌
git -C ~/worlds/econ diff main..alt-history                     # 看两条世界的分歧
```

世界内分歧点建议在时间线里补一条 `shift` 记录（「如果 X 没发生」），让视图也画得出岔路；世界外历史（谁改了什么）本来就在 `git log` 里。

### `--json` 输出字段（`check --json`）

一个 JSON 对象，顶层字段只有这些：

| 字段 | 类型 | 含义 |
|---|---|---|
| `classlint_version` | string | 本工具版本（当前 `"0.1"`）。与 WGP 的 `protocol_version` 不是一回事 |
| `entries` | 对象列表 | 每个**可解析**条目：`id`（frontmatter 缺失或不是字符串时为 `null`）、`path`（相对世界根的路径）、`meta`（frontmatter 原样）、`body_chars`（正文字数）、`mentions`（正文别名报告）。解析失败的文件不进此列表，由 `findings` 中的 CL100 报告 |
| `findings` | 对象列表 | 每条发现：`rule`（`CL1xx` / `PE0xx`）、`level`（`error` / `warning`）、`entry`（条目文件路径；仓库级为 `null`）、`message` |
| `reports` | 对象列表 | 报告级输出，**永不进退出码**；目前是 `--impact` 的 `{subject, downstream}` 受影响队列 |
| `rules_disabled` | 字符串列表 | 被 `rules: off` 关掉的规则编号；空列表 = 全规则在跑 |
| `judgement_complete` | bool | `true` = 本次判定覆盖全部规则；有规则被关时为 `false`（此时退出码 3，除非 `--accept-disabled-rules`） |

`mentions` 是正文别名报告：`{entity, alias, count}`。别名来自 `codex/entities.yaml`；缺文件或没有匹配时为 `[]`。匹配区分大小写、最长别名优先且不重叠，英文/数字别名要求词边界。它是只读报告，不改变 findings、CL/PE 判定、文本输出或 graph；坏注册表返回退出码 2。

`--impact ID...` 只改 `reports`：不改 `findings`，也不改退出码。

## 审计规则（协议 v0.4，见 [PROTOCOL.md](PROTOCOL.md)）

- **CL1xx 结构规则**（不可关）：解析失败、缺必填字段、id 非法/重复、未定义字段、关系 schema 违规、关系目标不存在、流量条目格式（CL108）。
- **PE001** 抽取必须有基础（`controls`/`coerces`/`owns`）；**PE002** 不能镇压自己的供养者（critical 依赖 = error，否则 warning）；**PE003** 合法性不得无锚闭环（有外部锚点的互锁合法）；**PE004** 剩余必须收敛（extracts 子图无环，定性版）；**PE005** 劳动者必须被覆盖（被抽取者须有来源侧边，定性版 warning）；**PE009** 债务必须收得回来（`owes` 要有收账通道：债主能支配/强制/抽取/撤回正当性，或债务人对债主持有 `critical: true` 或带物质类别 `kind` 的 `depends_on`，warning）；**PE010** 物流守恒（同单位流入 ≥ 需求，缺数据报 warning 不静默）；**PE011** 补给律（暴力线驻军地必须有物流线到达）；**PE012** 人口律（流失要有可对账的端点）；**PE006** 危机积累（剩余刚好够活 + `tax`/`tribute` 外流上升）；**PE007** 结构性压力（人口上升 + 占有关系未变）；**PE008** 镇压自己的基础（`coerces` 的对象同时用物流供养自己）。

PE 规则可在 `classlint.yaml` 关闭（`rules: {PE003: off}`）——可以关，不能改定义。

报告级输出（永不进退出码）：`classlint graph <仓库> [--format dot|json]` 关系图；`classlint check <仓库> --impact ID...` 下游影响报告。

测试：`python3 classlint/tests/run_tests.py`（27 个夹具世界：正反例 + 三个经典结构 + 两个真实作品 dogfood + 名分依据的规范形写法，期望判定钉死）。

## 世界仓库结构

```
world/
├── classlint.yaml        # 项目配置（名称、工具版本、PE 规则开关）
├── rules/                # 预留目录；YAML 声明式自定义规则尚未实现
├── lore/                 # 世界背景、规则、声音指南
├── codex/                # 实体注册表——条目唯一位置
│   ├── entities.yaml     # 稳定 ID 与别名注册
│   ├── characters/
│   ├── locations/
│   └── factions/         # 目录纯组织，可自由增删子目录
├── stories/              # 叙事正文
├── timeline/             # 世界内历史
└── records/              # 派生输出
```

**条目 = `codex/` 下一个带 YAML frontmatter 的 Markdown 文件。**
文本是源头，模型是投影：Git + Markdown 是唯一事实来源。

## 实体 ID 规范（Sprint 0）

- 仅允许小写字母、数字、连字符（`^[a-z0-9-]+$`）；
- 全库唯一；一旦发布永不更改、永不复用；
- 正文中的别名通过 `codex/entities.yaml` 注册到稳定 ID，识别结果见 `check --json` 的 `mentions`。

## 核心原则

1. **Git + Markdown 是唯一事实来源。** 文本变，模型变。
2. **固定关系，实体开放。** 关系是语法，实体是词汇。
3. **三层咬合：** 流量层（数据）→ 生产关系层（结构）→ 个人关系层（语境修正）。
4. **AI 可选。** AI 是提取器、提问者、连接者，不是裁决者；产出永不自动入库。
