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
| 七种关系字段 | 可选 | 列表 | 见 §2 |
| `x-*` | 可选 | 任意 | 扩展字段必须带 `x-` 前缀，审计器放行 |

除上表与 `x-` 前缀字段外，任何字段**必须**被审计器拒绝（CL103）。

### 1.2 引用语法

所有跨条目引用**必须**使用 `id`，禁止文件路径或标题。理由同 WGP：id 不可变，文件可移动。

## 2. 生产关系层：七种关系

**固定关系，实体开放。** 关系是语法，必须固定为本节七种；实体是词汇，用户随便定义。

七种关系全部是**有向边**，写在关系施加方的 frontmatter 里。`A 的 frontmatter 含 <relation>: [{id: B}]` 意为 `A —relation→ B`：

| 关系 | 含义 | 方向读法 | 可选属性 |
|---|---|---|---|
| `owns` | 占有 | A 占有 B（所有/占有，区别于控制：管家控制、领主占有） | `note` |
| `controls` | 控制 | A 控制 B | `note` |
| `extracts` | 抽取 | A 从 B 抽取（地租、税、剩余劳动…） | `what`（抽取物） |
| `coerces` | 暴力 | A 对 B 施加暴力/镇压 | `note` |
| `legitimizes` | 合法化 | A 给 B 合法性 | `note` |
| `owes` | 债务 | A 欠 B | `what`（债务内容） |
| `depends_on` | 供养 | A 靠 B 养（断供即崩的程度用 critical 标） | `critical`（bool）、`kind`（string，自由词汇） |

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

WGP 的 `depends_on` 要求 `kind`/`critical` 必填且 kind 六值封版；classlint 将二者降为可选、kind 改自由词汇——七层链与 kind 分族是 WGP 治理层的建模工具，classlint 的审计只关心边的存在性与方向。

## 3. 审计规则注册表

### 3.1 编号段

| 段 | 类别 |
|---|---|
| CL1xx | 结构（解析/frontmatter/schema/引用存在性） |
| PE0xx | 政治经济学规则（核心八条，本版实现 PE001–PE003） |

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
| PE003 | error | **合法性不得无锚闭环**：`legitimizes` 图的强连通分量（含自环）若没有任何来自分量外的 `legitimizes` 输入，报警。有外部锚点的互锁合法（依据：WGP v0.5 魔戒 dogfood，规范性互锁是常态） |

**无传递违规原则：** 只判直接边。A 抽取 B、B 的供养断裂并不使 A 连带违规；间接影响是将来影响报告（Sprint 3）的职责。

**判定一致性要求：** 同一仓库快照、同一协议版本，任何兼容实现的确定性判定**必须**逐条一致。

### 3.4 规则的开关

CL1xx 结构规则不可关（它们是数据 sanity 本身）。PE 规则**可以关，不能改定义**——在 `classlint.yaml` 中：

```yaml
rules:
  PE003: off    # YAML 1.1 下未加引号的 off 会解析成 false，两种写法等价
```

未知规则编号 = 配置错误（退出码 2）。规则包扩展（`rules/` 目录的 YAML 声明式规则）留待后续版本。

## 4. 退出码

- `0`：无 error（warning 不影响）；
- `1`：存在 error；
- `2`：用法/环境/配置错误。

## 5. 边界声明

本层证明**结构完整性**，不证明数值自洽（抽取量是否真超过剩余）。数值审计属流量层（Sprint 4–6）。AI 辅助判断将来同样只递建议条子，永不进退出码。
