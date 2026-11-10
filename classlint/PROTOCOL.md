# classlint 协议 · 生产关系层 + 流量层数据模型、守恒律与交叉规则 v0.4

**状态：草案 ｜ 日期：2026-09-24 ｜ 读者：协议实现者**
**条款用词"必须/应当/可以"为规范性词汇，含义同 RFC 2119 的 MUST/SHOULD/MAY。**

本协议定义 classlint 世界仓库的条目格式、生产关系层数据模型与审计规则集。
溯源：条目格式与 lint 架构继承自 WGP/canonlint；本协议不引入 WGP 的治理层（canon 状态机、矛盾标注、评审程序）——classlint 是审计工具，不是治理平台。

## 1. 条目

条目是世界的最小审计单元。**一个条目 = `codex/` 目录下一个 UTF-8 Markdown 文件**，由 YAML frontmatter 头与正文组成：

```markdown
---
id: harbor-guild
title: 码头行会
type: faction
extracts:
  - id: dockworkers
    what: 装卸费抽成
depends_on:
  - id: grain-trade
    critical: true
---

正文。文本是源头，模型是投影。
```

### 1.1 frontmatter 字段表

| 字段 | 必填 | 类型 | 约束 |
|---|---|---|---|
| `id` | **必须** | string | 全库唯一；`^[a-z0-9-]+$`；一旦发布永不更改、永不复用 |
| `title` | **必须** | string | 显示名 |
| `type` | **必须** | string | `^[a-z0-9-]+$`。**实体开放**：词汇用户自定义，初始建议集 `character` / `location` / `faction` / `item` / `event` / `resource` / `institution` |
| 关系字段（契约列过的全部具名字段） | 可选 | 列表 | 见 §2 |
| `relations` | 可选 | 对象列表 | 规范形：`{type, target, ...注解}`；与具名字段进入同一张边表，可含自定义关系名 |
| `demand` | 可选 | 对象 | 需求侧声明（v0.3）：`{物资名: {amount, unit}}`，见 §2.4；只允许非 `flow` 条目 |
| `population` | 可选 | 数字 | 人口基数（v0.3）：大于 0 的有限数字，见 §2.4；只允许非 `flow` 条目 |
| `x-*` | 可选 | 任意 | 扩展字段必须带 `x-` 前缀，审计器放行 |

除上表与 `x-` 前缀字段外，任何字段**必须**被审计器拒绝（CL103）。

例外只有两种：`type: flow` 的条目额外接受 §2.3 列的流量字段；非 `flow` 的条目额外接受 §2.4 的需求侧字段（`demand`/`population`）。同样的字段写进不匹配的条目仍按 CL103 拒绝——字段的合法性由**条目类型**决定，不是把词表放宽。

### 1.2 引用语法

所有跨条目引用**必须**使用 `id`，禁止文件路径或标题。理由同 WGP：id 不可变，文件可移动。

## 2. 生产关系层：七种关系

**固定关系，实体开放。** 本层下判语的生产关系固定为本节七种；实体词汇开放。规范形 `relations` 还允许自定义关系名：它们只建边、查目标存在性并进入 `graph`，不自动获得 PE 语义。

本条列的是**本层要判的七种生产关系**（`owns`/`controls`/`extracts`/`coerces`/`legitimizes`/
`owes`/`depends_on`）。契约 `world.schema.json` 的 `x-relation-vocabulary` 是关系名的唯一
真值表（含每条的 `means` 定义与可接受的拼法变体）；本层照单收下契约列过的关系名，其中
`canon_refs`/`conflicts_with`/`exchanges_with` 属于治理与流通，本层不判——但它们进图，
`graph` 与解析都会认。

**名分依据有两条写法，进的是同一张 `legitimizes` 图**（v1.1）：`A derives_legitimacy_from B`
与 `B legitimizes A` 同义（方向相反）。本层把前者翻译成后者再判定，所以 PE003 的闭环、
外部锚点、报在哪一侧与旧写法逐条一致（`classlint/tests/legit-canonical-*` 与
`check_legitimacy_forms_are_indistinguishable` 守着这条）。它**不**进 PE001/PE004/PE005 的
抽取与供给图：名分不是生产关系。（PE009 是例外方向：`legitimizes` 正是收账通道之一，债主能撤回正当性就收得回债。）

七种关系全部是**有向边**，写在关系施加方的 frontmatter 里。`A 的 frontmatter 含 <relation>: [{id: B}]` 意为 `A —relation→ B`：

| 关系 | 含义 | 方向读法 | 可选属性 |
|---|---|---|---|
| `owns` | 占有 | A 占有 B（所有/占有，区别于控制：管家控制、领主占有） | `note` |
| `controls` | 控制 | A 控制 B | `note` |
| `extracts` | 抽取 | A 从 B 抽取（地租、税、剩余劳动…） | `what`（抽取物）、`note` |
| `coerces` | 暴力 | A 对 B 施加暴力/镇压 | `note` |
| `legitimizes` | 合法化 | A 给 B 合法性 | `note` |
| `owes` | 债务 | A 欠 B | `what`（债务内容）、`note` |
| `depends_on` | 供养 | A 靠 B 养（断供即崩的程度用 critical 标）；`kind` 只说**哪一类物资** | `critical`（bool）、`kind`（string，物资五类或 `x-` 实验值）、`note` |
| `derives_legitimacy_from` | 名分依据 | A 的说法以 B 为依据（与 `B legitimizes A` 同义，方向相反） | `critical`（bool）、`note` |

### 2.1 元素形式

每个关系字段是列表，元素可以是：

```yaml
controls:
  - town-watch                    # 简式：纯 id
  - id: smugglers                 # 对象式
    note: 只控码头，不控海面
depends_on:
  - id: grain-trade
    critical: true                # 断供即崩
```

对象式**必须**含 `id`；属性键限上表所列（外加 `x-` 前缀扩展）；`what`/`note`/`kind` 为 string，`critical` 为 bool。违反 = CL104。

### 2.2 与 WGP 的差异说明

WGP 的 `depends_on` 要求 `kind`/`critical` 必填且 kind 五值定集（v1.1 起 `legitimacy` 已搬成独立关系名 `derives_legitimacy_from`）；classlint 将二者降为可选、kind 改自由词汇——八层链与 kind 分族是 WGP 治理层的建模工具，classlint 的审计只关心边的存在性与方向。这条差异是契约 `x-stricter-than-contract` 登记过的，实现在存储层的**一个开关**上（`store/model.py` 的 `Entry.depends_on_requires_annotations`，本引擎置 `False`）——不是两份建边代码：边层（`Entry.relations` / `relation_shape_errors`）与 canonlint 共用同一份，`tests/test_store.py` 的「两个引擎建同一张边图」钉住它。


### 2.3 流量层数据模型（v0.2）

流量 = **`type: flow` 的 codex 条目**，声明一笔有方向的流量。四条线各有自己的必填字段，公共字段四条线一致。

公共字段：

| 字段 | 必填 | 约束 |
|---|---|---|
| `line` | **必须** | `logistics` / `violence` / `information` / `people` 之一 |
| `from` / `to` | **必须** | 起点/母体、终点/驻地的条目 id（同 §1.2，悬空由 CL105 报） |
| `note` | 可选 | string |
| `trend` | 可选 | `rising` / `flat` / `falling`；给 PE006（抽取在上升）与 PE007（人口在增长）用，时序层就位前由作者手工标注 |

每条线的必填字段：

| `line` | 含义 | 本线必填字段 |
|---|---|---|
| `logistics` | 物流：粮食、税、贡赋 | `what`（自由词，建议 `grain`/`tax`/`tribute`）、`amount`（>0 的数字）、`unit`（非空字符串） |
| `violence` | 暴力：驻军、补给半径 | `amount`（>0）、`unit`、`supply_radius`（≥0 的数字）、`radius_unit`（非空字符串） |
| `information` | 信息：驿路、情报时延 | `delay`（≥0 的数字，日） |
| `people` | 人员：迁徙、流放、朝圣 | `what`（自由词，建议 `migration`/`exile`/`pilgrimage`）、`amount`（>0）、`unit` |

`amount` 这类数字字段必须是**有限数字**；`bool` 不算数字（YAML 的 `true` 解析成 bool，不能冒充 1）。写了别的线的字段（比如物流条目的 `delay`）同样非法。以上任何一条不满足 = CL108。

```yaml
---
id: flow-grain
title: 岁贡线
type: flow
line: logistics
from: grain-store
to: capital
what: grain
amount: 1200
unit: 石
trend: flat
note: 每年秋后北仓解送
---

正文。
```

这一层只回答「这条流量表述是否完整」；「这条流量在数值上是否自洽」（流入够不够需求、军队跨线有没有补给）由 Sprint 5 的守恒律（§2.4、PE010–PE012）判。

### 2.4 需求侧数据模型（v0.3）

守恒律需要知道「要多少」，而需求属于消费方，所以 `demand`/`population` 写在**实体卡**上（不是流量卡上；写进 `flow` 条目仍是 CL103）：

```yaml
---
id: capital
title: 王都
type: location
population: 8000
demand:
  grain:
    amount: 1000
    unit: 石
---
```

| 字段 | 必填 | 约束 |
|---|---|---|
| `demand` | 可选 | 映射：物资名 → `{amount: >0 的有限数字, unit: 非空字符串}`；不接受其它键 |
| `population` | 可选 | 大于 0 的有限数字（bool 不算） |

**数据分级**（PE010 的判定口径）：

1. 目标实体声明了 `demand`：同单位流入求和，`流入 < 需求` = error（断供）；流入存在但单位全都对不上 = warning（单位不可比，无法判定）；完全没有流入 = error（断供）。
2. 目标实体没有声明 `demand`：这条流入无法对账 = warning——不静默。静默等于把「没写」判成「够用」，正是 CA704 在协议 1.10 之前 fail-open 的教训。
3. `population` 是规模参照：PE012 用它判断人口流失的端点是否可对账；PE010 的硬判定仍只用 `demand`（人口推算的定量守恒仍未定口径，不冒充需求数）。
4. `demand`/`population` 形状坏掉 = CL108（结构错误），PE010/PE012 不拿坏数据下判——否则会出现「用 0 参与求和」的误导性断供。

信息时延律（信息线）需要事件时间，classlint 没有时间字段，**推后到 Sprint 8 时间线层**，本版不实现。

## 3. 审计规则注册表

### 3.1 编号段

| 段 | 类别 |
|---|---|
| CL1xx | 结构（解析/frontmatter/schema/引用存在性） |
| PE0xx | 政治经济学规则（规划八条：PE001–PE008 是核心，PE009 是生产关系层新增（占空号不改已规划编号），PE010–PE012 是流量层守恒律；本版已全部实现 PE001–PE012） |

### 3.2 结构规则（确定性）

| 编号 | 级别 | 定义 |
|---|---|---|
| CL100 | error | 文件无法解析（无 frontmatter / YAML 错误 / 非映射） |
| CL101 | error | 缺少必填字段（`id` / `title` / `type`） |
| CL102 | error | `id` 非法格式或全库重复 |
| CL103 | error | 存在不带 `x-` 前缀的未定义字段 |
| CL104 | error | 关系字段违反 §2.1 schema |
| CL105 | error | 关系目标 `id` 不存在（含流量条目的 `from`/`to`） |
| CL106 | warning | 拆分前的旧写法（`depends_on` + `kind: legitimacy`）——已按新关系名判定，只在输出里提示改写法（同 canonlint 的 CA111） |
| CL107 | warning | 关系名拼写近失：`relations[].type` 与某个规范名只差一个字符（去掉连字符/下划线后算，如 `extractss`、`depend_on`）。边**已按规范名建好**（所以 PE 族判得到它），本条只提示疑似拼写错误；距离 ≥2 的自定义关系名原样保留、不提示（同 canonlint 的 CA110） |
| CL108 | error | 流量层格式非法：`flow` 条目违反 §2.3（`line` 缺失/非法、`from`/`to` 缺失或非字符串、本线必填字段不全或类型不对、写了别的线的字段、`trend` 不在词表、`note` 非字符串）；或实体卡的需求侧声明违反 §2.4（`demand` 不是映射、物资名为空、`amount` 不是 >0 的有限数字、`unit` 非空字符串、多余键、`population` 不是 >0 的数字） |

### 3.3 政治经济学规则

| 编号 | 级别 | 定义 |
|---|---|---|
| PE001 | error | **抽取必须有基础**：存在 `A —extracts→ B` 但 A 对 B 没有任何 `controls` / `coerces` / `owns` 边。目标 `B` 不存在时**不判本条**（CL105 已报，「对不存在的东西论证它没有基础」是空话） |
| PE002 | error/warning | **不能镇压自己的供养者**：存在 `A —coerces→ B` 且 `A —depends_on→ B`。`critical: true` = error，否则 warning |
| PE003 | error | **合法性不得无锚闭环**：`legitimizes` 图的强连通分量（含自环）若没有任何来自分量外的 `legitimizes` 输入，报警。有外部锚点的互锁合法（依据：WGP v0.5 魔戒 dogfood，规范性互锁是常态）。**`derives_legitimacy_from` 写的那条也在这张图里**（翻译成反向的 `legitimizes`，判定与旧写法逐条相同）——名分是关系名，不再是 `depends_on` 的 `kind` 值 |
| PE004 | error | **剩余必须收敛（定性版）**：`extracts` 子图存在环（含自环）——剩余在循环中互相凭空抽取、不落地于任何生产（黑洞）。定量判定（抽取量 vs 剩余量）待流量层数据就位后回填 |
| PE005 | warning | **劳动者必须被覆盖（定性版）**：存在 `A —extracts→ B` 且 B 没有任何**物质**来源侧边——被抽取者的剩余/再生产在模型里不可见（隐形剥削嫌疑）。「物质来源侧边」= `extracts`、`exchanges_with`、或带物质类别 `kind`（`resource`/`production`/`economy`/`fiscal`/`manpower`，见 `world.schema.json` 的 `x-strict-vocabulary.depends_on.kind`）的 `depends_on`。一条裸 `depends_on`（无 kind，如 `depends_on: [weather]`）**不**消音：自然条件既不是生产关系也不承担再生产，消音必须是一次物质关系的声明。报在 B 侧：修法是补上带 kind 的物质来源，或确认 B 为终端生产者。定量判定待流量层回填 |
| PE006 | warning | **危机积累**（v0.4）：实体卡声明了 `demand`，同单位流入 ≥ 需求但余量 < 10%（剩余刚好够活），且该实体有一条 `what` 为 `tax`/`tribute`、`trend: rising` 的物流外流（抽取在上升）——报在实体侧。其它自由词（`grain` 等）的上涨外流算贸易，不据此判危机；classlint 没有时间轴，`trend` 是作者标注的定性方向，不是增长率 |
| PE007 | warning | **结构性压力**（v0.4）：`people` 流入某实体且 `trend: rising`（人口在增长），而该实体涉及 `owns` 关系（自己占有别人、或被别人占有——占有关系未变）——报在该实体侧。这是结构判据，不推算人口增长率 |
| PE008 | error | **镇压自己的基础**（v0.4）：存在 `A —coerces→ B`，且物流线从 `B` 流向 `A`（B 在供养 A）——镇压对象同时是供养来源，报在 A 侧。PE002 的流量层结构版：PE002 看承重依赖，PE008 看实际物流 |
| PE009 | warning | **债务必须收得回来**：存在 `A —owes→ B` 而模型里没有任何收账通道。通道有两条：**债主对债务人的支配**（`B —controls/coerces/extracts/legitimizes→ A` 任一条——能指挥、能强制、能抽取偿付、能撤回正当性），或**债务人对债主的承重依赖**（`A —depends_on→ B`，且这条依赖 `critical: true` 或带物质类别 `kind`：`resource`/`production`/`economy`/`fiscal`/`manpower`）。裸 `depends_on` 与 `x-` 实验类别不算通道。两条都没有 = 这笔债在模型里无法兑现，只是一句记账。报在 A 侧。注意 `owes` 与 `depends_on` 是两条不同的边（债务不等于供养），所以这里**不**因为写了 `owes` 就假定欠债方依赖债主——依赖得另外写出来 |
| PE010 | error/warning | **物流守恒**（v0.3）：实体卡声明了 `demand` 时，同单位 `logistics` 流入之和必须 ≥ 需求，不够 = error（断供）；流入存在但单位全不可比 = warning；完全没流入 = error。目标没有声明该 `what` 的需求 = warning（这条流入无法对账，不静默）。`demand` 形状坏掉由 CL108 报，本条不判 |
| PE011 | error | **补给律**（v0.3）：存在 `A —violence→ B` 但没有任何 `logistics` 流量以 `B` 为终点——驻军地没有物流线到达，军队跨线无补给（结构判据，不需要数值） |
| PE012 | warning | **人口律**（v0.3）：`people` 流量的起点与终点是同一实体（流失没有去向），或两端都没有声明 `population`（流失规模无法对账；给至少一端加 population）。结构判据为主，规模核账待人口推算口径定稿 |

### 3.4 报告级输出（永不进退出码）

- **关系图**：`classlint graph <仓库> [--format dot|json]`——节点 = 有效 id 条目，边 = 已建关系边（含契约关系与规范形自定义关系；悬空目标不进图）；DOT 可直接喂 Graphviz，JSON 供任意前端消费。
- **影响报告**：`classlint check <仓库> --impact ID...`——指定条目的 `depends_on` 反向传递闭包（"改 A 炸 B"的待复核队列），参考 WGP 的 CA504。**不含主体自身**：环会把主体带回自己的下游，而「改 A 会炸 A」是环的结论（由结构规则报），不是影响报告的结论——与 CA504 同口径。
- **正文提及报告**：`check --json` 的每个可解析条目带 `mentions: [{entity, alias, count}]`，把 `codex/entities.yaml` 注册的别名映射到稳定 id。匹配区分大小写、最长优先且不重叠，英文/数字别名要求词边界；缺文件或无匹配为 `[]`。只读正文，不改原文、findings、CL/PE、文本输出或 graph；坏注册表是配置错误（退出码 2）。
- **`--json` 的字段**（`classlint_version` / `entries` / `findings` / `reports` / `rules_disabled` / `judgement_complete`）以实际输出为准，逐字段说明见 `classlint/README.md` 的「`--json` 输出字段」一节。

**无传递违规原则：** 只判直接边。A 抽取 B、B 的供养断裂并不使 A 连带违规；间接影响是**影响报告**（`--impact`，§3.4）的职责——它已实现，只报 `depends_on` 的反向传递闭包，不改变任何判定结论。

**判定一致性要求：** 同一仓库快照、同一协议版本，任何兼容实现的确定性判定**必须**逐条一致。

### 3.5 规则的开关

CL1xx 结构规则不可关（它们是数据 sanity 本身）。PE 规则**可以关，不能改定义**——在 `classlint.yaml` 中：

```yaml
rules:
  PE003: off    # YAML 1.1 下未加引号的 off 会解析成 false，两种写法等价
```

未知规则编号 = 配置错误（退出码 2）。规则包扩展（`rules/` 目录的 YAML 声明式规则）留待后续版本。

关掉规则会让「通过」这句话变弱：通过的是一台少了几条规则的机器。因此 `check` 在有关闭
规则时返回 `3`（见 §4），并在摘要行与 `--json` 的 `rules_disabled` / `judgement_complete`
里如实标出——关规则可以，但要留下痕迹。

## 4. 退出码

- `0`：无 error（warning 不影响），且没有规则被关闭；或虽已关闭规则，但显式加了 `--accept-disabled-rules`；
- `1`：存在 error；
- `2`：用法/环境/配置错误（含**指错目录**：`codex/` 不在时直说「不像一个 classlint 世界仓库」，而不是收 0 条给出全绿报告——整机版的「看起来在被审」）；
- `3`：判定通过，但有 PE 规则被 `rules: off` 关闭——「通过」只覆盖仍开着的规则，
  自动化无法据此断言全面通过。确认关闭是有意的，加 `--accept-disabled-rules` 回到 0
  （约定与 canonlint 侧「跳过必须显式授权」一致）。

## 5. 边界声明

本层证明**结构完整性**，不证明数值自洽（抽取量是否真超过剩余）。数值审计属流量层：Sprint 4 做数据模型（CL108 四线流量 + demand/population），Sprint 5 做守恒律（PE010–PE012），Sprint 6 做交叉规则（PE006–PE008）——量是否守恒由 PE010–PE012 判，结构是否互相拆台由 PE006–PE008 判；信息时延律需要事件时间，待 Sprint 8 时间线层。AI 辅助判断将来同样只递建议条子，永不进退出码。
