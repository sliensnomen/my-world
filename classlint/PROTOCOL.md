# classlint 协议 · 生产关系层 v0.1

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
| `x-*` | 可选 | 任意 | 扩展字段必须带 `x-` 前缀，审计器放行 |

除上表与 `x-` 前缀字段外，任何字段**必须**被审计器拒绝（CL103）。

### 1.2 引用语法

所有跨条目引用**必须**使用 `id`，禁止文件路径或标题。理由同 WGP：id 不可变，文件可移动。

## 2. 生产关系层：七种关系

**固定关系，实体开放。** 关系是语法，必须固定为本节的具名关系；实体是词汇，用户随便定义。

本条列的是**本层要判的七种生产关系**（`own`/`controls`/`extracts`/`coerces`/`legitimizes`/
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

WGP 的 `depends_on` 要求 `kind`/`critical` 必填且 kind 六值封版；classlint 将二者降为可选、kind 改自由词汇——八层链与 kind 分族是 WGP 治理层的建模工具，classlint 的审计只关心边的存在性与方向。

## 3. 审计规则注册表

### 3.1 编号段

| 段 | 类别 |
|---|---|
| CL1xx | 结构（解析/frontmatter/schema/引用存在性） |
| PE0xx | 政治经济学规则（规划八条：本版已实现 PE001–PE005 与 PE009；PE006–PE008 属流量层，待数据模型就位——债务那条是生产关系层的新增，占下一个空号，不改已规划的编号） |

### 3.2 结构规则（确定性）

| 编号 | 级别 | 定义 |
|---|---|---|
| CL100 | error | 文件无法解析（无 frontmatter / YAML 错误 / 非映射） |
| CL101 | error | 缺少必填字段（`id` / `title` / `type`） |
| CL102 | error | `id` 非法格式或全库重复 |
| CL103 | error | 存在不带 `x-` 前缀的未定义字段 |
| CL104 | error | 关系字段违反 §2.1 schema |
| CL105 | error | 关系目标 `id` 不存在 |

### 3.3 政治经济学规则

| 编号 | 级别 | 定义 |
|---|---|---|
| PE001 | error | **抽取必须有基础**：存在 `A —extracts→ B` 但 A 对 B 没有任何 `controls` / `coerces` / `owns` 边 |
| PE002 | error/warning | **不能镇压自己的供养者**：存在 `A —coerces→ B` 且 `A —depends_on→ B`。`critical: true` = error，否则 warning |
| PE003 | error | **合法性不得无锚闭环**：`legitimizes` 图的强连通分量（含自环）若没有任何来自分量外的 `legitimizes` 输入，报警。有外部锚点的互锁合法（依据：WGP v0.5 魔戒 dogfood，规范性互锁是常态）。**`derives_legitimacy_from` 写的那条也在这张图里**（翻译成反向的 `legitimizes`，判定与旧写法逐条相同）——名分是关系名，不再是 `depends_on` 的 `kind` 值 |
| PE004 | error | **剩余必须收敛（定性版）**：`extracts` 子图存在环（含自环）——剩余在循环中互相凭空抽取、不落地于任何生产（黑洞）。定量判定（抽取量 vs 剩余量）待流量层数据就位后回填 |
| PE005 | warning | **劳动者必须被覆盖（定性版）**：存在 `A —extracts→ B` 且 B 没有任何**物质**来源侧边——被抽取者的剩余/再生产在模型里不可见（隐形剥削嫌疑）。「物质来源侧边」= `extracts`、`exchanges_with`、或带物质类别 `kind`（`resource`/`production`/`economy`/`fiscal`/`manpower`，见 `world.schema.json` 的 `x-strict-vocabulary.depends_on.kind`）的 `depends_on`。一条裸 `depends_on`（无 kind，如 `depends_on: [weather]`）**不**消音：自然条件既不是生产关系也不承担再生产，消音必须是一次物质关系的声明。报在 B 侧：修法是补上带 kind 的物质来源，或确认 B 为终端生产者。定量判定待流量层回填 |
| PE009 | warning | **债务必须收得回来**：存在 `A —owes→ B` 而模型里没有任何收账通道。通道有两条：**债主对债务人的支配**（`B —controls/coerces/extracts/legitimizes→ A` 任一条——能指挥、能强制、能抽取偿付、能撤回正当性），或**债务人依赖债主**（`A —depends_on→ B`——断供即崩，续借的开关在债主手里）。两条都没有 = 这笔债在模型里无法兑现，只是一句记账。报在 A 侧。注意 `owes` 与 `depends_on` 是两条不同的边（债务不等于供养），所以这里**不**因为写了 `owes` 就假定欠债方依赖债主——依赖得另外写出来 |

### 3.4 报告级输出（永不进退出码）

- **关系图**：`classlint graph <仓库> [--format dot|json]`——节点 = 条目，边 = 契约列过的全部关系（本层判的七种 + `canon_refs`/`conflicts_with`/`exchanges_with`/`derives_legitimacy_from`）；DOT 可直接喂 Graphviz，JSON 供任意前端消费。
- **影响报告**：`classlint check <仓库> --impact ID...`——指定条目的 `depends_on` 反向传递闭包（"改 A 炸 B"的待复核队列），参考 WGP 的 CA504。

**无传递违规原则：** 只判直接边。A 抽取 B、B 的供养断裂并不使 A 连带违规；间接影响是将来影响报告（Sprint 3）的职责。

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

- `0`：无 error（warning 不影响），且**没有规则被关闭**；
- `1`：存在 error；
- `2`：用法/环境/配置错误；
- `3`：判定通过，但有 PE 规则被 `rules: off` 关闭——「通过」只覆盖仍开着的规则，
  自动化无法据此断言全面通过。确认关闭是有意的，加 `--accept-disabled-rules` 回到 0
  （约定与 canonlint 侧「跳过必须显式授权」一致）。

## 5. 边界声明

本层证明**结构完整性**，不证明数值自洽（抽取量是否真超过剩余）。数值审计属流量层（Sprint 4–6）。AI 辅助判断将来同样只递建议条子，永不进退出码。
