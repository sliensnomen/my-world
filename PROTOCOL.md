# 世界观治理协议（World Governance Protocol）草案 v0.5

**状态：草案，未冻结 ｜ 日期：2026-09-23**
**本文件的读者：协议实现者。条款用词"必须/应当/可以"为规范性词汇，含义同 RFC 2119 的 MUST/SHOULD/MAY。**

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
- 引用与矛盾标注（`canon_refs` / `conflicts_with` / `depends_on`）；
- 审计规则注册表（CA 编号规则集）。

本协议**不规定**：存储后端（git、数据库、纯文件皆可）、编辑界面、发布形式、AI 实现细节、权限模型。

**定位声明：** 协议是产品，实现是参考。任何工具只要通过本协议的规则集，即为兼容实现。协议活得比任何工具久。

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
| `type` | 必须 | enum | `location` / `faction` / `character` / `event` / `item` |
| `author` | 必须 | string | 实名/笔名皆可；实名映射表属实现细节，不入协议 |
| `date` | 必须 | date | ISO 8601（YYYY-MM-DD），首次创建日期 |
| `status` | 必须 | enum | 见 §3 状态机 |
| `load_bearing` | 必须 | bool | `true` = 显式声明为承重墙条目，触发 §5 全部义务 |
| `canon_refs` | 必须 | id 列表 | 本条目语义依赖的已定档条目，可以为空列表 |
| `conflicts_with` | 必须 | 列表 | 元素为 id 或对象（§4.1），可以为空列表 |
| `depends_on` | 条件必填 | 对象列表 | 见 §5.3 schema；`load_bearing: true` 时必填 |
| `layer` | 条件必填 | enum | 见 §5.2；`load_bearing: true` 时必填 |
| `superseded_by` | 条件必填 | id 或 null | 见 §3.4；仅 `archived` 条目使用 |
| `ai_assisted` | 必须 | bool | 见 §7 AI 条款 |

**扩展字段：** 实现可以添加任何 `x-` 前缀的自定义字段；不带前缀的未定义字段**必须**被审计器拒绝（CA106），防止私有字段渗透进协议。

### 2.3 引用语法

所有跨条目引用（`canon_refs` / `conflicts_with` / `depends_on[].id` / `superseded_by`）**必须**使用 `id`，**禁止**使用文件路径或标题。

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

---

## 5. 政治经济学链条（承重墙的结构化约束）

### 5.1 动机

设定的多数矛盾不是文本互斥，而是**供应链断裂**（贫穷农业国养十万常备军）。本协议将政治经济学的层叠模型编码为可机器检查的推导链，使此类矛盾从语义问题降格为图论问题。

### 5.2 层级字典（协议常量，七层，刻意最小）

```
geo → resource → production → economy → fiscal → military → political → ideology
```

每层有确定的**链条序号**（geo=0 … ideology=6）。字典的扩展走协议变更程序（§9），实现**不得**私增层级。

### 5.3 承重墙条目的义务

承重墙身份由 `load_bearing: true` **显式声明**，声明即承担全部义务：

| 义务 | 缺失后果 |
|---|---|
| 填 `layer` | CA302 **error** |
| 填 `depends_on`（可为空列表，但字段必须在） | CA302 **error** |

仅命中附录 A 关键词但未声明 `load_bearing` 的条目，CA301 发出 **warning**（提示作者考虑声明）。"必须"只落在显式声明上，审计器不替作者做决定。

### 5.4 `depends_on` 对象 schema（kind 暂不封版）

每个元素**必须**恰好包含以下三个必填字段，可以加 `x-` 扩展字段：

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | id 引用 | 必填 |
| `kind` | string | 必填。初始集六值：`resource` / `production` / `economy` / `fiscal` / `manpower` / `legitimacy`；**初始集外允许 `x-` 前缀实验值**（如 `x-faith`），用于案例收集，集满后再议封版（附录 B） |
| `critical` | bool | 必填；`true` = 断供即崩塌 |

缺字段、多字段（非 `x-`）= CA107 error；`kind` 在初始集外且无 `x-` 前缀 = CA108 error，有 `x-` 前缀 = CA108 info 级提示（计入案例收集）。

**kind 分族（v0.5 起）：** 初始集六值分为两族——

- **物质族** `resource` / `production` / `economy` / `fiscal` / `manpower`：自下而上流动，受 CA501 层级方向约束与 CA502 环检测；
- **规范族** `legitimacy` 与一切 `x-` 实验 kind：自上而下流动（合法性、强制力、超自然力），豁免 CA501，不参与 CA502。

`depends_on` 只表达**供养关系**（断供即崩），**不得**用来表达"主题相关"（那用 `canon_refs` 或正文叙述）。

### 5.5 链条合法性

- **物质族** `depends_on` 目标的 `layer` 链条序号**必须 ≤** 本条目 `layer` 的链条序号；**同层依赖允许**。违反 = CA501 error。规范族边不做方向检查。
- **物质族**依赖子图**必须**无环（A 养 B、B 养 A = 永动机）。违反 = CA502 error。规范族互锁（如"魔戒↔支配者"）合法。
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
| CA102 | error | 枚举字段非法（`type`/`status`/`layer`/`stance`） |
| CA103 | error | `date` 非合法 ISO 日期 |
| CA104 | warning | `trial`/`canon` 条目正文少于 200 字（计数算法见 §6.6） |
| CA105 | error | `id` 重复，或含小写字母/数字/连字符以外字符 |
| CA106 | error | 存在不带 `x-` 前缀的未定义字段 |
| CA107 | error | `depends_on` 对象违反 §5.4 schema（缺字段/多非 x- 字段） |
| CA108 | error/info | `depends_on[].kind` 在初始集外：无 `x-` 前缀 = error；有 `x-` 前缀 = info（案例收集） |
| CA109 | error | 字段类型/格式非法：`canon_refs` 非列表或元素非字符串、`load_bearing`/`ai_assisted`/`critical` 非 bool、id 引用不符合 `^[a-z0-9-]+$` 格式（`world:id` 形式除外，归 CA401）等 |
| CA201 | warning | 两条目正文相似度 ≥ 阈值（默认 0.85；预处理与最短长度见 §6.6） |
| CA301 | warning | 命中附录 A 关键词但 `load_bearing` 非 `true`（提示考虑声明） |
| CA302 | error | `load_bearing: true` 但缺 `layer` 或 `depends_on` |
| CA401 | error | 引用（含 `superseded_by`）指向不存在的 `id`；或引用为 `world:id` 形式（本版未支持，**禁止静默忽略**） |
| CA402 | error | `canon_refs` 目标状态为 `draft`/`trial`；或目标为 `archived` 且已填 `superseded_by`（提示迁移至承接条目）。目标为 `archived` 且未填 `superseded_by` 时**不报本条**，由 CA405 在 archived 条目侧单独报告，避免双报 |
| CA403 | warning | `conflicts_with` 双方均简式且缺回指（对象式标注豁免，见 §4.2） |
| CA404 | error | `canon` 条目的 `depends_on` 目标状态非 `canon`（链条依赖只能建立在已定档上） |
| CA405 | error | `archived` 条目仍被 `canon_refs` 引用且 `superseded_by` 未填（降级处置不完整） |
| CA501 | error | **物质族** `depends_on` 目标的链条序号 > 本条目的链条序号（规范族边豁免） |
| CA502 | error | **物质族**依赖子图存在环 |
| CA503 | warning | economy/fiscal/military/political 层承重墙条目无任何**物质族** `critical: true` 依赖（ideology 层豁免） |
| CA505 | warning | 仓库级：存在 military/political 层承重墙条目，但全库没有任何 `layer: fiscal` 的条目（财政维度缺失提示；条目不须为承重墙） |
| CA504 | report | 变更/降级影响报告：输出变更条目的下游传递闭包 |

**无传递违规原则：** CA402/CA404/CA405 只判**直接边**的违规。A 引用 B、B 违规并不使 A 连带违规；"连带影响"是 CA504 报告的职责，不是 error 的传染。

**判定一致性要求：** 同一仓库快照、同一规则集版本，任何兼容实现的确定性规则判定**必须**逐条一致。判定出现分歧 = 某实现有 bug 或协议有歧义，两者都必须修。

### 6.4 退出码约定

- `0`：无 error（warning/info/report 不影响）；
- `1`：存在 error；
- `--strict` 模式下 warning 也使退出码为 1（pre-commit 等场景使用）；
- **CA504 与 CA9xx 永不参与退出码。**

### 6.5 机器可读输出（JSON）

兼容审计级实现**必须**支持 JSON 输出，schema 如下（此 schema 封版，扩展走 `x-` 字段）：

```json
{
  "protocol_version": "0.5",
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

**进行中：**
- **kind 案例收集计划**：用 3–5 个真实世界观做供应链标注，落不进初始集六值的一律 `x-` 前缀记录；集满案例后评审是否扩集或封版。巫王世界为第一个样本（一个政权的钱与兵 + 一座城的人口与粮源）。
