# 结论断言与干净所有权模型 Implementation Plan（B 方案）

> **状态：历史（2026-11-09 完成）**——Task 1–5 已全部勾选，提交 3519038 / 4af0258 / 51d43d0 / 2d8fc60。
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 把「手写断言」的语义从「期初事实」彻底改成「当前结论」，并让流水成为唯一的时序来源——`transfer`/`grant` 补 `from` 腿、派生状态事件优先、`certainty` 三态进导出契约；A 方案（协议 1.10）已经把措辞与同刻未定序的地砖铺好。

**Architecture:** 判定层两套实现（legacy `canonlint.py` 与 Registry `judges/ca/ledger.py`）必须同步改；`ledger.py` 的 `derive_state` 从「owns 初始化 + 流水覆盖」改成「流水推出 + owns 兜底」，并新增 `from` 腿的时序校验；契约 0.7→0.8 在 `world.schema.json` 增加 `certainty`，导出 JSON 的 `ledger` 段透出 `known/unknown/ambiguous`；前端三视图展示未定序，而不是显示一个确定答案。

**Tech Stack:** Python 3 标准库、PyYAML、现有脚本式断言测试、JSON/HTTP、GitHub Actions；不引 pytest 或新依赖。

**Spec:** GitHub issue #10（`sliensnomen/my-world`）——「owns/custody_of/member_of 时间语义与不确定状态」；对照 `docs/事件流水设计.md` D3/D5。

## 背景：A 方案已经做了什么（协议 1.10）

- 同刻「归属未定序」warning 从断言循环里抽出来：没有 `owns`/`custody_of` 也报，每客体一条。
- 文档与代码口径统一为「当前结论断言」：`owns` 无时间，没有更早流水时兼作历史起点，流转后写最终持有者。
- **没有**动的是：`from` 腿、`certainty` 契约、派生状态的「事件优先」、前端展示。这些全部留给本计划。

## Global Constraints

- 一个任务一个 commit；测试不绿不提交；改判定 = 协议变更（按 §9.1 升号、同步 §6.3、钉数字文档）。
- 双后端（`legacy` / `registry`）行为必须完全一致；每批改动双跑并通过六套回归。
- 世界夹具由生成器产出（`tests/make_worlds.py`、`tests/make_ledger.py`）：先改生成器再重新生成，`git diff --stat` 核对不该动的世界一个字节不变。
- 快照只在有意变更时 `--update`，更新后逐份肉眼核对 diff。
- 契约变更按 §9.1：`CONTRACT_VERSION` 0.7→0.8 需同步 `world.schema.json`、`tests/test_schema.py` 与文档里的版本字面。

## Review Focus

1. **`from` 腿的时序语义**：`transfer`/`grant` 的 `from` 是「谁交出的」，与 `by`（谁执行的）分离；缺 `from` 时 fail-open（不判时序不一致），不能把旧世界判红。
2. **derive_state 的事件优先与兜底**：有流水时 owns 只做对账（CA704/709）；无流水时才用 owns 当历史起点。`member_of`、`custody_of` 同口径。
3. **certainty 三态**：`known`（唯一结论）/ `unknown`（无断言也无流水）/ `ambiguous`（同刻未定序或断言互搏）——`ambiguous` 不是错误，是诚实的导出值；前端三视图必须能展示。
4. **双后端与夹具重生成**：全族 CA7xx 在两边都要跑；重生成夹具后逐世界核对 diff。

---

### Task 1: 契约 0.8——`from` 腿与 `certainty`

**Files:**
- Modify: `world.schema.json`（事件字段与导出契约）
- Modify: `canonlint.py`（`CONTRACT_VERSION`）
- Modify: `tests/test_schema.py`
- Test: `tests/run_tests.py`

- [x] 先写红测试：带 `from` 的 `transfer`/`grant` 合法；`certainty` 三态在 JSON 里出现且取值受限。
- [x] 契约升 0.8：事件字段允许 `from`（形状已允许，补语义与测试）；导出 `ledger` 段每个客体带 `certainty`。
- [x] 同步 `PROTOCOL.md` §9.1 与 `world.schema.json` 的 `x-contract-version`。

### Task 2: 派生状态改为「事件优先，owns 兜底」

**Files:**
- Modify: `ledger.py`（`derive_state`、`derive_membership`）
- Modify: `canonlint.py`、`judges/ca/ledger.py`（CA703/CA704/CA709/CA712）
- Test: `tests/run_tests.py`

- [x] 先写红测试：有完整流水时，派生状态完全由流水决定；owns 只参与对账。
- [x] 无流水时 owns 仍是历史起点（A 的语义保留）；`certainty` 按三态计算并随导出输出。
- [x] 双后端对齐，全族 CA7xx 双跑。

### Task 3: `from` 腿的时序校验（新规则编号按 §9.1 决定）

- [x] 先写红测试：`transfer.from` 与「上一笔 transfer 的 to」不一致时报什么、缺 `from` 时 fail-open。
- [x] 与 CA711 同款「只与严格更早比较、同刻合并」的口径；编号、级别、规则表同步。
- [x] 事件夹具补 `from` 用例；生成器重生成后核对 diff。

### Task 4: 前端三视图与导出

**Files:**
- Modify: `web/index.html`、`docs/给前端的说明.md`
- Test: `tests/test_serve.py`

- [x] 视图一：确定态（流水唯一结论）；视图二：猜的（无流水，仅 owns，标 `certainty: unknown`）；视图三：未定序（`ambiguous`，展示冲突双方，不挑赢家）。
- [x] 导出 JSON 与 HTTP 接口同步；`docs/给前端的说明.md` 补字段说明。

### Task 5: 验收与文档收口

- [x] 六套回归全绿；快照逐份核对；夹具重生成后的 `git diff --stat` 核对。
- [x] `README.md` / `CONTRIBUTING.md` / `store/README.md` 的检查项数、`PROTOCOL.md` §6.3 与版本号同步。
- [x] 完成后把本计划状态改为「历史」，并在 `docs/README.md` 同步状态。

## 不做（本期明确排除）

- 不建「期初快照文件」（`docs/事件流水设计.md` D5 已否决：两份真值必然漂移）。
- 不引入 `entry_points`、AI、chain、热重载。
- 不把事件 id 序当历史；同刻永远 fail-open 或「未定序」。
