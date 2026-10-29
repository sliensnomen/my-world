# `modify` 事件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Backlog B1 的 `modify` 转为第 12 种正式事件，锁住「同一 id 内变化、不改窗口与派生状态」的语义。

**Architecture:** 只扩展 `ledger.py` 的共享事件词表和必填腿表，现有 CA 规则、CLI、HTTP 与导出自动复用。协议升 1.9、契约升 0.7，不新增字段、CA 规则或属性补丁模型；独立合成世界负责意图测试，既有世界夹具不动。

**Tech Stack:** Python 3 标准库、PyYAML、JSON Schema、Markdown、仓库现有脚本式断言测试（不引 pytest）。

**Spec:** `docs/superpowers/specs/2026-10-28-modify-event-design.md`

## Global Constraints

- `modify` 必填 `object`、可选 `by`；正文记录变化，不新增属性前后值结构。
- `modify` 不改变身份、存在窗口、持有者、保管人、位置或成员关系；`result` 不为它开窗。
- 协议版本改为 1.9、契约版本改为 0.7；确定性规则保持 55 条，不新增 CA 编号。
- 不引入新依赖，不引 pytest；新意图测试必须先看到红，再实现到绿。
- 不修改既有 `tests/world-*` 和 `tests/snapshots/`；若实测出现意外 diff，停止并查明原因。
- B3 携带推导与 B5 CA301 的决定不变；不实现其他 README 产品方向。
- 保留工作区已有 `.gitignore`、`AGENTS.md` 和 `.review-scratch/` 状态，不读、不改 `.review-scratch/`。
- 用户未要求 Git 提交，本计划不执行 `git add` / `git commit`。

## Review Focus

1. **缺 `when_sort` 的 `modify`**：应仍是合法完整事件但不进有序流水、不报 CA708；Task 1 Step 2 的 `ev-unsorted` 锁住。
2. **缺失、坏形状、悬空 `object`**：分别只走 CA702、CA109、CA401，不能双报或静默；Task 1 Step 2 的 `ev-missing`、`ev-shape`、`ev-ghost` 锁住。
3. **与 death 同刻的施动者**：同刻不算死后，严格更晚才报 CA705；Task 1 Step 2 的 `ev-same` / `ev-late-actor` 锁住。
4. **误带 `result` 的 `modify`**：不得像 transform 一样给新 id 开窗；Task 1 Step 2 的 `ev-modify-result` / `ev-move-new` 锁住。
5. **已有派生状态与 CLI 入口**：modify 不得清掉持有/保管/位置，真实 `event modify` 建卡必须可审计；Task 1 Step 2 的 ledger 断言和 CLI 临时世界锁住。

---

### Task 1: 事件词表、必填腿与契约运行时

**Files:**
- Modify: `tests/run_tests.py`（新意图函数与 extras 登记）
- Modify: `ledger.py:9-33`（`EVENT_KINDS`、`REQUIRED_LEGS`）
- Modify: `canonlint.py:38-40,701-707`（版本与 CA708 注释）
- Modify: `world.schema.json:4-7,26,35`（契约版本、事件词表与规则范围说明）

**Interfaces:**
- Consumes: `_card()`、`_temp_world()`、`_judge()`、`run_case()`、`ledger.EVENT_KINDS`、`ledger.REQUIRED_LEGS`。
- Produces: 正式 `event_kind: modify`；`REQUIRED_LEGS["modify"] == ("object",)`；`PROTOCOL_VERSION == "1.9"`；`CONTRACT_VERSION == "0.7"`。

- [x] **Step 1: 建立绿色基线**

Run:

```bash
python3 tests/run_tests.py && python3 tests/test_schema.py
```

Expected: 主套件 `62 项检查 | 全部通过`，schema `12 项检查 | 全部通过`。

- [x] **Step 2: 写入完整的 modify 失败测试**

在 `tests/run_tests.py` 的 `check_transform_closes_and_opens_windows()` 后加入：

```python
def check_modify_preserves_identity_and_state() -> list[str]:
    """modify（协议 1.9）：同 id 变化，不动窗口、持有、保管或位置。"""
    problems = []

    def ev(eid: str, kind: str, sort: float | None, legs: str) -> str:
        sort_line = f"when_sort: {sort}\n" if sort is not None else ""
        return _card(
            eid, f"when: 第{sort}年\nevent_kind: {kind}\n{sort_line}{legs}"
        ).replace("type: location", "type: event")

    def findings(world: Path) -> list[dict]:
        _code, out, err = _judge(world, "--json")
        if err:
            problems.append(f"modify 世界把 traceback 写到了 stderr：\n{err}")
        try:
            return json.loads(out)["findings"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            problems.append(f"modify 世界的 JSON 审计输出不可读：{exc}\n{out}")
            return []

    def hit(items: list[dict], rule: str, entry: str) -> bool:
        return any(f["rule"] == rule and Path(f["entry"]).name == f"{entry}.md"
                   for f in items)

    cards = {
        "relic": _card("relic", ""),
        "owner": _card("owner", "owns:\n  - relic\n"),
        "keeper": _card("keeper", "custody_of:\n  - relic\n"),
        "old-place": _card("old-place", ""),
        "ev-create": ev("ev-create", "create", 1, "object:\n  - relic\n"),
        "ev-custody": ev("ev-custody", "custody", 2,
                         "by:\n  - owner\nto:\n  - keeper\nobject:\n  - relic\n"),
        "ev-move": ev("ev-move", "move", 2,
                      "object:\n  - relic\nto:\n  - old-place\n"),
        "ev-modify": ev("ev-modify", "modify", 3, "object:\n  - relic\n"),
        "ev-unsorted": ev("ev-unsorted", "modify", None, "object:\n  - relic\n"),
    }
    tmp, world = _temp_world("canonlint-modify-ok-", cards)
    with tmp:
        items = findings(world)
        for rule in ("CA102", "CA702", "CA708"):
            for entry in ("ev-modify", "ev-unsorted"):
                if hit(items, rule, entry):
                    problems.append(f"合法 {entry} 不该报 {rule}：{items}")
        code, out, err = run_case(["ledger", str(world)])
        expected = "relic: 持有者 owner（来自 `owner`） | 保管 keeper | 位置 old-place"
        if code != 0 or err or expected not in out:
            problems.append(f"modify 改变了既有派生状态：\n{out}{err}")

    cards = {
        "relic": _card("relic", ""),
        "person": _card("person", ""),
        "ev-early": ev("ev-early", "modify", 0, "object:\n  - relic\n"),
        "ev-death": ev("ev-death", "death", 1, "object:\n  - person\n"),
        "ev-same": ev("ev-same", "modify", 1,
                      "by:\n  - person\nobject:\n  - relic\n"),
        "ev-late-actor": ev("ev-late-actor", "modify", 2,
                            "by:\n  - person\nobject:\n  - relic\n"),
        "ev-create": ev("ev-create", "create", 3, "object:\n  - relic\n"),
        "ev-destroy": ev("ev-destroy", "destroy", 4, "object:\n  - relic\n"),
        "ev-after": ev("ev-after", "modify", 5, "object:\n  - relic\n"),
        "ev-missing": ev("ev-missing", "modify", 6, ""),
        "ev-shape": ev("ev-shape", "modify", 7, "object: relic\n"),
        "ev-ghost": ev("ev-ghost", "modify", 8, "object:\n  - ghost\n"),
    }
    tmp, world = _temp_world("canonlint-modify-bad-", cards)
    with tmp:
        items = findings(world)
        for entry in ("ev-early", "ev-after"):
            if not hit(items, "CA708", entry):
                problems.append(f"{entry} 落在存在窗口外却没报 CA708：{items}")
        if hit(items, "CA705", "ev-same"):
            problems.append(f"与 death 同刻的 modify 不该报 CA705：{items}")
        if not hit(items, "CA705", "ev-late-actor"):
            problems.append(f"严格晚于 death 的 modify 没报 CA705：{items}")
        if not hit(items, "CA702", "ev-missing"):
            problems.append(f"modify 缺 object 没报 CA702：{items}")
        if not hit(items, "CA109", "ev-shape") or hit(items, "CA702", "ev-shape"):
            problems.append(f"坏 object 形状应只报 CA109：{items}")
        if not hit(items, "CA401", "ev-ghost"):
            problems.append(f"modify 的悬空 object 没报 CA401：{items}")

    cards = {
        "old-relic": _card("old-relic", ""),
        "new-relic": _card("new-relic", ""),
        "keep": _card("keep", ""),
        "ev-modify-result": ev(
            "ev-modify-result", "modify", 3,
            "object:\n  - old-relic\nresult:\n  - new-relic\n"),
        "ev-move-new": ev("ev-move-new", "move", 4,
                          "object:\n  - new-relic\nto:\n  - keep\n"),
        "ev-create-new": ev("ev-create-new", "create", 5,
                            "object:\n  - new-relic\n"),
    }
    tmp, world = _temp_world("canonlint-modify-result-", cards)
    with tmp:
        items = findings(world)
        if not hit(items, "CA708", "ev-move-new"):
            problems.append(f"modify 的 result 被误当成开窗边界：{items}")
        if hit(items, "CA708", "ev-modify-result"):
            problems.append(f"modify 自身不该成为存在窗口边界：{items}")

    tmp, world = _temp_world("canonlint-modify-cli-", {"relic": _card("relic", "")})
    with tmp:
        p = subprocess.run(
            [PY, str(TOOL), "event", "modify", "局部改建",
             "--root", str(world), "--id", "ev-cli",
             "--when", "元年", "--when-sort", "1", "--object", "relic"],
            cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            problems.append(f"event modify 应能建卡，实际 exit={p.returncode}：{p.stderr or p.stdout}")
        if not (world / "entries" / "events" / "ev-cli.md").is_file():
            problems.append("event modify 没有写出 entries/events/ev-cli.md")
        items = findings(world)
        for rule in ("CA102", "CA702", "CA708"):
            if hit(items, rule, "ev-cli"):
                problems.append(f"CLI 建出的合法 modify 不该报 {rule}：{items}")
    return problems
```

在 extras 中 transform 项之后登记：

```python
        ("modify 同 id 变化：不动窗口/状态，复用通用规则与 CLI",
         check_modify_preserves_identity_and_state),
```

- [x] **Step 3: 运行测试并确认先红**

Run: `python3 tests/run_tests.py`

Expected: 总数变为 63，新检查 FAIL；合法 modify 报 CA102，缺 object 没有 CA702，CLI `event modify` 退出非 0。既有 62 项仍通过。

- [x] **Step 4: 做最小运行时与契约实现**

`ledger.py` 的词表与腿表改为：

```python
EVENT_KINDS = {"transfer", "custody", "move", "create", "destroy",
               "grant", "birth", "death", "join", "leave", "transform", "modify"}
```

在 `REQUIRED_LEGS` 的 transform 项后加入：

```python
    # modify（协议 1.9）：同一 id 内的变化；不动存在窗口和派生状态，by 可选。
    "modify": ("object",),
```

`canonlint.py` 改为：

```python
PROTOCOL_VERSION = "1.9"   # 1.9：modify 转正；同一 id 内变化，不动窗口与派生状态
CONTRACT_VERSION = "0.7"   # 与 world.schema.json 的 x-contract-version 一致（tests/test_docs.py 钉住）
```

CA708 注释补明 `modify` 不是端点：

```python
    # CA708: 客体的事件必须落在它自己的存在窗口里（create/birth 开窗，
    # death/destroy 关窗，transform 关旧窗开新窗；端点事件自身即边界，跳过）。
    # modify 是普通客体事件，只受窗口约束，不改变窗口。
```

`world.schema.json` 做四处精确替换：

```text
世界文件契约 v0.6 → 世界文件契约 v0.7
"x-contract-version": "0.6" → "x-contract-version": "0.7"
event_kind 数组在 "move" 前加入 "modify"
CA701–CA710 → CA701–CA712
```

- [x] **Step 5: 跑到主套件与 schema 全绿**

Run:

```bash
python3 tests/run_tests.py && python3 tests/test_schema.py
```

Expected: `63 项检查 | 全部通过`、`12 项检查 | 全部通过`；没有快照更新。

### Task 2: 协议、规则表与现行参考同步

**Files:**
- Modify: `PROTOCOL.md`（1.9 修订、字段表、CA702/708、JSON 示例）
- Modify: `docs/判定规则总表.md`
- Modify: `docs/事件流水设计.md`
- Modify: `docs/给前端的说明.md`
- Modify: `docs/superpowers/specs/2026-10-24-works-layer-design.md`
- Modify: `README.md`、`CONTRIBUTING.md`、`store/README.md`

**Interfaces:**
- Consumes: Task 1 的 1.9 / 0.7 版本、十二种事件和 63 项主套件实测。
- Produces: 与代码一致的协议、规则表、Backlog 和前端样例；55 条规则不变。

- [x] **Step 1: 让现有文档守卫先指出过期数字**

Run: `python3 tests/test_docs.py`

Expected: FAIL，至少指出 README/CONTRIBUTING 的 62 与实测 63 不符，以及 PROTOCOL 的 1.8 与代码 1.9 不符。不得改测试迁就文档。

- [x] **Step 2: 更新权威协议**

在 `PROTOCOL.md` 的 v1.8 修订第 31 条后加入：

```markdown
**v1.9 修订记录（2026-10-28，modify 转正）：**

32. **`modify` 进词表：同一身份内的变化**。`object` 必填、`by` 可选，具体变化写在事件正文；它不新增属性补丁结构，不改变持有者、保管、位置或成员关系。与 `transform` 不同，`modify` 不关闭或打开存在窗口，`result` 对它没有产物语义。CA102/CA109/CA401/CA702/CA705/CA708 复用既有判定，不新增规则编号，按 §9.1 升 minor；契约升 0.7。
```

同步这些精确内容：

- 顶部 `PROTOCOL_VERSION = "1.8"` 改为 `"1.9"`，JSON 示例的 `protocol_version` 同样改 1.9。
- §2.2 的 `event_kind` 改为“十二值”，列表末尾加入 `modify`。
- CA702 的腿表明确写入：`create`/`destroy`/`birth`/`death`/`modify` 要 `object`；其余现有腿表不变。
- CA708 补一句：“`modify` 是普通客体事件，不是端点；同一 id 的变化不关闭或打开窗口。”
- §9 规则数保持 39 core CA、总计 55，不为 modify 新增编号。

- [x] **Step 3: 更新规则总表、Backlog 与前端契约样例**

`docs/判定规则总表.md`：

- 顶部改为“协议 1.9 / 契约 0.7”，数量仍为 55。
- CA102 的“十一种事件”改“十二种事件”。
- CA702 与附录 A.4 加入 `modify | object`；CA708 补明 modify 不动窗口。

`docs/事件流水设计.md`：

- B1 标题改为“✅（transform 协议 1.7、modify 协议 1.9 均已转正）”。
- 保留历史案例，新增“modify 转正裁决”：`object` 必填、`by` 可选、正文记变化、同 id 不动窗口和派生状态、不建属性补丁模型。
- D7 的窗口交接段把“modify 仍未进词表，等案例再说”改为“modify 已在 1.9 转正，是普通客体事件，不动窗口”。
- B3 与 B5 原文不动。

`docs/给前端的说明.md`：两份 JSON 样例改为 `protocol_version: 1.9`、`contract_version: 0.7`；事件种类示例加入 modify，完整词表改为十二种。

`docs/superpowers/specs/2026-10-24-works-layer-design.md`：仅把预留“契约 0.7”改为“契约 0.8”，其他作品层文字不动。

- [x] **Step 4: 同步入口数字与下一轮方向**

- `README.md` 两处 `62 + 12 + 26 + 31 + 15` 改为 `63 + 12 + 26 + 31 + 15`。
- `CONTRIBUTING.md` 与 `store/README.md` 的主套件 `62 项` 改为 `63 项`。
- `README.md` 下一步第 5 项改为：“事件流水后续：携带推导等待容器卡触发；`modify` 已在协议 1.9 转正”，保留设计文档链接。
- 不改历史评审报告和已执行计划里的旧版本、旧数字。

Run:

```bash
python3 tests/test_docs.py && python3 tests/test_serve.py && python3 tests/run_tests.py
```

Expected: 文档 `15 项检查 | 全部通过`，HTTP `31 项检查 | 31 通过 | 全部通过`，主套件 `63 项检查 | 全部通过`。

### Task 3: 设计状态收口与全量验收

**Files:**
- Modify: `docs/superpowers/specs/2026-10-28-modify-event-design.md`
- Modify: `docs/superpowers/plans/2026-10-28-modify-event.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: Task 1–2 的实现与绿色证据。
- Produces: 已实施规格、已执行计划和可复核的六套回归结果。

- [x] **Step 1: 收口文档状态**

- 规格顶部状态改为“已确认并实施，2026-10-28”。
- 本计划只勾选实际完成的步骤，不补勾未执行项。
- `docs/README.md` 中规格状态由“草案”改“现行”，本计划状态由“草案”改“历史”；摘要和更新触发保持与实施事实一致。

Run: `python3 tests/test_docs.py`

Expected: `15 项检查 | 全部通过`，索引包含规格与计划，无漏登记、重复或非法状态。

- [x] **Step 2: 跑完整六套标准回归**

```bash
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 tests/test_serve.py
python3 tests/test_docs.py
python3 classlint/tests/run_tests.py
```

Expected: `63 + 12 + 26 + 31 + 15` 项全部通过，classlint 18 个夹具世界全部通过。

- [x] **Step 3: 真实 CLI 场景验收**

在临时副本上建卡，不改仓库夹具：

```bash
tmp=$(mktemp -d)
cp -R tests/world-ledger "$tmp/world"
python3 canonlint.py event modify "局部改建" \
  --root "$tmp/world" --id ev-modify-smoke \
  --when "验收时" --when-sort 8 --object fox-blade
python3 canonlint.py "$tmp/world"
python3 canonlint.py ledger "$tmp/world"
rm -rf "$tmp"
```

Expected: 建卡 exit 0；审计为 `0 错误 | 0 警告`、exit 0；ledger 有 9 笔完整事件，fox-blade 的持有者、保管与位置保持原值。

- [x] **Step 4: 核对最终 diff 与不变量**

Run:

```bash
git diff --stat
git diff -- tests/world-* tests/snapshots
git status --short
```

Expected:

- 世界夹具与快照无 diff；规则数仍为 55；协议/契约为 1.9/0.7。
- diff 只含本计划登记的实现、测试、协议、文档文件。
- 既有 `.gitignore`、`AGENTS.md`、`.review-scratch/` 状态未被本任务改变。
- 不执行 Git 提交；最终回复列出六套实测结果和 CLI 验收结果。
