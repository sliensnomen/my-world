# 世界观治理协议（World Governance Protocol）v1.0.1

**状态：历史规范散文（2026-09-23 冻结时的快照） ｜ 日期：2026-09-23**
**本文件的读者：协议实现者。条款用词"必须/应当/可以"为规范性词汇，含义同 RFC 2119 的 MUST/SHOULD/MAY。**

> **本文档不是权威。** 权威按此顺序：
>
> 1. `world.schema.json` —— 条目格式的唯一契约；
> 2. 代码 + 测试 —— 行为由 `tests/snapshots/` 与 `classlint/tests/` 钉死；
> 3. 本文档 —— 规则表（§6.3，**25 条**）与代码逐条互证，其余叙述是当时的意图；与代码不一致时以代码为准。
>
> 版本号只有一个来源：`canonlint.py` 的 `PROTOCOL_VERSION = "1.1"`（即 JSON 输出里的 `protocol_version`）。
> 标题里的 v1.0.1 是这份文档当年的修订号，不再表示「已冻结」的承诺——**先有工具，才有协议**。
> 下面的修订记录（v0.2 → v1.0.1）原样保留，作为当时的决策依据。

**v1.1 修订记录（2026-10，进行中；编号见上文第 12 行）：**
1. **`type` 允许 `x-` 实验类型**（§5.2 五值词表的泄压阀）：写成 `x-<命名空间>-<名称>` 即合法，能存、不判错，CA102 记 **info** 级并计入案例收集。词表本身不动——确定普适的类型进词表是收紧（§9.1），不能顺手做。放宽按 §9.1 升 minor。
2. **规范形 `relations` 与旧具名字段判定等价**：审计器把两种写法归一化到同一张边表再判定（CA108 kind、CA401/CA402/CA403/CA404/CA405 引用与状态、CA501 层级方向、CA502 环、CA503 物质族 critical、CA504 影响闭包），**同一条边写在哪、报的都一样**。此前实现只读旧字段（`depends_on`/`conflicts_with`/`canon_refs`），写成 `relations:` 会静默不判——这是实现缺口补齐。
   这条等价承诺在第一版里有个反例：规范形曾经**不强制** `kind`，而 CA501/CA502/CA503 都以 `kind` 为门禁，于是「规范形省略 `kind`」= 合法地关掉整族承重链条判定。§5.4 说的是 `depends_on` 对象的 `kind`/`critical` 必填，与写法无关，所以现在**两种写法一致**：规范形的 `depends_on` 项缺 `kind` 或 `critical` 同样报 CA107，不再跳过。
3. 契约侧字段面未变：`world.schema.json` 的 `x-contract-version` 保持 `0.2`。
4. **关系名的唯一真值表进了契约**（`x-relation-vocabulary`）：契约声明的拼法、历史拼法与规范名归一化成同一族。此前契约把 `canon_refs` 写成 `canon-ref`、`conflicts_with` 写成 `conflicts-with`，而两个引擎按规范名精确匹配——**契约自己声明的写法对判定完全隐形**（整族 CA4xx 静默失效），`depends_on` 却因两边恰好同拼法而正常体检：同一份契约三个族两种下场。现在 `canon-ref`/`canon-refs`/`canon_refs` 与 `conflicts-with`/`depends-on` 等变体一律归一到规范名再判定。
5. **CA110 拼写近失守卫**（warning，非致命）：规范形 `relations[].type` 与某个规范名编辑距离 ≤1 时提示疑似拼写错误，工具**仍按归一化后的规范名判定该边**；`x-` 前缀与真正的新关系名不报（自由档不变）。修复前 `depends-on` 一字符之差会**双向出错**：既漏判 CA501/CA401/CA504，又凭空造出 CA302/CA503（谎称作者没声明依赖）。
6. **降级级联的 `null` 语义统一**：`superseded_by: null` 是 CA101 允许的「无承接者」写法，因此 CA405（目标侧）把「字段缺」与「显式 null」当成同一件事，CA402（引用方）对两者都不报——以前填一个 `null` 就能把 CA405 关掉，且 CA402 会把 Python 的 `None` 印进报告。
7. **降级承接对豁免 CA201**：承接条目按定义要接着旧条目写，两份正文天然高度相似；`superseded_by` 声明的两方不再判疑似重复。
8. **提示性规则不阻断草稿**：CA301（命中承重墙关键词但未声明）只对**已定档**（trial/canon）条目发出——§5.3 说「审计器不替作者做决定」，而 `--strict` 会把任何 warning 变成失败；draft 写到「政治/经济」不该无法提交。
9. **`--impact` 从不把主体列进自己的下游**：`--impact x` 问的是「谁依赖 x」，环内闭包以前会把 x 自己带回列表（环由 CA502 单独报）。
10. **参数越界是用法错误**：`--dup-threshold` 必须落在 `(0, 1]`，越界返回退出码 2；以前 `2.5` 会让 CA201 永不触发而退出码仍为 0——一条规则被一个参数悄悄关掉。
11. **新增 `exchanges_with`（流通关系）**（§4.3）：表达「两条目互相提供东西」（分工/互市/贸易），形状与 `conflicts_with` 同构。它**不进** CA501/CA502/CA503/CA504 的承重图，因此互相交换在模型里合法；要表达「互相供养、谁断谁塌」仍写两条 `depends_on`（照报 CA502）。补这个缺口是因为以前**没有表达交换的合法写法**：互市只能写成两条 `depends_on`，被判成永动机，作者要么改模型要么关规则。
12. **关系名有了定义**（§4.4）：契约 `x-relation-vocabulary` 的每个名字都带 `means`（这个关系是什么意思、哪些规则用它），并把「**物质依赖**」写死为 `depends_on` 的 `kind` ∈ {resource, production, economy, fiscal, manpower}——受 CA501/CA502/CA503 约束；`x-` 实验值是规范依赖，三条规则豁免（第 15 条把这个缺口彻底补齐：名分依据搬出去之后，类别表只剩 `x-strict-vocabulary.depends_on.kind` 一份）。此前关系名只有拼法没有定义，作者按直觉选词、工具按名字建图，双方对「这条边算不算承重」没有共识。`tests/test_store.py` 现在钉住「每个关系名必须有 `means`」与「物质族只有一份真值」。
13. **关掉规则必须落在退出码上**（classlint §4）：`rules: {PE00x: off}` 时 `check` 返回 **3**（判定通过，但通过的是少了几条规则的机器），只有显式 `--accept-disabled-rules` 才回到 0；`--json` 增 `judgement_complete`。以前这只看摘要行一句附注，退出码与全规则通过完全相同。
14. **PE005 的消音必须是一次物质关系声明**（classlint §3.2）：来源侧边只认 `extracts`、`exchanges_with`、或带物质类别 `kind` 的 `depends_on`。以前一条任意出边即消音，`depends_on: [weather]` 一行就能让「被抽取者的再生产不可见」消失——自然条件不是生产关系，也不承担再生产，消音门槛低到等于没有门槛。相关夹具已补上 `kind`。
15. **拆开 `depends_on`：名分依据成为独立关系名 `derives_legitimacy_from`**（§4.4/§4.5）。一个关系名曾经装两种意思——「我靠它活着」与「我的说法以它为依据」——而 CA501/CA502/CA503 的门禁恰好是 `kind`：于是副标签决定了「算不算承重」，`legitimacy` 还和物资挤在同一张类别表里，漏填或拼错 `kind` 就能合法关掉整族判定；反过来 `kind` 也不再是纯粹的类别标签。现在门禁看**关系名**，`kind` 只回答「靠哪一类物资」。旧写法 `depends_on` + `kind: legitimacy` 继续接受：存储层按契约 `deprecations` 归一成新关系名（判定与迁移后逐条相同），另记一条 CA111 warning 提示改写。`tests/test_store.py` 钉住「每个关系名必须有 `means`」与「`kind` 词表只有一份真值」，`classlint/tests/` 钉住两种写法同判。

16. **每一种关系的悬空引用都报 CA401**（§6.3）：`own`/`control`/`extract`/`coerce`/`legitimize`/`owes` 六种字段的语义虽归 classlint 那一层，但从前 canonlint 一条都不查——`owns: [幽灵]` 在本层完全隐形，只有跑 classlint 才有 CL105。规则归属不改变「引用指向不存在的 id 是结构问题」，现在本层对契约列过的每一种关系都查存在性（照旧**不**给生产关系附加状态语义：依据草稿、交换对象降级都不构成违规）。`tests/run_tests.py` 钉住五种关系 × 两种写法都要报、目标存在时不报。

17. **`owes` 有了判语：债务必须收得回来**（classlint PE009，见 `classlint/PROTOCOL.md` §3.3）：存在 `A —owes→ B` 时，模型里必须有收账通道——债主对债务人的支配（`controls`/`coerces`/`extracts`/`legitimizes` 任一条），或债务人依赖债主（`depends_on`）。两条都没有就报 warning：那样的 `owes` 只是一句记账，模型里没有能兑现它的结构。此前 `owes` 有词表、有形状、有定义，却没有一条规则用它——契约自己写着「本版 PE 规则还没用它下判语」，这是已知缺口。编号取 **PE009** 而不是 PE006：`classlint` 规划里的 PE006–PE008 属流量层（剩余量/人口/交叉），编号即协议，不占用已规划的空位。

**v1.0.1 澄清（不改语义，只消歧义）：**
- `superseded_by`：archived 必填（无承接者填 null）；其他状态**可以省略或填 null**（模板统一写入合法）
- §6.5 JSON schema 的 `entry` 字段允许伪值 `"(仓库级)"`，用于 CA505 等仓库级 finding
- 目录约定明确：`entries/{type}/` 是唯一条目位置，目录纯组织、状态只认 frontmatter；`canon/`、`sandbox/`、`archive/` 仅为兼容旧仓库的扫描路径，新仓库不使用

**v1.0 封版记录（三个测试世界 dogfood 完成）：**
1. **kind 初始集封版**：六值冻结（resource/production/economy/fiscal/manpower/legitimacy）。证据：魔戒、冰与火、沙丘三个差异极大的世界中，物质五值零例外；装不下的全部落在规范族（`x-will-binding`、`x-magic-logistics`、`x-faith-engineering` 各出现一次，证据不足以升格，留档观察）
2. **`x-` 实验通道永久开放**：不作为过渡机制，作为协议的长期泄压阀（CA108 info 级收集）
3. 一致性终审完成：规则表 23 条（CA100–CA109、CA201、CA301/302、CA401–CA405、CA501–CA505）与参考实现逐条互证（v1.1 增列 CA110、CA111，见 §6.3 与 §9 修订记录）；清除死代码（v0.4 的 CA503 旧阈值常量）
4. 自本版起，结构性变更走 major 版本（§9）

**v0.5 修订记录（魔戒/冰火真实数据 dogfood 回流）：**
1. **kind 分族**：物质五 kind（resource/production/economy/fiscal/manpower）受层级方向约束；legitimacy 与 `x-` 实验 kind 属**规范流**——合法性、强制力、超自然力自上而下流动，豁免 CA501。依据：洛汗誓言→封邑征召、索伦意志→魔多大军、异鬼魔法→尸鬼军团三个真实案例
2. CA502 环检测只在物质子图上运行（规范性互锁如"魔戒↔索伦支配"是常态不是永动机）
3. CA503 收窄：economy/fiscal/military/political 层承重墙须有**物质类** critical 依赖；ideology 层豁免（规范节点不吃物质饭）
4. 新增 CA505（仓库级 warning）：存在 military/political 承重墙条目但全库无 fiscal 层条目 = 财政维度缺失提示（依据：刚铎全书无财政记载，v0.4 规则未能检出）
5. 建模纪律入规范：`depends_on` 只表达"供养/断供即崩"，**不表达主题相关**（依据：瑟曦违约案误连）

**v0.4 修订记录（实现首轮代码评审回流）：**
1. 新增 CA109（字段类型/格式非法）：`canon_refs` 非列表、元素非合法 id 字符串、`load_bearing`/`ai_assisted` 非 bool 等，统一归此规则
2. CA402/CA405 去重：CA402 只管 draft/trial 目标；archived 目标由 CA405 系列接管——`superseded_by` 缺失报 CA405（报在 archived 条目侧），已填则报 CA402 提示迁移（报在引用方侧），同一问题不再双报
3. `conflicts_with` 目标状态明确**不设约束**（提案挑战已定档是常态）
4. CA403 措辞收紧：stance 豁免以"这对矛盾关系"为单位判定
5. `superseded_by` 引用目标纳入 CA401 存在性检查

**v0.3 修订记录（附录 B 五条待决问题全部裁决）：**
1. `depends_on.kind` **不封版**：六值降为"初始集"，实验值允许 `x-` 前缀（如 `x-faith`）；启动 3–5 个真实世界观的供应链标注案例收集计划，集满再定封版（附录 B）
2. 权限维持不入协议；新增**审计中立性条款**（§6.2）：权限信息不得写入 frontmatter，不得以任何形式影响确定性判定
3. `conflicts_with` 默认对称；新增可选 `stance` 字段（official/heretic/unknown），CA403 相应放宽（§4）
4. 跨仓库引用语法 `world:id` 本版保留不实现；实现遇到**必须**报 CA401，禁止静默忽略（§2.3）
5. 恢复路径：默认 `archived → trial → canon`；直接恢复 `archived → canon` 及冷却期/次数上限交由仓库宪章声明，协议不硬规定（§3.2/3.3）

**v0.2 修订记录（首轮评审，10 项）：** 降级级联（superseded_by + CA405）；archived 非终态；承重墙显式声明（load_bearing + CA302）；CA402/CA404 合并与无传递违规原则；depends_on schema（CA107）；链条序号取代"更高层级"表述；CA504 定级与 JSON 输出 schema；中文预处理算法（§6.5）；AI 条款产出/辅助边界；兼容读取措辞收紧。

---

## 1. 范围与地位

本协议定义一套用于多人共创世界的**治理数据模型与确定性审计规则集**：

- 条目格式（frontmatter 规范）；
- Canon 状态机（条目的生命周期）；
- 引用、矛盾、流通标注与名分依据（`canon_refs` / `conflicts_with` / `depends_on` / `exchanges_with` / `derives_legitimacy_from`）；
- 审计规则注册表（CA 编号规则集）。

本协议**不规定**：存储后端（git、数据库、纯文件皆可）、编辑界面、发布形式、AI 实现细节、权限模型。

**定位声明（2026-10 修订）：先有工具，才有协议。** 本文档是工具行为的描述与当时的意图记录，规则以代码与测试为准。
协议真正的用处不在"它是产品"，而在**它是可被第二份实现照做的清单**——没有第二份实现之前，"冻结"只是一个人的承诺。
`world.schema.json` 取代了本文档作为格式权威的地位，因为它能被机器验证，所以不会撒谎。

---

## 2. 基本数据模型

### 2.1 条目（Entry）

条目是世界的最小治理单元。**一个条目 = 一个 UTF-8 Markdown 文件**，由 YAML frontmatter 头与正文组成：

```markdown
---
id: gray-harbor
title: 灰港
type: location
author: 署名
date: 2026-10-05
status: canon
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---

正文。200–500 字起步。
```

### 2.2 frontmatter 字段表

| 字段 | 必填 | 类型 | 约束 |
|---|---|---|---|
| `id` | **必须** | string | 全库唯一；小写字母/数字/连字符；**一旦发布永不更改、永不复用** |
| `title` | 必须 | string | 显示名，可含任意字符 |
| `type` | 必须 | enum | `location` / `faction` / `character` / `event` / `item`；`x-<命名空间>-<名称>`（如 `x-wgp-religion`）为实验类型：能存、不判错，CA102 记 info（协议 1.1 起，与 `kind` 的泄压阀同一套） |
| `author` | 必须 | string | 实名/笔名皆可；实名映射表属实现细节，不入协议 |
| `date` | 必须 | date | ISO 8601（YYYY-MM-DD），首次创建日期 |
| `status` | 必须 | enum | 见 §3 状态机 |
| `load_bearing` | 必须 | bool | `true` = 显式声明为承重墙条目，触发 §5 全部义务 |
| `canon_refs` | 必须 | id 列表 | 本条目语义依赖的已定档条目，可以为空列表 |
| `conflicts_with` | 必须 | 列表 | 元素为 id 或对象（§4.1），可以为空列表 |
| `exchanges_with` | 可选 | 列表 | 元素为 id 或对象（`{id, what?}`）；**流通**关系，不参与承重判定（§4.3） |
| `derives_legitimacy_from` | 可选 | 列表 | 元素为 id 或对象（`{id, critical?, note?}`）；**名分依据**（§4.5）。与旧写法 `B legitimizes A` 同义（方向相反），判定完全一致；不进承重图，只查存在性 |
| `depends_on` | 条件必填 | 对象列表 | 见 §5.3 schema；`load_bearing: true` 时必填 |
| `layer` | 条件必填 | enum | 见 §5.2；`load_bearing: true` 时必填 |
| `superseded_by` | 条件必填 | id 或 null | 见 §3.4；`archived` 必填，其他状态可省略或填 null |
| `ai_assisted` | 必须 | bool | 见 §7 AI 条款 |

**扩展字段：** 实现可以添加任何 `x-` 前缀的自定义字段；不带前缀的未定义字段**必须**被审计器拒绝（CA106），防止私有字段渗透进协议。

### 2.3 引用语法

所有跨条目引用（`canon_refs` / `conflicts_with` / `exchanges_with[].id` / `derives_legitimacy_from[].id` / `depends_on[].id` / `superseded_by`）**必须**使用 `id`，**禁止**使用文件路径或标题。

理由：`id` 不可变，文件可以移动、重命名、换目录而不炸任何引用。文件路径是存储细节，不是身份。

实现应当提供 `id → 文件` 的索引构建；索引是缓存，不是数据。

**跨仓库引用（保留）：** 形如 `world:id`（含命名空间前缀）的引用为将来跨世界引用预留的语法。本版**不实现**。审计器遇到此类引用**必须**报 CA401（未支持的引用形式），**禁止**静默忽略或按本地 id 侥幸匹配。

---

## 3. Canon 状态机

### 3.1 状态定义

| 状态 | 定义 | 谁能动 | 进入条件 |
|---|---|---|---|
| `draft` | 提案档：未跑过、未审过 | 作者本人 | 创建即 draft |
| `trial` | 试水档：跑过/讨论过，未定论 | 作者 + 桌面现场 | 经一场桌或一次共创会 |
| `canon` | 已定档：主干强一致 | 仅升格评审 | 评审通过（理由必须引用宪章条款） |
| `archived` | 标灰封存（**非终态**） | 仅评审 | 降级裁决，或恢复程序的出发点 |

### 3.2 合法迁移

```
draft → trial → canon → archived
                  archived → trial    （默认恢复路径，重走升格）
                  archived → canon    （快速通道，须宪章声明，见 3.3）
```

- **升格** `draft → trial → canon`：不许跳级。
- **降级** `canon → archived`：唯一降级路径。不存在 `canon → trial`——"降回试水档"的意图通过 `archived` + 恢复程序实现。**降级不删稿。**
- **恢复**：一切恢复**必须**走评审。默认路径为 `archived → trial → canon`（与升格同标准，理由引用宪章条款）。

### 3.3 恢复快速通道与上诉期

仓库宪章**可以**声明：

- 允许 `archived → canon` 直接恢复（快速通道）；
- 恢复/上诉的冷却期与次数上限。

宪章未声明时，一律走默认路径 `archived → trial → canon`，且不设冷却期与次数上限。**协议不硬规定程序参数，把它们留给各世界的宪章——治理密度是地方事务。**

降级裁决后设 72 小时上诉期（建议值，宪章可改）。上诉期是**程序性概念**，由宪章和协作流程执行，**不进入数据模型**——lint 不感知时间。

### 3.4 降级的级联处置（消灭"stale 引用"）

降级一条 `canon` 条目会使其所有下游的 `canon_refs` 立即违反 CA402。为消除协议死锁，降级裁决**必须**附带处置方案：

1. 评审执行降级时，**必须**在 `archived` 条目上填写 `superseded_by`，指向承接其地位的条目（可以是新条目或既有条目）；确无承接者时填 `null` 并在裁决理由中说明。
2. 降级的同时，评审**必须**生成 CA504 影响报告，列出该条目的全部下游依赖者，作为待复核工单。
3. 下游条目在工单关闭前处于"已知违规"状态——CA402 照报 error，**协议不提供豁免**。违规必须在工单中实质性解决（改指向 `superseded_by` 目标、或修改正文消除依赖），不允许"标记 stale 后放着不管"。

设计理由：stale 标记是债务的合法化，与本协议"降级不删稿但也不留暗账"的立场冲突。允许的唯一缓冲是工单本身，不是数据里的豁免位。

---

## 4. 矛盾标注（矛盾合法化）

**核心条款：** 矛盾不是错误，是数据。裁决不是选一边，而是标注矛盾、两条分支都保留（"Everything is canon, but not everything is true"）。

### 4.1 标注形式

`conflicts_with` 的元素可以是：

```yaml
conflicts_with:
  - other-entry-id                     # 简式：纯 id，对称义务生效
  - id: official-record                # 带 stance 的对象式
    stance: heretic                    # 本条目自认的叙事地位
```

`stance` 三值，**描述本条目自认的世界内叙事地位**：

| stance | 含义 |
|---|---|
| `official` | 本条目代表主流/官方叙事 |
| `heretic` | 本条目为异端/边缘/被压制叙事 |
| `unknown` | 地位未定（默认） |

### 4.2 规则

1. 矛盾不阻塞任何状态迁移：`canon` 条目之间允许存在 `conflicts_with` 边。
2. 矛盾条目在世界内解释为不可靠叙述（地区差异/阵营宣传/纪年错位）。**翻译优先**：能世界内解释的不许动刀。
3. **对称义务的放宽：** 双方均用简式标注时，互指为义务，缺失回指报 CA403 warning；**本关系的任何一端使用对象式（带 `stance`）时，视为有意的不对称，CA403 不报**——异端叙事本就常常没有官方的回指。"本关系的一端"仅指这对矛盾双方指向对方的这两条边，与各自对其他条目的标注形式无关。
4. 强弱语义（谁先被相信）由呈现层依据 `stance` 渲染，协议只保证标注存在。
5. `conflicts_with` 的目标状态**不设约束**：可以指向任何状态的条目——提案挑战已定档、已定档与待定档互相矛盾，都是常态，不是违规。

### 4.3 流通标注（`exchanges_with`，v1.1 新增）

`exchanges_with` 表示**两条目互相提供东西**——分工、互市、贸易、朝贡往来。它的形状与
`conflicts_with` 同构（id 或 `{id, what?}`），但它说的是**流通**，不是**承重**：

- 交换不进入承重判定的任何一张图：CA501（层级方向）、CA502（物质族成环）、CA503（承重墙
  须有物质来源）都不看它，CA504 的影响闭包也不走它。
- 因此「A 与 B 互相交换」在模型里**合法**，不会被判成永动机。要表达「A 与 B 互相供养、
  谁断了谁都塌」，仍然写两条 `depends_on`——那**应当**报 CA502 的物质族成环，因为那个环里
  确实没有外部底座。
- 目标存在性照查（CA401）；目标状态不设约束（与 `conflicts_with` 同口径，交换对象降级
  不构成违规）。

这条关系是补上一个真实缺口：**以前没有表达「交换」的合法写法**，于是互相交换的两个条目
只能写成两条 `depends_on`，被判成永动机；作者要么改模型、要么关规则。判词是「这个环里没有
外部底座」，而交换本来就不声称有底座——关系名错了，不是世界错了。

### 4.4 关系名与定义（唯一真值表在契约）

关系名、可接受的拼法变体、以及**每一条关系的定义（`means`）**都写在
`world.schema.json` 的 `x-relation-vocabulary` 里，两个引擎读同一份。本文档不再复述定义，
以免出现第二份会过期的说法。

**「物质依赖」的定义**（契约 `x-strict-vocabulary.depends_on.kind`，词表只有一份）：`depends_on`
的 `kind` 落在 `resource` / `production` / `economy` / `fiscal` / `manpower` 五值时，依赖的是
**要被人生产出来、会耗尽、能断供**的东西，受 §5 三条规则约束；`x-` 实验值是**规范依赖**
（依赖的是说法/名分，不是物资），三条规则豁免——豁免不等于无意义，只是这三条判不了它。

v1.1 起，名分依据**不再借用 `depends_on` 的 `kind`**（§4.5）：它有了自己的关系名，
所以「算不算承重」由**关系名**决定，`kind` 只回答「靠哪一类物资」。这条拆分消灭了旧写法里
一个真实的合法绕过口——`kind` 曾经既是类别标签又是承重门禁，拼错或省略就能悄悄关掉整族判定。

### 4.5 名分依据（`derives_legitimacy_from`，v1.1 新增）

`A derives_legitimacy_from B` 表示「A 的说法以 B 为依据」——王权来自神授、产权来自惯例、
命令来自授权。它与旧写法 `B legitimizes A` 是**同一句话**，方向相反：两个引擎都把前者
翻译成后者再进图（classlint 的 `legitimizes` 图），因此：

- **判定完全一致**：同一个闭环、同一个外部锚点、同一条报在哪一侧，两种写法逐条相同。
  `tests/world-*` 与 `classlint/tests/legit-canonical-*` 夹具守着这条。
- **不进任何承重图**：CA501 / CA502 / CA503 / CA504 都不看它。名分来源断了是叙事问题，
  不是供应链断裂。
- **只查存在性**（CA401）：目标条目必须存在；目标**状态**不参与判定（与 `conflicts_with`、
  `exchanges_with` 同口径）——来源条目归档不等于这个说法失效，所以既不报 CA402 也不报 CA405。
- **它不冒充生产关系**：classlint 的 PE001 / PE004 / PE005（抽取/供给）不看它；PE003
  （合法性闭环）看它，这正是它存在的意义。

**旧写法兼容**：`depends_on` + `kind: legitimacy` 仍然被接受，存储层按契约
`x-relation-vocabulary.deprecations` 把它归一成这个关系名，**判定结果与迁移后逐条相同**；
同时记一条 CA111 warning 提示作者改写。废弃不静默，也不让旧数据变成错误。

---

## 5. 政治经济学链条（承重墙的结构化约束）

### 5.1 动机

设定的多数矛盾不是文本互斥，而是**供应链断裂**（贫穷农业国养十万常备军）。本协议将政治经济学的层叠模型编码为可机器检查的推导链，使此类矛盾从语义问题降格为图论问题。

### 5.2 层级字典（协议常量，八层，刻意最小）

```
geo → resource → production → economy → fiscal → military → political → ideology
```

每层有确定的**链条序号**（geo=0 … ideology=7）。字典的扩展走协议变更程序（§9），实现**不得**私增层级。

### 5.3 承重墙条目的义务

承重墙身份由 `load_bearing: true` **显式声明**，声明即承担全部义务：

| 义务 | 缺失后果 |
|---|---|
| 填 `layer` | CA302 **error** |
| **声明**依赖（见下表） | CA302 **error** |

CA302 判的是「有没有声明」，不是「有没有边」——所以下面这些写法**判定结果必须相同**。
「对依赖什么都没说」与「声明了没有依赖」是两件事：

| 写法 | 声明了吗 | CA302 |
|---|---|---|
| 什么都没写 | 否 | **error** |
| `depends_on: []`（字段在） | 是（空） | — |
| `relations: []`（规范形整表为空） | 是（空） | — |
| `relations:` 里只有别的边（如一条 `conflicts-with`） | 否 | **error** |
| 只写 `conflicts_with:`、没碰依赖 | 否 | **error** |
| `relations:` 放别的边 + `depends_on: []`（混用） | 是（空） | — |
| `relations:` 里有一条 `depends_on` 边 | 是 | — |

规范形是一张混装的关系表，没有单独的「空 `depends_on`」条目，所以「空依赖 + 别的边」
只有混用写法能表达：`relations:` 放别的边、`depends_on: []` 显式声明空。混用是**契约支持**
的写法（`world.schema.json` 的 `x-relation-source.written-form`），不是将就。

仅命中附录 A 关键词但未声明 `load_bearing` 的条目，CA301 发出 **warning**（提示作者考虑声明）。"必须"只落在显式声明上，审计器不替作者做决定。

### 5.4 `depends_on` 对象 schema（kind 已封版，v1.0）

每个元素**必须**恰好包含以下三个必填字段，可以加 `x-` 扩展字段。**这条对两种写法同样成立**：旧具名字段 `depends_on:` 的元素按 `id`/`kind`/`critical`，规范形 `relations:` 里的 `depends_on` 项按 `target`/`kind`/`critical`——缺一个就报 CA107，两条路径都不跳过，否则「规范形省掉 `kind`」就能合法地关掉 CA501/CA502/CA503（见 §9 v1.1 修订记录第 2 条）。

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | id 引用 | 必填 |
| `kind` | string | 必填。**五值初始集**：`resource` / `production` / `economy` / `fiscal` / `manpower`（哪一类物资）；集外仅允许 `x-` 前缀实验值（如 `x-faith`），作为协议的长期泄压阀，CA108 info 级收集证据。v1.1 起 `legitimacy` **不再是 kind 值**——名分依据是关系名（§4.5） |
| `critical` | bool | 必填；`true` = 断供即崩塌 |

缺字段、多字段（非 `x-`）= CA107 error；`kind` 在初始集外且无 `x-` 前缀 = CA108 error，有 `x-` 前缀 = CA108 info 级提示（计入案例收集）。

**kind 分族（v0.5 起）：** 初始集六值分为两族——

- **物质族** `resource` / `production` / `economy` / `fiscal` / `manpower`：自下而上流动，受 CA501 层级方向约束与 CA502 环检测；
- **规范族** `legitimacy` 与一切 `x-` 实验 kind：自上而下流动（合法性、强制力、超自然力），豁免 CA501，不参与 CA502。

`depends_on` 只表达**供养关系**（断供即崩），**不得**用来表达"主题相关"（那用 `canon_refs` 或正文叙述）。

**两种写法，判定等价（v1.1）：** 关系可以写成旧具名字段（`depends_on:` / `conflicts_with:` / `canon_refs:` / `exchanges_with:` + classlint 的关系字段），也可以写成规范形 `relations:`（形状见 `world.schema.json` 的 `x-relation-source`）。审计器把两种写法归一化到同一张边表（`Entry.relations`）之后再判定——**同一条边，写在哪，报的都一样**，§5.4 的 `kind`/`critical` 必填对两条路径同样成立。

剩下的唯一差异在**未知 `type` 值**上：规范形里未知的 `type` 原样保留、不下判语（自由档允许用户自定义关系名，见 §4.4），但**与任一规范名编辑距离 ≤1** 的值会记一条 CA110 warning（拼写近失守卫）——`depends-onn` 这类手滑既不能静默漏判，也不能凭空造出别的结论（v1.1 修订记录第 5 条）。

### 5.5 链条合法性

**先看适用对象（工具行为，照此实现才逐条一致）：** 下面第一条（CA501）与第三条（CA503）**只检查
`load_bearing: true` 的条目**；第二条（CA502）在**全部条目**的物质族子图上跑；第四条（CA505）是仓库级。
也就是说：**没声明承重墙的条目不会被链条规则打扰**——声明承重墙才是承担义务的方式（§5.3）。

- **物质族** `depends_on` 目标的 `layer` 链条序号**必须 ≤** 本条目 `layer` 的链条序号；**同层依赖允许**。违反 = CA501 error。规范族边不做方向检查。**仅对承重墙条目检查。**
- **物质族**依赖子图**必须**无环（A 养 B、B 养 A = 永动机）。违反 = CA502 error。规范族互锁（如"魔戒↔支配者"）合法。**对全部条目检查**（环不分承重墙）。
- `layer` 为 economy/fiscal/military/political（序号 3–6）的承重墙条目，若 `depends_on` 中没有任何**物质族** `critical: true` 依赖，CA503 发出 warning（空中楼阁提示）。ideology 层豁免——规范节点不吃物质饭。
- **仓库级检查 CA505（warning）：** 全库存在 military/political 层承重墙条目，但没有任何 `layer: fiscal` 的条目（不要求是承重墙）时，提示财政维度可能缺失（刚铎型盲区：帝国养兵而全库无账）。
- 目标状态约束见 CA404（§6.3）。

### 5.6 变更影响报告

审计器**必须**（兼容治理级，见 §8）提供：给定条目变更或降级时，输出其 `depends_on` 反向传递闭包（全部下游依赖者）作为待复核队列。这使"改 A 炸 B"从事故变为工单。

### 5.7 边界声明

链条证明**结构完整性**，不证明**数值自洽**（关税收入是否真养得起舰队）。数值/合理性验算属 AI 审计层（CA9xx）与人工裁决，不在确定性规则范围内。

---

## 6. 审计规则注册表

### 6.1 编号段

| 段 | 类别 | 性质 |
|---|---|---|
| CA1xx | 结构（frontmatter/解析/schema） | 确定性 |
| CA2xx | 内容（查重/篇幅） | 确定性 |
| CA3xx | 承重墙触发 | 确定性 |
| CA4xx | 引用与状态机 | 确定性 |
| CA5xx | 政治经济学链条 | 确定性 |
| CA9xx | AI 语义审计 | **建议性，永不进退出码** |

### 6.2 审计中立性条款

**权限信息不进入数据模型。** 条目的 frontmatter（含 `x-` 扩展字段）**不得**携带权限、角色、治理身份等信息；实现**不得**让任何 frontmatter 字段改变确定性规则的判定结果。同一仓库快照喂给任何兼容实现，确定性判定必须逐条一致——作者是创始人还是路人，不影响 lint 的嘴。

权限模型（谁能动 `canon/main/`、评审组构成）属 forge/CI 层与各世界宪章，见附录 B 第 2 条裁决。

### 6.3 确定性规则定义

| 编号 | 级别 | 定义 |
|---|---|---|
| CA100 | error | 文件无法解析（无 frontmatter / YAML 错误 / 非映射） |
| CA101 | error | 缺少必填字段（按 §2.2，含条件必填） |
| CA102 | error | 枚举字段非法（`type`/`status`/`layer`/`stance`）；`type` 是 `x-` 实验类型时降为 info（协议 1.1） |
| CA103 | error | `date` 非合法 ISO 日期。**两种形态都收**：YAML 原生日期对象（`date: 2026-10-15` 没加引号时会被 YAML 解成 `datetime.date`）与契约要求的 ISO 字符串（`"2026-10-15"`）。工具自己写出的卡是字符串形态 |
| CA104 | warning | `trial`/`canon` 条目正文少于 200 字（计数算法见 §6.6） |
| CA105 | error | `id` 重复，或含小写字母/数字/连字符以外字符。重复时按路径序首个入索引：别人引用这个 id 时指的是前者，**被遮蔽那一份自己的出边照旧检查**（它没进索引不等于没写错） |
| CA106 | error | 存在不带 `x-` 前缀的未定义字段 |
| CA107 | error | `depends_on` 对象违反 §5.4 schema（缺字段/多非 x- 字段） |
| CA108 | error/info | `depends_on[].kind` 在初始集外：无 `x-` 前缀 = error；有 `x-` 前缀 = info（案例收集） |
| CA109 | error | 字段类型/格式非法：`canon_refs` 非列表或元素非字符串、`load_bearing`/`ai_assisted`/`critical` 非 bool、id 引用不符合 `^[a-z0-9-]+$` 格式（`world:id` 形式除外，归 CA401）等 |
| CA110 | warning | 关系名拼写近失：规范形 `relations[].type` 与某个规范关系名的编辑距离 ≤1（如 `depends-onn`）。工具仍按**规范名**判定该边，本条只提示疑似拼写错误；真正的新关系名不报（自由档，见 §5.4） |
| CA111 | warning | 旧写法迁移提示：某个关系名拆分前用「旧关系名 + 某个注解值」表达（见契约 `x-relation-vocabulary.deprecations`）。工具**已按新关系名判定**（结论与迁移后逐条相同），本条只提示作者改写，例如把 `depends_on` 里 `kind: legitimacy` 的那一条改写成关系名 `derives_legitimacy_from`。这是唯一允许的迁移提示；迁移完成后本条不再触发 |
| CA201 | warning | 两条目正文相似度 ≥ 阈值（默认 0.85；预处理与最短长度见 §6.6）。**降级承接对豁免**：`superseded_by` 声明的两方相似是要求的，不是疑似重复 |
| CA301 | warning | 命中附录 A 关键词但 `load_bearing` 非 `true`（提示考虑声明）。**只对已定档条目（trial/canon）发出**：draft 还没到做决定的时候，而 `--strict` 会把 warning 当失败 |
| CA302 | error | `load_bearing: true` 但缺 `layer` 或 `depends_on` |
| CA401 | error | 引用指向不存在的 `id`；或引用为 `world:id` 形式（本版未支持，**禁止静默忽略**）。**覆盖契约列过的每一种关系**：`canon_refs`/`conflicts_with`/`depends_on`/`exchanges_with`/`derives_legitimacy_from`/`superseded_by`，以及语义归 classlint 那一层管的生产关系 `owns`/`controls`/`extracts`/`coerces`/`legitimizes`/`owes`。规则归属不改变一件事：指向不存在的 id 是结构问题，判定层不许看不见它 |
| CA402 | error | `canon_refs` 目标状态为 `draft`/`trial`；或目标为 `archived` 且已填 `superseded_by`（提示迁移至承接条目）。目标为 `archived` 且未填 `superseded_by` 时**不报本条**，由 CA405 在 archived 条目侧单独报告，避免双报 |
| CA403 | warning | `conflicts_with` 双方均简式且缺回指（对象式标注豁免，见 §4.2） |
| CA404 | error | `canon` 条目的 `depends_on` 目标状态非 `canon`（链条依赖只能建立在已定档上） |
| CA405 | error | `archived` 条目仍被 `canon_refs` 引用，且 `superseded_by` **未填或为 `null`**（两者都表示「没有承接者」，见 v1.0.1 澄清）——降级处置不完整 |
| CA501 | error | **物质族** `depends_on` 目标的链条序号 > 本条目的链条序号（规范族边豁免） |
| CA502 | error | **物质族**依赖子图存在环 |
| CA503 | warning | economy/fiscal/military/political 层承重墙条目无任何**物质族** `critical: true` 依赖（ideology 层豁免） |
| CA505 | warning | 仓库级：存在 military/political 层承重墙条目，但全库没有任何 `layer: fiscal` 的条目（财政维度缺失提示；条目不须为承重墙） |
| CA504 | report | 变更/降级影响报告：输出变更条目的下游传递闭包（**不含主体自身**——`--impact x` 问的是「谁依赖 x」，环由 CA502 单独报） |

**无传递违规原则：** CA402/CA404/CA405 只判**直接边**的违规。A 引用 B、B 违规并不使 A 连带违规；"连带影响"是 CA504 报告的职责，不是 error 的传染。

**三张依赖图（同一份 frontmatter，三条规则读的子图各不相同，必须分别记）：**

- **CA501 / CA503**（承重链条规则）：只读该条目**自身**的 `depends_on` 边。CA501 按 `kind` 判层级方向（落物资五类才判）；CA503 数物资类里 `critical: true` 的有几条。两者都以 `load_bearing: true` 为门禁。名分依据（`derives_legitimacy_from`）不在这张图里。
- **CA502**（物质族成环）：读全库 `depends_on` 边的**物质族子图**（目标条目必须存在）。只看 `kind` 是否落在物质族；不看 `load_bearing`，也不看层。
- **CA504**（影响闭包）：读全库 `depends_on` 边的**全图**并做传递闭包。都不看：任何 `depends_on` 边都算下游，连 `kind` 缺失的也算。

所以"环"（CA502）与"影响闭包"（CA504）在**同一份数据上可以给出不同的下游集合**，这不是 bug 而是分工：CA502 只关心物质生产能否自我循环，CA504 关心改名/降级会波及谁。承重墙声明（`load_bearing: true`）是 CA501/CA503 的门禁，对 CA502/CA504 不产生影响。**这三张图是契约的一部分**，兼容实现必须按同一张表建图，否则一致性要求（上一段）无法满足。

**判定一致性要求：** 同一仓库快照、同一规则集版本，任何兼容实现的确定性规则判定**必须**逐条一致。判定出现分歧 = 某实现有 bug 或协议有歧义，两者都必须修。

### 6.4 退出码约定

- `0`：无 error（warning/info/report 不影响）；
- `1`：存在 error；
- `--strict` 模式下 warning 也使退出码为 1（pre-commit 等场景使用）；
- `2`：用法/环境错误（参数越界、扩展包缺失、**指错目录**——给一个既没有 `entries/`、根目录里也没有一篇带 frontmatter 的条目卡的地方，会被直说「不像一个世界仓库」，而不是把每篇文档都当成坏条目报几百条假错误）；
- **CA504 与 CA9xx 永不参与退出码。**

### 6.5 机器可读输出（JSON）

兼容审计级实现**必须**支持 JSON 输出，schema 如下（此 schema 封版，扩展走 `x-` 字段）：

```json
{
  "protocol_version": "1.0",
  "entries": 12,
  "findings": [
    {"rule": "CA402", "level": "error", "entry": "gray-harbor-fleet",
     "message": "canon_refs 目标 'old-tax-law' 状态为 archived"}
  ],
  "reports": [
    {"rule": "CA504", "subject": "old-tax-law",
     "downstream": ["gray-harbor-fleet", "harbor-guard-payroll"]}
  ]
}
```

`reports` 数组仅兼容治理级必须输出；`downstream` 为 `depends_on` 反向传递闭包的 `id` 列表，按链条序号降序排列（越靠后的越先复核）。

`findings[].entry` 通常是被判条目的 id 或路径；仓库级 finding（如 CA505）使用伪值 `"(仓库级)"`。

### 6.6 中文文本预处理（CA104/CA201 的计数与比较算法）

为避免中文与 Markdown 造成的误报，计数与相似度比较前**必须**执行同一预处理：

1. 剥除 frontmatter；
2. 剥除 fenced code block（``` 包围段）与 HTML 注释；
3. 剥除全部空白字符与 Unicode 标点（`P*` 类别）。

**正文长度** = 预处理后剩余字符数（每个 CJK 字符计 1）。
**相似度** = 预处理后文本的 `difflib.SequenceMatcher.ratio()`；参与比较的两条文本均须 ≥ 100 字符，否则该对跳过 CA201（短文本相似度无意义）。

### 6.7 AI 规则段（CA9xx）

实现可以自由发明 CA9xx 规则（语义冲突检测、数值验算、文风检查），但输出**只能**是建议，**禁止**影响退出码，**禁止**作为升格/降级的唯一依据。理由：模型版本漂移不得污染可复现的协议判定。

---

## 7. AI 条款

1. **AI 产出**（未经自然人实质性重写的生成内容）**永不**进入 `canon` 状态。
2. 任何在创作过程中使用过 AI 的条目，`ai_assisted` 必须标 `true`，该标注**永久保留**，不因后续人工修改而移除。
3. AI 辅助 + 自然人实质性重写并署名负责的条目，**可以**升格 `canon`——签字人即内容责任人，AI 不留责任位。
4. 世界主权在人：升格、降级、恢复、矛盾裁决的最终签字权必须是自然人。

---

## 8. 实现一致性分级

| 级 | 要求 |
|---|---|
| **兼容读取** | 能解析全部字段；**不丢失任何字段，包括 `x-` 扩展字段**（读取-写回往返无损） |
| **兼容审计** | 通过 §6.3 全部确定性规则（CA504 除外），判定与参考实现逐条一致；支持 §6.5 JSON 输出（可不含 `reports`） |
| **兼容治理** | 额外实现状态机迁移控制与 CA504 影响报告（含 JSON `reports` 输出） |

只有"兼容审计"级以上的实现可以在宣传中使用本协议名称与规则编号。

---

## 9. 协议版本化与变更程序

1. 协议自身遵循语义化版本：规则的新增/放宽升 minor，规则的收紧/字段语义变更升 major。
2. 仓库在 `CONSTITUTION.md` 或 frontmatter 中声明所遵循的协议版本；major 版本不同的实现不得混用判定结果。
3. 变更提案必须附：**动机、对现有仓库的迁移成本、参考实现中的对应 diff**。没有实现背书的协议变更是空谈。
4. **扩展包机制：** 数值系统（WGP-econ）、地理坐标（WGP-geo）等作为独立扩展包维护，独立版本号；仓库声明启用哪些包，lint 只跑启用包的规则。core 保持最小。
5. **实验值泄压阀（协议 1.1 起）：** `type` 与 `depends_on.kind` 一样，允许 `x-<命名空间>-<名称>` 形式的实验值——**能存、不判错**，`type` 记 CA102 info、`kind` 记 CA108 info。词表要扩，先攒真实案例，再按第 1 条升版本。

---

## 附录 A · 承重墙关键词清单（初始集）

经济、货币、税收、贸易、铸币、政治、政权、法律、继承、选帝、军队、征兵、战争赔款。

（此清单升 minor 版本维护；各仓库可以**追加**本地关键词，不得删减协议集。）

## 附录 B · 裁决记录与进行中的事项

**已裁决（v0.3 落槌）：**
1. ~~kind 六值封版~~ → **不封版**，六值为初始集，`x-` 前缀实验值合法（CA108 info 计入案例收集）。
2. ~~条目级权限~~ → 不入协议；落地为审计中立性条款（§6.2）。
3. ~~conflicts_with 方向性~~ → 默认对称 + 可选 `stance`（§4），CA403 放宽。
4. ~~跨仓库引用~~ → 语法 `world:id` 保留，本版不实现，遇到必报 CA401（§2.3）。
5. ~~恢复冷却期/次数上限~~ → 交宪章声明；默认路径 `archived → trial → canon`（§3.3）。

**已封版（v1.0 落槌）：**
- **kind 六值封版**：三个测试世界（魔戒/冰火/沙丘）案例收集完成。物质五值零例外；实验值 `x-will-binding`、`x-magic-logistics`、`x-faith-engineering` 各出现一次，证据不足以升格，留档观察。`x-` 通道永久开放。
