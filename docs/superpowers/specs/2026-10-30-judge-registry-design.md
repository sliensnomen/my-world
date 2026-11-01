# 判定器注册表设计

> 状态：已确认并实施。2026-10-30。
> 一句话：用统一 Rule/Pack 元数据和加载入口组合条目规则与世界规则，分期迁移 CA/CL/PE/econ，迁移期间判定不变且随时可回退。

## 1. 目标与边界

最终目标是把 CA、CL、PE 和 econ 纳入同一个注册表架构，同时保留现有引擎的语义。
`chain --judge ca|pe` 后续只查询注册表；classlint 的“存 / 判”拆分通过独立判定包完成。

本期不实现 chain、AI 判定器、作品层、流量层、热重载或 entry_points 动态发现，不引入新依赖。
AI 若以后接入，只能走独立 `JudgeReport`/stdout 报告流，不得进入 Finding、退出码或自动写入。

迁移若改变任何现有判定，必须停止并修正，不得以“注册表重构”为名顺手改协议。
等价迁移不改变 `PROTOCOL_VERSION`、classlint 协议版本或现有规则编号。

## 2. 当前接口与兼容事实

当前存在三种形态：

- canonlint 的成组检查函数，顺序为结构→内容→引用→链→事件→流水→查重→扩展包；
- classlint 的 `Rule(world, emit)` 与按编号排序的 PE 执行；
- econ 的 `KNOWN_FIELDS + check_entry(meta, rel, add)`。

兼容不仅指规则集合相同，还包括：Finding 顺序、级别、消息、条目路径、info、stdout、stderr、
退出码、JSON/reports、文本输出、graph、mentions 和 CLI/serve 行为。当前没有行列号、时间戳或
耗时字段，迁移不得新增这些非确定输出。

## 3. Rule、Pack 与 Finding

### 3.1 Rule 元数据

每条 Rule 固定包含：

| 字段 | 含义 |
|---|---|
| `id` | 稳定规则编号；执行时由 Registry 注入，check/emit 不得改写 |
| `pack` | 所属 Pack 名 |
| `scope` | `entry` 或 `world`；本期不引入 `both` |
| `entry_domain` | entry 规则的遍历域：`all_entries` / `all_parseable` / `index_parseable` |
| `check` | 按 scope 分派的可调用对象 |
| `default_level` | 默认 Finding 级别，必须属于 `levels` |
| `levels` | 该规则实际的全部允许级别；逐规则登记，不能从示例推导 |
| `order` | Pack 内唯一序号，不是全局 Finding 顺序的完整描述 |

`message_template` 与 `fix` 属于 Finding，不进 Rule。是否启用由 Pack 选择决定；实验包必须显式
加载。`since_version` 由 Pack 版本承担。单次 Finding 可用 `emit(level, entry, message)` 覆盖
默认级别，但覆盖值必须属于 `levels`，不能修改规则 id。CA102/CA108 等规则必须登记
`{error, info}`，CA704/709、PE002 等则登记实际双级别集合。

分派方式：

- `entry`：按 `entry_domain` 选择条目并调用 `check(meta, rel, add)`；
- `world`：用引擎私有上下文调用一次 `check(world, emit)`，上下文至少含
  `all_entries`、去重后的 `index` 与运行参数。

econ 的域必须是 `index_parseable`，与当前只遍历 `index.values()` 且跳过 parse_error 一致；
不得扩大到重复 id 的被遮蔽条目。CL100 等需要坏卡输入的规则使用 `all_entries`。

Registry 统一元数据、加载、查询、开关校验和 Finding 适配；**各 engine 驱动继续拥有执行日程**，
不是由通用 Registry 决定循环方式。Registry 包装 add/emit 生成统一数据形状
`rule / level / entry / message`，最终排序、去重和退出码仍归各引擎既有出口。

### 3.2 Pack 元数据与边界

Pack 固定包含 `name`、`version`、`engine`、`ca106_fields` 和有序 Rule 列表。
`ca106_fields` 只服务 canonlint CA106；classlint 的 CL103 字段表留在 classlint 驱动，两个命名空间
不得合并，classlint Pack 的该字段必须为空。

内置包：

| Pack | engine | 内容 |
|---|---|---|
| `core-ca` | canonlint | 全部 core CA；包内保持现有规则族顺序 |
| `core-cl` | classlint | CL100–CL107 逐规则注册 |
| `pe` | classlint | 全部 PE 规则 |
| `econ` | canonlint | figures 与 CA601/CA602 |

未来作品层、流量层作为新 Pack，不为 CA1xx/CA4xx 单独拆包。`basis`、`source_ref`、
`evidence_ref` 不进本期 Rule 元数据；`scope` 可扩展，不阻碍未来增加 `relation` 阶段。

`ca106_fields` 仅是当前 canonlint、当前所选 Pack 集合内的白名单并集，不表达字段所有权或语义
接管。在这个选择集内，两个 Pack 声明同一非 `x-` 字段是加载冲突；`x-` 字段继续走扩展通道。
加载器必须在 CA106 前提供并集。

## 4. 执行日程、顺序与 Finding 拼接

Pack 内 `order` 只约束该包的局部顺序，重复即加载失败；它不能替代引擎执行日程。当前日程至少
包括：

- store 先产生 CA114 初始发现；
- canonlint 对 `all_entries` 逐条目交错执行 structure→content，再执行 refs→chain→events→
  ledger→duplicates，最后按 `index_parseable` 执行 econ；
- classlint 先扫描建索引，再按 collect 的 CL 发现顺序拼接 CL105，最后按编号执行 PE；
- 各引擎出口再做既有稳定排序。

CL 的扫描/建索引必须与逐规则判定分开，CL100–CL107 各自注册；不得把 collect 整体包成一个
复合 Rule 黑盒。适配器只适配函数签名和 Finding，不得绕过逐 Rule 加载、查询与开关校验。

迁移期必须保持这些顺序；未来新增规则可插中间，但若改变 Finding 顺序，必须作为有意行为变更
更新快照并走协议审查。

`rules: off` 长期保持**仅 PE、按规则 id**，这是有意保留的现有不对称：CA/CL 不可关。
关闭不会级联禁用依赖规则，`judgement_complete` 继续只表示是否有规则被显式关闭。继续接受
YAML 1.1 将未加引号的 `off` 解析成的 `False`。

## 5. 加载失败与进程生命周期

以下均在规则执行前 fail-fast，不运行部分审计，也不“警告后继续”：

- 重复规则 id、重复 Pack 内 order、当前选择集内重复 `ca106_fields`、未知 Pack、非法级别或 scope；
- `rules: off` 中未知规则 id、非法开关值或不可关闭的 CA/CL id；
- `WGP_JUDGE_BACKEND` 非法值。

CLI 对用法/环境/配置错误返回 **2**，不是审计失败 1。Pack 结构错误在 CLI 审计前、serve 绑定
端口前暴露。世界配置在读取后、任何规则执行前校验；HTTP 沿用现有错误映射，不产生部分审计或
写入结果。

同一 Pack 在一次选择列表中被重复显式指定时，加载器只加载模块一次，但按当前行为重复执行，
避免把现有重复 `--pack econ` 静默变成新错误；不同 Pack 间的规则 id 冲突仍然失败。

serve 使用不可变注册表，本期不做热重载；规则包更新后重启进程。CLI 与 serve 必须消费同一个
加载函数、后端选择与 Pack 选择，防止读写口径分叉。

## 6. 本期延后的设计

`requires_annotations` 与 `rule_coverage` 延后到第一个真实插件需求出现时再设计。本期不新增
注解路径语法、跳过 info、coverage JSON/report 或 classlint info 输出语义，避免改变现有顶层 JSON
键和退出码计数。未来依赖 basis/source_ref/evidence_ref 的规则，只有字段进入正式 schema 后才可
登记，不能提前虚构名称。

## 7. 双跑与快照验收

每个 Pack 迁移都同时做：

1. **规范化 Finding diff**：分别比较驱动原始序列和出口排序后序列，逐项核对
   `(rule, level, entry, message)`；
2. **完整外部行为 diff**：确定性 CLI 比较 stdout、stderr、退出码及相关 JSON/reports，临时根目录
   统一为 `<WORLD>`，其余字节不清洗。

serve 使用固定比较包络：比较 HTTP 状态、body 字节和明确列出的语义头部；传输级 `Date` 与动态
端口不属于判定等价。写请求在两个相同的独立世界副本执行；审计日志的 `ts` 用固定时钟或单列
检查，其余字段逐项相等。只允许这些事先列明的既有动态量，不得新增清洗规则。

旧路径与新 Registry 在测试期并行，但正式输出只走一个后端。每个 Pack 只有在旧快照、双跑 diff
和六套回归全部一致后才算完成；阶段 0–3 不改变默认后端。

PE 验收绝不是“注册成功”：每条规则必须有真阳性、真阴性和变异证据，证明实际 Finding 的编号、
级别、归因条目和文本与旧实现一致；悬空目标、开关、graph、mentions 和 JSON 也要覆盖。

## 8. 分期实施

### 阶段 0：表征基线

- 固化现有六套输出、Finding 流和 CLI/serve 行为；
- 建立旧后端调用入口和双跑工具，确保临时路径与 serve 比较包络可重复。

### 阶段 1：Registry 骨架与 econ 参照

- 实现 Rule/Pack/Registry、加载校验、字段注入、entry_domain 和引擎 Finding 适配；
- 从本阶段起提供 `WGP_JUDGE_BACKEND=registry|legacy`，默认 **legacy**，非法值返回 2；
- 先迁移 econ，验证 `check_entry`、字段白名单和加载失败语义。

### 阶段 2：CA 分批迁移（仍默认 legacy）

按现有日程迁移结构、内容、引用、链、事件、流水、查重。每批都先写双跑红测试，证明 Registry
路径与旧路径一致；Registry 只在显式 opt-in 和双跑中启用，禁止逐批改默认后端。

### 阶段 3：classlint/PE 收口（仍默认 legacy）

- 拆分 CL 扫描/建索引与判定，CL100–CL107 逐规则进入 `core-cl`，保留 Finding 拼接顺序；
- PE 全部迁入独立包，保留 `rules: off`、退出码 3、`judgement_complete`；
- 验证正文 mentions、graph、JSON 与初始化行为完全不变；
- 每条 PE 都要有实际 Finding 的正反例与变异证据。

### 阶段 4：全量验收后原子切换

全部 Pack 验收完成后，CLI 与 serve 才把默认值一次性改为 `registry`，避免混合后端矩阵。
CI 同时跑 registry/legacy 两种后端，旧实现保留为显式紧急回退，不作为长期功能扩张。

### 阶段 5：一个发布周期后签核移除

Registry 默认运行**一个发布周期**且没有应急回退后，才由用户签核独立删除 legacy。
删除后若发现问题，通过 `git revert` 恢复删除提交；删除前优先用
`WGP_JUDGE_BACKEND=legacy` 应急并回退切换提交。

## 9. 签核标准与回滚依据

最终签核需要全部满足：

- 每个 Pack 的双跑 Finding diff 和外部行为 diff 为零；
- 六套标准回归全绿，且 registry/legacy 两个后端均通过；
- 每条迁移规则都有真实正反例，关键变异确实变红；
- CLI、serve、JSON、graph、mentions、rules: off 和错误分流一致；
- 独立代码评审无未解决 Critical/Important；
- 验收报告列出规则覆盖、快照证据、已知限制和回退方式，由用户明确批准；
- Registry 默认运行一个发布周期且无应急回退。

回退按时间顺序：先切 `WGP_JUDGE_BACKEND=legacy`；再回退默认切换提交；若旧路径已签核删除，
则 `git revert` 删除提交。禁止用重置或强推掩盖问题。

## 10. 测试与文档要求

- 保留现有快照与意图断言，新增 Registry 单元测试、加载失败矩阵和双跑差分测试；
- 每个 Pack 独立红绿，不能只做“注册成功”测试；
- 迁移期新增规则不得夹带在等价提交中，避免快照变化无法归因；
- 更新 README、CONTRIBUTING、规则总表、classlint 文档和扩展包开发菜谱；
- 新规格、实施计划与验收报告登记到 `docs/README.md`；
- 最终交付六套结果、双后端结果、独立评审结论和回退证明。
