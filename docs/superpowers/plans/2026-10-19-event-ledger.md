# 事件流水（协议 1.2 · CA7xx）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/事件流水设计.md` 实现事件流水 v0：六个事件字段进契约与存储字段面，六条 CA7xx 规则 + `canonlint ledger` 只读子命令进判定层，冰火夹具补期初与流水，文档与版本号收口。

**Architecture:** 字段形状进 `world.schema.json` + `store/model.py` 的 FIELD_TABLE（存储只认「有这个键」）；事件解析与派生状态（谁拿着什么）住新模块 `ledger.py`（判定侧纯函数，无规则编号字面量）；判语（CA701–CA706 及事件腿的 CA401/CA102/CA109）全在 `canonlint.py`（规则编号字面量必须出现在 `canonlint.py` 或 `store/*.py`，否则 `tests/test_docs.py` 的规则编号双向一致性检查会红）。测试沿用仓库惯例：夹具世界 + 逐字节快照（`tests/run_tests.py` CASES）+ 意图断言（extras），不引 pytest。

**Tech Stack:** Python 3.12/3.14（仅标准库 + pyyaml）、bash 快照测试、JSON Schema 子集（`tests/json_schema_subset.py`）。

**Spec:** `docs/事件流水设计.md`（D1–D10 为已定决定；本计划补的两处实现裁决见下）

## 关键实现裁决（spec 留白，已与作者确认或在计划中钉死）

1. **事件腿（`by`/`to`/`object`）的悬空 id 报 CA401 error**（作者已确认）。与 v1.1 修订第 16 条同一哲学：指向不存在的 id 是结构问题，不因规则归属而隐形。检查点在 `check_refs`（CA4xx 的家），用 `ledger.event_view(e)` 取腿。
2. **`event_kind` 非词表值照 type/kind 泄压阀模式**（作者已确认）：非词表且不带 `x-` 前缀 → CA102 error；`x-` 前缀 → CA102 info（案例收集）。词表进契约 `x-strict-vocabulary.event_kind`，与代码常量互相钉死。
3. **D3 与 CA704 的张力 → 「owns 断言 = 无时间的持有者主张，必须与流水推出的最终持有者一致」**。D3 说卡上断言「等于期初就这样」，而 CA704 要求断言与「最后一条 transfer 推出的持有者」一致——若断言真是期初，任何发生过流转的客体都会误报。裁决：CA704 只对**有 transfer/grant 流水推出最终持有者**的客体比对；断言与最终持有者不一致即 error。无流水的客体，`owns` 断言即全部历史，CA704 不判。期初断言同时充当 CA703 的「有持有者」证据（owns 无时间，这是 spec 原文「既无 owns 断言」的直读）。
4. **`when_sort` 缺席 = 全部时序/账平规则 fail-open**：CA701/CA703/CA704/CA705 都只判「双方都有 `when_sort` 能定先后」的部分。CA703 要求该 transfer 自己有 `when_sort`（否则「更早」无定义）。
5. **`x-` 实验 event_kind**：是事件（参与 CA701 时序，它不看 kind），但腿表未知，不判 CA702，也不参与 CA703/CA704/CA705 的派生。
6. **create/birth/death/destroy 不产生/消灭持有者记录**（v0 spec-literal）：CA703 的持有者来源只有 owns 断言与更早的 transfer/grant。grant 算持有者来源（D2 自己定义 grant 为「名分转移」）。
7. **腿写坏形状（如 `by: notalist`）→ CA109 error**，该腿仍算「声明过」（CA702 不因同一条腿双报），但取不出 id、不参与 CA401/CA705。
8. **导出（`export`/`serve.py`）v0 不动**：`_entry_export` 不加事件字段。前端还不存在，YAGNI；要加是另一个任务。

## Global Constraints

- 依赖只有 pyyaml；不许引入新依赖。
- `store/` 不许出现政治经济学/判定理论词汇（`tests/test_store.py` AST 守卫）；事件字段名（`when`/`when_sort`/`event_kind`/`by`/`to`/`object`）是中性词，可以进 FIELD_TABLE。
- 规则编号即协议：新增编号只有 CA701–CA706；不许重编号或复用现有编号。
- `report` 级输出（`ledger` 子命令）**永不进退出码**——与 `--impact` 同一条纪律。
- `--strict` 只改退出码不改判定；CA706/CA701/CA703/CA705 是 warning，CA702/CA704 是 error，级别照 spec D7，不许自行升降。
- 快照逐字节冻结（`tests/snapshots/*.txt`，首行 `exit=N`）；任何输出文案改动都会变红，属预期内变更才 `--update`。
- 文档数字被 `tests/test_docs.py` 钉死：README/CONTRIBUTING 的规则条数、检查项数、夹具数必须与实测一致；PROTOCOL.md §6.3 规则表与代码双向一致。
- 文案风格：发现（Finding）的 message 用中文、讲清「为什么/怎么办」，照 `canonlint.py` 现有口吻。
-  git 提交信息用中文，风格照 `git log`（如「锁上 CA503 的义务，而不只是它的豁免」）。

## Review Focus

spec 没说、但最可能咬人的输入（每条都已在任务里配了测试）：

1. **旧世界的 27 张史料事件卡**（无 `when`/`event_kind`）必须一条不红（D9 硬要求）→ Task 3 extras `check_historical_event_cards_stay_silent`；既有快照（world-arrakis/world-middle-earth/world-westeros）在 Task 5 之前**一字节不许动**。
2. **完整事件缺 `when_sort`**：四条时序/账平规则必须全部静默，不许猜顺序 → Task 3 extras `check_ledger_fail_open_without_when_sort`。
3. **`when_sort` 相等**：CA701 用 `≤`（并列合法），CA705 用严格 `<`（同刻死亡不算「死后做事」）→ Task 3 extras `check_equal_sort_boundaries`。
4. **腿形状写坏**：`by: notalist` 报 CA109 且不叠 CA702（不双报）→ Task 3 extras `check_leg_shape_is_ca109_not_double_ca702`。
5. **owns 断言与流水并存**：有流水的客体才比对最终持有者；断言正好等于最终持有者的世界必须全绿 → Task 3 夹具 `world-ledger`（全绿基准）与 `world-ledger-bad`（CA704 反例）。
6. **`ledger` 子命令跑在有 error 的世界上也 exit 0**，且一个字节不写盘 → Task 4 extras `check_ledger_command_is_readonly_report`。

---

### Task 1: 契约与存储字段面（六个事件字段可存、可验）

**Files:**
- Modify: `world.schema.json`（properties、x-strict-vocabulary、x-contract-version、description 尾部）
- Modify: `store/model.py:82-98`（字段表区）
- Modify: `canonlint.py:37-38`（CONTRACT_VERSION；顺手加 `import ledger` 之前的准备工作本任务不做）
- Test: `tests/test_schema.py`（词表钉法 + 严格层执行）

**Interfaces:**
- Produces: `store/model.py` 的 `EVENT_FIELDS = ("when", "when_sort", "event_kind", "by", "to", "object")`；FIELD_TABLE 包含它。契约 `properties` 新增六个键；`x-strict-vocabulary.event_kind` 八值列表。后续任务依赖这些名字逐字不变。

- [ ] **Step 1: 先写会红的测试**

在 `tests/test_schema.py` 的 `check_vocabulary_matches_code`（约 254-266 行）的词表元组列表里加一行（此时红，因为契约和代码都还没有 event_kind）：

```python
        ("x-strict-vocabulary.event_kind", sv["event_kind"],
         ledger.EVENT_KINDS, True),
```

文件顶部 import 区加 `import ledger`（`ledger.py` 还不存在 → 红）。`tests/test_schema.py` 的 `strict_problems`（约 143-154 行）的词表执行元组改成：

```python
    for field, values, x_ok in (("type", sv["type"], True),
                                ("status", sv["status"], False),
                                ("layer", sv["layer"], False),
                                ("event_kind", sv["event_kind"], True)):
```

Run: `python3 tests/test_schema.py`
Expected: FAIL（`ModuleNotFoundError: ledger` 或 KeyError: 'event_kind'）

- [ ] **Step 2: 改契约 `world.schema.json`**

- `x-contract-version`: `"0.2"` → `"0.3"`。
- `title` 改「世界文件契约 v0.3」。
- `properties` 里 `superseded_by` 之后插入：

```json
    "when": {"type": "string"},
    "when_sort": {"type": "number"},
    "event_kind": {"type": "string"},
    "by": {"type": "array", "items": {"$ref": "#/$defs/id"}},
    "to": {"type": "array", "items": {"$ref": "#/$defs/id"}},
    "object": {"type": "array", "items": {"$ref": "#/$defs/id"}},
```

- `x-strict-vocabulary` 里 `depends_on.kind-exception` 之后加：

```json
    "event_kind": ["birth", "create", "custody", "death", "destroy", "grant", "move", "transfer"],
    "event_kind-exception": "以 x- 开头的实验值合法（CA102 记 info），与 type/kind 同一套泄压阀（协议 1.2）。实验值的腿表未知，不进 CA702–CA705 判定。",
```

- `x-stricter-than-contract` 列表末尾追加一条：

```json
    "事件字段（when/when_sort/event_kind/by/to/object）：本契约只约束形状；event_kind 词表、必填腿、时序与账平是判定层的事（CA102/CA109/CA401/CA701–CA706），classlint 不判事件。",
```

- 注意 `json_schema_subset.py` 是 fail-loud 的：本步只用了已支持的关键字（`type`/`array`/`items`/`$ref`），若校验器报 `UnsupportedKeyword` 说明用超了，退回去。

- [ ] **Step 3: 存储字段面 + 占位常量让 Step 1 的钉法转绿**

`store/model.py` 在 `ANNOTATION_FIELDS` 后加：

```python
# 事件流水字段（协议 1.2）：存储层只认「有这些键」，词表与腿表是判定层的事
EVENT_FIELDS = ("when", "when_sort", "event_kind", "by", "to", "object")
```

`FIELD_TABLE` 改为：

```python
FIELD_TABLE = (frozenset(CORE_REQUIRED_FIELDS) | frozenset(ANNOTATION_FIELDS)
               | frozenset(LEGACY_RELATION_FIELDS) | {RELATIONS_FIELD}
               | frozenset(EVENT_FIELDS))
```

新建 `ledger.py`（本任务只放常量，函数后续任务加）：

```python
"""事件流水（协议 1.2）——事件字段解析与派生状态。

卡片是账户，事件是流水，现在的状态是算出来的（docs/事件流水设计.md）。
本模块只提供判定原料：事件长什么样、流水按什么顺序、每个客体最后在谁手里。
判语（什么算错）在 canonlint.py 的 CA7xx；本模块不出现任何规则编号。
"""
from __future__ import annotations

EVENT_KINDS = {"transfer", "custody", "move", "create", "destroy",
               "grant", "birth", "death"}
```

`canonlint.py`：`CONTRACT_VERSION = "0.2"` → `"0.3"`（行尾注释不变）。

- [ ] **Step 4: 跑三套验证转绿且无副作用**

Run: `python3 tests/test_schema.py && python3 tests/test_store.py && python3 tests/run_tests.py`
Expected: 全 PASS。特别核对：`tests/run_tests.py` 的所有快照**一字节未动**（事件字段没出现在任何旧夹具里，D9）；`tests/test_serve.py` 若因 `contract_version` 文档样本变红，把 `docs/接口说明.md` 与 `docs/给前端的说明.md` 里的 `"contract_version": "0.2"` 改成 `"0.3"`（这是文档钉代码的既有机制，属预期内联动）。

- [ ] **Step 5: Commit**

```bash
git add world.schema.json store/model.py canonlint.py ledger.py tests/test_schema.py docs/接口说明.md docs/给前端的说明.md docs/事件流水设计.md
git commit -m "契约 0.3：事件流水六个字段可存可验（协议 1.2 字段面）"
```

（`docs/事件流水设计.md` 是 spec，顺手入库；后两个 docs 文件只有实际变红时才 add。）

---

### Task 2: ledger.py——事件解析与派生状态（纯函数）

**Files:**
- Modify: `ledger.py`（Task 1 已建常量）
- Test: `tests/run_tests.py`（本任务的测试夹在上层任务里走夹具；本任务自身的边界行为由 Task 3 的 extras 覆盖，不写独立单测——仓库惯例是夹具驱动）

**Interfaces:**
- Consumes: `store.Entry`（`.meta`、`.parse_error`、`.id`、`.rel`、`edges_of("owns")`）
- Produces（后续任务逐字依赖）:
  - `ledger.EVENT_KINDS: set[str]`（已有）
  - `ledger.REQUIRED_LEGS: dict[str, tuple[str, ...]]`
  - `ledger.LEG_FIELDS = ("by", "to", "object")`
  - `ledger.EventView` dataclass：字段 `kind, when, when_sort, legs, declared, shape_errors`
  - `ledger.event_view(e: Entry) -> EventView`
  - `ledger.is_experimental_kind(kind) -> bool`
  - `ledger.is_complete_event(v: EventView) -> bool`
  - `ledger.ordered_events(index) -> list[tuple[Entry, EventView]]`（完整事件且有 when_sort，按 `(when_sort, id)` 确定序）
  - `ledger.ObjectState` dataclass：`holder, holder_source, custodian, location`
  - `ledger.derive_state(index) -> dict[str, ObjectState]`

- [ ] **Step 1: 实现事件视图与腿表**

`ledger.py` 追加：

```python
from dataclasses import dataclass

from store import Entry

REQUIRED_LEGS: dict[str, tuple[str, ...]] = {
    "transfer": ("by", "to", "object"),
    "custody": ("by", "to", "object"),
    "grant": ("by", "to", "object"),
    "move": ("object", "to"),
    "create": ("object",),
    "destroy": ("object",),
    "birth": ("object",),
    "death": ("object",),
}
LEG_FIELDS = ("by", "to", "object")


@dataclass
class EventView:
    """一张卡作为「事件」的视图。字段缺席与写坏是两回事：写坏的腿由判定层
    报 CA109，但它仍算「声明过」（CA702 不双报），只是取不出 id。"""
    kind: object                 # event_kind 原值（非字符串也留着，给 CA102 报）
    when: object                 # when 原值
    when_sort: float | None      # 合法数字才是数字，否则 None（fail-open）
    legs: dict[str, list[str]]   # 形状合法的腿 → id 列表
    declared: set[str]           # 作者写过的腿（含写坏的、含空列表）
    shape_errors: list[str]      # 人读的形状问题（判定层包成 CA109）


def event_view(e: Entry) -> EventView:
    meta = e.meta
    legs: dict[str, list[str]] = {}
    declared: set[str] = set()
    errors: list[str] = []
    for leg in LEG_FIELDS:
        if leg not in meta:
            continue
        declared.add(leg)
        raw = meta[leg]
        if not isinstance(raw, list):
            errors.append(f"事件的 `{leg}` 必须是 id 列表")
            continue
        ids: list[str] = []
        for i, item in enumerate(raw):
            if not isinstance(item, str):
                errors.append(f"事件的 `{leg}[{i}]` 必须是 id 字符串，得到 {item!r}")
                continue
            ids.append(item)
        legs[leg] = ids
    ws = meta.get("when_sort")
    if ws is not None and (not isinstance(ws, (int, float)) or isinstance(ws, bool)):
        errors.append(f"when_sort={ws!r} 必须是数字（可选排序键，不给就不参与时序判定）")
        ws = None
    when = meta.get("when")
    if when is not None and not isinstance(when, str):
        errors.append(f"when={when!r} 必须是字符串（故事内时间，自由文本）")
    return EventView(meta.get("event_kind"), when, ws, legs, declared, errors)


def is_experimental_kind(kind) -> bool:
    return isinstance(kind, str) and kind.startswith("x-")


def is_complete_event(v: EventView) -> bool:
    """完整事件 = event_kind 落在词表里。x- 实验值是事件但腿表未知（不判腿）。"""
    return v.kind in EVENT_KINDS
```

- [ ] **Step 2: 实现排序与派生状态**

`ledger.py` 追加：

```python
@dataclass
class ObjectState:
    holder: str | None = None         # 当前持有者（owns 断言或 transfer/grant 推出）
    holder_source: str | None = None  # 来源条目/事件 id
    custodian: str | None = None      # 保管人（custody 推出；不改变持有者）
    location: str | None = None       # 位置（move 推出）


def ordered_events(index: dict[str, Entry]) -> list[tuple[Entry, EventView]]:
    """有 when_sort 的完整事件，按 (when_sort, id) 确定序。没有排序键的不进流水。"""
    out = []
    for e in index.values():
        if e.parse_error:
            continue
        v = event_view(e)
        if is_complete_event(v) and v.when_sort is not None:
            out.append((e, v))
    out.sort(key=lambda t: (t[1].when_sort, t[0].id or ""))
    return out


def derive_state(index: dict[str, Entry]) -> dict[str, ObjectState]:
    """期初断言（owns）+ 流水 → 每个客体的当前状态。只读，确定序。"""
    states: dict[str, ObjectState] = {}
    for e in sorted(index.values(), key=lambda x: x.id or ""):
        if e.parse_error or not e.id:
            continue
        for r in e.edges_of("owns"):
            st = states.setdefault(r.target, ObjectState())
            if st.holder is None:  # 多个 owns 断言并存时按 id 序取第一个；矛盾由 CA704 报
                st.holder, st.holder_source = e.id, e.id
    for e, v in ordered_events(index):
        for obj in v.legs.get("object", []):
            st = states.setdefault(obj, ObjectState())
            if v.kind in ("transfer", "grant") and v.legs.get("to"):
                st.holder, st.holder_source = v.legs["to"][0], e.id
            elif v.kind == "custody" and v.legs.get("to"):
                st.custodian = v.legs["to"][0]
            elif v.kind == "move" and v.legs.get("to"):
                st.location = v.legs["to"][0]
    return states
```

- [ ] **Step 3: 冒烟验证（不提交断言，只看能跑）**

Run: `python3 -c "import ledger; print(sorted(ledger.EVENT_KINDS)); print(ledger.REQUIRED_LEGS['transfer'])"`
Expected: 打印八值集合（排序后）与 `('by', 'to', 'object')`，无 traceback。

- [ ] **Step 4: Commit**

```bash
git add ledger.py
git commit -m "ledger.py：事件视图、流水排序与派生状态（判定原料，无判语）"
```

---

### Task 3: CA701–CA706 判定 + 事件腿 CA401/CA102/CA109 + 夹具与意图断言

**Files:**
- Modify: `canonlint.py`（新增 `check_events` / `check_ledger`；`check_refs` 加事件腿 CA401；`run()` 接线；`import ledger`）
- Create: `tests/make_ledger.py`（生成 `tests/world-ledger` 与 `tests/world-ledger-bad`）
- Create: `tests/world-ledger/`、`tests/world-ledger-bad/`（生成物，提交）
- Modify: `tests/run_tests.py`（CASES +4、extras +5）
- Create: `tests/snapshots/world-ledger.txt`、`world-ledger+strict.txt`、`world-ledger-bad.txt`

**Interfaces:**
- Consumes: Task 2 的 `ledger.*` 全部接口；`canonlint.Finding`、`store.collect`。
- Produces: `canonlint.check_events(e, findings)`、`canonlint.check_ledger(index, findings)`；Task 4 的 `ledger` 子命令将复用 `ledger.derive_state` 与 `check_ledger`。

- [ ] **Step 1: 先生成夹具（会红，因为规则还没实现）**

新建 `tests/make_ledger.py`（风格照 `tests/make_worlds.py`）。要点：每个条目都是合法契约形状（`world-ledger-bad` 的违规全是**语义**违规——契约只能管形状，形状违规会撞 `tests/test_schema.py` 的好语料校验，所以形状测试在 extras 的临时世界里做）。

```python
#!/usr/bin/env python3
"""生成事件流水夹具世界：world-ledger（全绿）与 world-ledger-bad（每条 CA7xx 至少踩一次）。

world-ledger 是流水族的**全绿基准**：owns 断言与流水推出的最终持有者全部对得上。
world-ledger-bad 的每个违规都保持契约形状合法（字段类型正确、id 语法正确），
只踩语义——形状违规归 tests/run_tests.py 的 extras 临时世界管。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent

BODY = "这是一段用于夹具的正文。" * 30  # >200 字，避免 CA104 噪声


def card(id, type_, extra="", status="canon"):
    return f"""---
id: {id}
title: {id}
type: {type_}
author: fixture
date: 2026-01-01
status: {status}
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
{extra}---

{BODY}
"""


def event(id, kind, when_sort, legs="", extra=""):
    return card(id, "event",
                f"when: 第 {when_sort:g} 年\nwhen_sort: {when_sort}\n"
                f"event_kind: {kind}\n{legs}{extra}")


CLEAN = {
    # 期初断言（owns 写在「当前持有者」卡上，与流水推出的最终持有者一致）
    "house-fox": card("house-fox", "faction", "owns:\n  - grey-rock\n"),
    "lord-anna": card("lord-anna", "character", "owns:\n  - fox-blade\n"),
    # owns 断言必须等于流水推出的最终持有者（CA704）：watch-command 经 grant 归 bob
    "squire-bob": card("squire-bob", "character", "owns:\n  - watch-command\n"),
    "grey-rock": card("grey-rock", "location"),
    "fox-blade": card("fox-blade", "item"),
    "watch-command": card("watch-command", "item"),
    "fox-host": card("fox-host", "faction"),
    "east-gate": card("east-gate", "location"),
    # 流水（8 笔，覆盖全部八类 event_kind）
    "ev-bob-born": event("ev-bob-born", "birth", 0, "object:\n  - squire-bob\n"),
    "ev-blade-forged": event("ev-blade-forged", "create", 1, "object:\n  - fox-blade\n"),
    "ev-blade-to-anna": event(
        "ev-blade-to-anna", "transfer", 2,
        "by:\n  - house-fox\nto:\n  - lord-anna\nobject:\n  - fox-blade\n",
        "depends_on:\n  - {id: ev-blade-forged, kind: production, critical: false}\n"),
    "ev-command-granted": event(
        "ev-command-granted", "grant", 3,
        "by:\n  - house-fox\nto:\n  - squire-bob\nobject:\n  - watch-command\n"),
    "ev-blade-in-keep": event(
        "ev-blade-in-keep", "custody", 4,
        "by:\n  - lord-anna\nto:\n  - house-fox\nobject:\n  - fox-blade\n"),
    "ev-host-marches": event(
        "ev-host-marches", "move", 5,
        "object:\n  - fox-host\nto:\n  - east-gate\n"),
    "ev-old-lord-dies": event("ev-old-lord-dies", "death", 6, "object:\n  - lord-anna\n"),
    "ev-keep-burned": event("ev-keep-burned", "destroy", 7, "object:\n  - east-gate\n"),
}

BAD = {
    "house-a": card("house-a", "faction", "owns:\n  - castle-x\n"),
    "house-b": card("house-b", "faction"),
    "castle-x": card("castle-x", "location"),
    "orphan-item": card("orphan-item", "item"),
    "old-knight": card("old-knight", "character"),
    "sword-y": card("sword-y", "item"),
    # CA706：只给 when，不给 event_kind
    "ev-half": card("ev-half", "event", "when: 某年\n"),
    # CA102：event_kind 非词表且不带 x- 前缀（形状合法：是字符串）
    "ev-bad-kind": card("ev-bad-kind", "event",
                        "when: 某年\nevent_kind: teleport\nwhen_sort: 1\n"),
    # CA102 info：x- 实验 event_kind（不判腿、不进派生）
    "ev-x-kind": card("ev-x-kind", "event",
                      "when: 某年\nevent_kind: x-mine-teleport\nwhen_sort: 2\n"),
    # CA702：transfer 缺 to 这条腿
    "ev-missing-leg": event("ev-missing-leg", "transfer", 3,
                            "by:\n  - house-a\nobject:\n  - sword-y\n"),
    # CA704：house-a 断言 owns castle-x，但最后一笔 transfer 把它给了 house-b
    "ev-castle-to-b": event(
        "ev-castle-to-b", "transfer", 4,
        "by:\n  - house-a\nto:\n  - house-b\nobject:\n  - castle-x\n"),
    # CA705：old-knight 在 5 已 death，7 的事件 by 里还有他
    "ev-knight-dies": event("ev-knight-dies", "death", 5, "object:\n  - old-knight\n"),
    "ev-knight-acts": event(
        "ev-knight-acts", "move", 7,
        "by:\n  - old-knight\nobject:\n  - sword-y\nto:\n  - castle-x\n"),
    # CA703：orphan-item 无任何 owns 断言、无更早 transfer，却被 transfer
    "ev-no-source": event(
        "ev-no-source", "transfer", 8,
        "by:\n  - house-a\nto:\n  - house-b\nobject:\n  - orphan-item\n"),
    # CA701：when_sort=9 的事件 depends_on when_sort=11 的事件（时序倒流，B > A）
    "ev-late-dep": event(
        "ev-late-dep", "destroy", 9, "object:\n  - sword-y\n",
        "depends_on:\n  - {id: ev-ghost, kind: resource, critical: false}\n"),
    # CA401：腿指向幽灵 id（契约形状合法：id 语法正确，只是不存在）
    "ev-ghost": event("ev-ghost", "move", 11,
                      "object:\n  - sword-y\nto:\n  - ghost-place\n"),
}


def write_world(name, entries):
    path = ROOT / name
    if path.exists():
        shutil.rmtree(path)
    (path / "entries").mkdir(parents=True)
    for id, text in entries.items():
        (path / "entries" / f"{id}.md").write_text(text, encoding="utf-8")


write_world("world-ledger", CLEAN)
write_world("world-ledger-bad", BAD)
print(f"world-ledger: {len(CLEAN)} entries, world-ledger-bad: {len(BAD)} entries")
```

注意 `BAD` 里先写后覆盖的写法是为了让每一行注释可读；实现时直接写成最终形态亦可，但上面列出的触发矩阵（哪张卡踩哪条规则）**不许改**。

Run: `python3 tests/make_ledger.py && python3 canonlint.py tests/world-ledger; python3 canonlint.py tests/world-ledger-bad`
Expected: world-ledger exit 0（旧规则不该响）；world-ledger-bad 有 CA401（幽灵腿**还没接**，此时不报）等——此时 CA7xx 一条都没有，这就是要变红的地方。

- [ ] **Step 2: 在 run_tests.py 加快照用例与五条意图断言（此时红）**

`CASES` 列表末尾加：

```python
    # 事件流水（协议 1.2）：world-ledger 是流水族的全绿基准（默认与 --strict 都 exit 0）；
    # world-ledger-bad 把 CA701–CA706 每条至少踩一次（触发矩阵见 tests/make_ledger.py）。
    ("world-ledger", ["tests/world-ledger"]),
    ("world-ledger+strict", ["tests/world-ledger", "--strict"]),
    ("world-ledger-bad", ["tests/world-ledger-bad"]),
```

`tests/run_tests.py` 追加五个 extras 检查函数，并登记进 `main()` 的 `extras` 列表：

```python
def check_historical_event_cards_stay_silent() -> list[str]:
    """D9 硬要求：没有 when/event_kind 的史料事件卡，一条 CA7xx 都不许响。

    示例世界里那 27 张 type: event 卡（起源、改编、文献）不是流水事件；
    协议 1.1 的世界在 1.2 下必须仍然全绿。
    """
    problems = []
    # _card 固定 type: location；史料事件卡拿它的模板换个 type
    tmp, world = _temp_world("canonlint-hist-event-", {
        "old-lore": _card("old-lore", "").replace("type: location", "type: event"),
    })
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"史料事件卡把 traceback 写到了 stderr：\n{err}")
        if re.search(r"\[CA70[1-6]\]", out):
            problems.append(f"史料事件卡（无 when/event_kind）触发了流水规则：\n{out}")
        if code != 0:
            problems.append(f"纯史料事件卡的世界应当 exit 0，实际 {code}：\n{out}")
    return problems


def check_ledger_fail_open_without_when_sort() -> list[str]:
    """缺 when_sort = 全部时序/账平规则 fail-open（D2：不给就不参与时序判定）。

    一个 depends_on 指向「更晚」事件、客体没有来源的完整事件，只要没给
    when_sort，CA701/CA703 都必须静默——排不了序就猜一个顺序，比不判更坏。
    """
    problems = []
    cards = {
        "ghostless-item": _card("ghostless-item", ""),
        "ev-no-sort": _card("ev-no-sort", (
            "when: 某年\nevent_kind: transfer\n"
            "by:\n  - somebody\nto:\n  - somebody\nobject:\n  - ghostless-item\n"
            "depends_on:\n  - {id: ev-later, kind: resource, critical: false}\n"
        )).replace("type: location", "type: event"),
        "ev-later": _card("ev-later", (
            "when: 另一年\nevent_kind: create\nwhen_sort: 99\n"
            "object:\n  - ghostless-item\n"
        )).replace("type: location", "type: event"),
        "somebody": _card("somebody", ""),
    }
    tmp, world = _temp_world("canonlint-nosort-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"无 when_sort 的世界把 traceback 写到了 stderr：\n{err}")
        if re.search(r"\[CA70[1345]\]", out):
            problems.append(f"缺 when_sort 时 CA701/CA703/CA704/CA705 必须静默：\n{out}")
    return problems


def check_equal_sort_boundaries() -> list[str]:
    """when_sort 相等：CA701 用 ≤（并列合法），CA705 用严格 <（同刻不算死后）。"""
    problems = []
    cards = {
        "person-a": _card("person-a", ""),
        "thing-x": _card("thing-x", ""),
        "ev-a": _card("ev-a", (
            "when: 同年\nevent_kind: death\nwhen_sort: 5\nobject:\n  - person-a\n"
        )).replace("type: location", "type: event"),
        "ev-b": _card("ev-b", (
            "when: 同年\nevent_kind: move\nwhen_sort: 5\n"
            "by:\n  - person-a\nobject:\n  - thing-x\nto:\n  - person-a\n"
            "depends_on:\n  - {id: ev-a, kind: resource, critical: false}\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-eqsort-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"等值 when_sort 把 traceback 写到了 stderr：\n{err}")
        if "CA701" in out:
            problems.append(f"when_sort 相等不该报 CA701（规则是 ≤）：\n{out}")
        if "CA705" in out:
            problems.append(f"同刻死亡不算「死人做活事」（规则是严格更早）：\n{out}")
    return problems


def check_leg_shape_is_ca109_not_double_ca702() -> list[str]:
    """腿写坏形状（by 不是列表）报 CA109；这条腿算「声明过」，不叠 CA702。"""
    problems = []
    cards = {
        "thing-x": _card("thing-x", ""),
        "keep-y": _card("keep-y", ""),
        # move 的必填腿是 object + to（都给了，不触发 CA702）；
        # by 不是必填腿，写坏形状只该报 CA109
        "ev-bad-shape": _card("ev-bad-shape", (
            "when: 某年\nevent_kind: move\nwhen_sort: 1\n"
            "by: notalist\nobject:\n  - thing-x\nto:\n  - keep-y\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legshape-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"坏形状腿把 traceback 写到了 stderr：\n{err}")
        if "CA109" not in out:
            problems.append(f"by: notalist 没报 CA109（形状坏掉不许静默）：\n{out}")
        if "CA702" in out:
            problems.append(f"坏形状腿又叠了一条 CA702（同一句话报两遍）：\n{out}")
    return problems


def check_ledger_bad_world_fires_every_rule() -> list[str]:
    """变异验证的骨架：world-ledger-bad 必须真的把六条新规则每条至少踩一次。

    快照只证明「没变」，这条证明「守卫在生效」——某条规则被改哑（比如把
    error 降级、把比较方向写反成 >=），这里就变红。
    """
    problems = []
    code, out, err = _judge(HERE / "world-ledger-bad")
    if err:
        problems.append(f"world-ledger-bad 把 traceback 写到了 stderr：\n{err}")
    for rule in ("CA701", "CA702", "CA703", "CA704", "CA705", "CA706",
                 "CA102", "CA401"):
        if f"[{rule}]" not in out:
            problems.append(f"world-ledger-bad 没有触发 {rule}（触发矩阵失效）：\n{out}")
    if code != 1:
        problems.append(f"world-ledger-bad 有 error 应当 exit 1，实际 {code}")
    return problems
```

`main()` 的 `extras` 列表末尾登记：

```python
        ("史料事件卡（无 when/event_kind）一条 CA7xx 都不响（D9）", check_historical_event_cards_stay_silent),
        ("缺 when_sort 时时序/账平规则 fail-open", check_ledger_fail_open_without_when_sort),
        ("when_sort 相等：CA701 合法、CA705 不算死后", check_equal_sort_boundaries),
        ("腿形状写坏报 CA109、不叠 CA702", check_leg_shape_is_ca109_not_double_ca702),
        ("world-ledger-bad 把六条流水规则每条至少踩一次", check_ledger_bad_world_fires_every_rule),
```

Run: `python3 tests/run_tests.py`
Expected: 新增的 3 个快照用例报「缺少快照」，5 条 extras 里至少 `check_ledger_bad_world_fires_every_rule` 红（规则还不存在）。

- [ ] **Step 3: 实现 `canonlint.py` 的判定**

`canonlint.py` 头部 import 区加 `import ledger`。

在 `check_content` 之后加单条目部分：

```python
def check_events(e: Entry, findings: list[Finding]) -> None:
    """CA7xx 的单条目部分 + 事件字段形状（CA109）与 event_kind 词表（CA102）。

    「给了 event_kind 才算完整事件」（D2）；when 与 event_kind 只给一个
    是半截事件（CA706）。x- 实验 event_kind 与 type/kind 同一套泄压阀：
    记 info、不判腿、不进派生，但 CA701 时序照算（时序不看 kind）。
    """
    if e.parse_error:
        return
    rel = e.rel
    v = ledger.event_view(e)
    for msg in v.shape_errors:
        findings.append(Finding("CA109", "error", rel, msg))
    has_when = "when" in e.meta
    has_kind = "event_kind" in e.meta
    if has_kind:
        if not isinstance(v.kind, str):
            findings.append(Finding("CA102", "error", rel,
                                    f"event_kind={v.kind!r} 必须是字符串"))
        elif v.kind not in ledger.EVENT_KINDS:
            if ledger.is_experimental_kind(v.kind):
                findings.append(Finding("CA102", "info", rel,
                                        f"event_kind={v.kind!r} 为实验值（x- 前缀），已计入案例收集"))
            else:
                findings.append(Finding(
                    "CA102", "error", rel,
                    f"event_kind={v.kind!r} 非法，须为 {sorted(ledger.EVENT_KINDS)}"
                    f"（实验值须形如 `x-<命名空间>-<名称>`）"))
    if has_when != has_kind:
        findings.append(Finding("CA706", "warning", rel,
                                "半截事件：`when` 与 `event_kind` 只给了一个"
                                "（两个都给才进流水判定，都不给就是普通史料卡）"))
    if not ledger.is_complete_event(v):
        return
    for leg in ledger.REQUIRED_LEGS[v.kind]:
        if leg not in v.declared:
            findings.append(Finding(
                "CA702", "error", rel,
                f"{v.kind} 事件缺腿 `{leg}`（必填：{list(ledger.REQUIRED_LEGS[v.kind])}）——账不平"))
        elif leg in v.legs and not v.legs[leg]:
            findings.append(Finding("CA702", "error", rel,
                                    f"{v.kind} 事件的 `{leg}` 是空列表——账不平"))
        # 腿声明过但形状写坏：CA109 已报，这里不双报
```

在 `check_refs` 里 `superseded_by` 检查块之后加事件腿的存在性检查：

```python
        # 事件腿（by/to/object，协议 1.2）的悬空引用与关系边同罪：
        # 「指向不存在的 id 是结构问题」不因字段归属而改变（v1.1 修订第 16 条的同一原则）
        for leg in ledger.LEG_FIELDS:
            for ref_id in ledger.event_view(e).legs.get(leg, []):
                check_target(ref_id, leg)
```

在 `check_chain` 之后加跨条目部分：

```python
def check_ledger(index: dict[str, Entry], findings: list[Finding]) -> None:
    """CA7xx 的跨条目部分：时序与账平。缺 when_sort 一律 fail-open（D2）。

    CA703/CA704 的持有者口径见 ledger.derive_state：owns 断言是无时间的
    「有持有者」证据（D3），transfer/grant 推出新的最终持有者；断言与最终
    持有者打架是 CA704（error），客体从无来源是 CA703（warning）。
    """
    events = ledger.ordered_events(index)

    def is_event(v: ledger.EventView) -> bool:
        return ledger.is_complete_event(v) or ledger.is_experimental_kind(v.kind)

    # CA701: 事件 A depends_on 事件 B，两边都有 when_sort 时要求 B ≤ A
    for e in index.values():
        if e.parse_error:
            continue
        va = ledger.event_view(e)
        if va.when_sort is None or not is_event(va):
            continue
        for d in e.edges_of("depends_on"):
            b = index.get(d.target)
            if b is None or b.parse_error:
                continue  # 悬空由 CA401 报
            vb = ledger.event_view(b)
            if vb.when_sort is None or not is_event(vb):
                continue
            if vb.when_sort > va.when_sort:
                findings.append(Finding(
                    "CA701", "warning", e.rel,
                    f"时序倒流：本事件 when_sort={va.when_sort:g}，"
                    f"depends_on 的事件 `{b.id}` when_sort={vb.when_sort:g}（要求 ≤ 本事件）"))

    # CA703: transfer/grant 的客体在它之前没有任何持有者
    # （owns 断言是无时间的「有持有者」证据；更早的 transfer/grant 也算）
    held: set[str] = set()
    for e in index.values():
        if not e.parse_error:
            held.update(r.target for r in e.edges_of("owns"))
    for e, v in events:
        if v.kind in ("transfer", "grant"):
            for obj in v.legs.get("object", []):
                if obj not in held:
                    findings.append(Finding(
                        "CA703", "warning", e.rel,
                        f"无源之财：{v.kind} 的客体 `{obj}` 在它之前没有任何持有者"
                        f"（既无 owns 断言，也无更早的 transfer/grant 指向它）"))
            held.update(v.legs.get("object", []))

    # CA704: 手写 owns 断言与流水推出的最终持有者打架
    # （只对有流水的客体比对；无流水的客体，断言即全部历史）
    states = ledger.derive_state(index)
    transferred = {obj for e, v in events if v.kind in ("transfer", "grant")
                   for obj in v.legs.get("object", [])}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for r in e.edges_of("owns"):
            if r.target not in transferred:
                continue
            st = states.get(r.target)
            if st is not None and st.holder is not None and st.holder != e.id:
                findings.append(Finding(
                    "CA704", "error", e.rel,
                    f"结论与流水打架：卡上断言 owns `{r.target}`，但流水推出的"
                    f"最终持有者是 `{st.holder}`（来自事件 `{st.holder_source}`）"))

    # CA705: 事件的 by 里有人在更早的事件里已 death（同刻不算，严格 <）
    deaths: dict[str, float] = {}
    for e, v in events:
        if v.kind == "death":
            for obj in v.legs.get("object", []):
                deaths[obj] = min(deaths.get(obj, v.when_sort), v.when_sort)
    for e, v in events:
        if v.kind == "death":
            continue
        for actor in v.legs.get("by", []):
            if actor in deaths and deaths[actor] < v.when_sort:
                findings.append(Finding(
                    "CA705", "warning", e.rel,
                    f"死人做活事：`{actor}` 在 when_sort={deaths[actor]:g} 的事件里"
                    f"已 death，却在更晚的本事件（when_sort={v.when_sort:g}）的 by 里"))
```

`run()` 里接线（`check_chain(index, findings)` 之后）：

```python
    for e in all_entries:
        check_events(e, findings)
    check_ledger(index, findings)
```

注意：`check_refs(all_entries, index, findings)` 必须在 `check_events` 之前或之后都行，但事件腿 CA401 写在 `check_refs` 内部，随它一起跑。

- [ ] **Step 4: 生成快照并跑全套**

Run: `python3 tests/run_tests.py --update && python3 tests/run_tests.py`
Expected: 全 PASS。逐条肉眼核对三个新快照：
- `world-ledger.txt` / `world-ledger+strict.txt`：exit=0，零 findings（全绿基准，两种模式）；
- `world-ledger-bad.txt`：exit=1，触发矩阵里每条规则至少一次，CA704 文案指明「流水推出的最终持有者是 house-b」。
再跑 `python3 tests/test_schema.py && python3 tests/test_store.py && python3 tests/test_serve.py && python3 classlint/tests/run_tests.py`：全 PASS（新夹具世界的每张卡都过契约；classlint 不受 FIELD_TABLE 新增影响）。

- [ ] **Step 5: Commit**

```bash
git add canonlint.py tests/make_ledger.py tests/world-ledger tests/world-ledger-bad tests/run_tests.py tests/snapshots/
git commit -m "CA701–CA706：事件流水的六条判定与全绿/全踩夹具"
```

---

### Task 4: `canonlint ledger <世界>` 只读子命令

**Files:**
- Modify: `canonlint.py`（`main()` 子命令表、epilog；新增 `ledger_report()`）
- Modify: `tests/run_tests.py`（CASES +1、extras +1）
- Create: `tests/snapshots/world-ledger+ledger.txt`

**Interfaces:**
- Consumes: `ledger.derive_state`、`ledger.ordered_events`、`check_ledger`（Task 3）、`store.collect`。
- Produces: `canonlint.ledger_report(root: Path) -> int`（永远 return 0；目录不存在等用法错误 return 2）。

- [ ] **Step 1: 先加快照用例与意图断言（此时红）**

`CASES` 末尾加：

```python
    # ledger 子命令是 report 级输出：快照钉住报告形状，钉住它 exit 0
    ("world-ledger+ledger", ["ledger", "tests/world-ledger"]),
```

`tests/run_tests.py` 追加：

```python
def check_ledger_command_is_readonly_report() -> list[str]:
    """ledger 子命令与 --impact 同一条纪律：报告级输出永不进退出码、永不写盘。

    在一个有 error 的世界上跑 ledger 也必须 exit 0；目录树的逐字节哈希
    前后一致（「跑一下 ledger 就算改好了」是这条纪律要防的误解）。
    """
    problems = []
    world = HERE / "world-ledger-bad"
    before = {p.relative_to(world): p.read_bytes()
              for p in sorted(world.rglob("*")) if p.is_file()}
    p = subprocess.run([PY, str(TOOL), "ledger", str(world)],
                       cwd=ROOT, capture_output=True, text=True)
    if p.stderr:
        problems.append(f"ledger 子命令把 traceback 写到了 stderr：\n{p.stderr}")
    if p.returncode != 0:
        problems.append(f"ledger 在有 error 的世界上也必须 exit 0，实际 {p.returncode}")
    if "派生状态" not in p.stdout:
        problems.append(f"ledger 输出里看不到派生状态：\n{p.stdout}")
    after = {p.relative_to(world): p.read_bytes()
             for p in sorted(world.rglob("*")) if p.is_file()}
    if before != after:
        problems.append("ledger 子命令改动了世界目录（只读纪律被破坏）")
    return problems
```

登记 extras：`("ledger 子命令是只读报告（不改退出码、不写盘）", check_ledger_command_is_readonly_report),`

Run: `python3 tests/run_tests.py`
Expected: `world-ledger+ledger` 报缺少快照（子命令不存在 → 输出是用法错误），`check_ledger_command_is_readonly_report` 红。

- [ ] **Step 2: 实现子命令**

`canonlint.py` 的 `main()` 里把子命令表 `"init", "new", "link", "export"` 改为 `"init", "new", "link", "export", "ledger"`；在 `if cmd == "export"` 的 argparse 块之后加：

```python
        if cmd == "ledger":
            sp.add_argument("root_pos", type=Path, nargs="?", default=None,
                            help="世界仓库目录（位置参数，等价 --root）")
```

在 `if cmd == "export":` 处理块之后加：

```python
        if cmd == "ledger":
            root = (a.root_pos or a.root).resolve()
            if not root.is_dir():
                print(f"error: {root} 不是目录", file=sys.stderr)
                return 2
            return ledger_report(root)
```

新增函数（放在 `impact_report` 之后）：

```python
def ledger_report(root: Path) -> int:
    """`canonlint ledger <世界>`：打印派生状态与没算平的地方。

    与 --impact 同一条纪律：report 级输出，永不进退出码、永不写盘。
    「没算平的」复用 check_ledger 的判据（CA703/CA704/CA705），
    报告与门禁不许各说一套。
    """
    all_entries, index, _issues = store.collect(root)
    events = ledger.ordered_events(index)
    states = ledger.derive_state(index)
    findings: list[Finding] = []
    check_ledger(index, findings)
    n_entries = sum(1 for e in all_entries if not e.parse_error)
    print(f"{n_entries} 个条目 | {len(events)} 笔完整事件（有 when_sort 才进流水）")
    print("\n== 派生状态（期初断言 + 流水）==")
    if not states:
        print("(没有可派生的客体：没有 owns 断言，也没有完整事件)")
    for obj in sorted(states):
        st = states[obj]
        src = f"来自 `{st.holder_source}`" if st.holder_source else ""
        print(f"{obj}: 持有者 {st.holder or '（无）'}{src}"
              f" | 保管 {st.custodian or '-'} | 位置 {st.location or '-'}")
    unbalanced = [f for f in findings if f.rule in ("CA703", "CA704", "CA705")]
    print("\n== 没算平的 ==")
    if not unbalanced:
        print("(账平)")
    for f in unbalanced:
        print(f"[{f.rule}] {f.entry}: {f.message}")
    return 0
```

epilog 的「人类工作流子命令」帮助段加一行：

```
  canonlint ledger [目录]                          事件流水：派生状态与没算平的（只读报告）
```

- [ ] **Step 3: 生成快照，跑全套**

Run: `python3 tests/run_tests.py --update && python3 tests/run_tests.py`
Expected: 全 PASS。肉眼核对 `world-ledger+ledger.txt`：exit=0；派生状态里 `fox-blade` 持有者是 `lord-anna`（custody 不改持有者）、保管是 `house-fox`；`fox-host` 位置是 `east-gate`；「没算平的」是 `(账平)`。

- [ ] **Step 4: Commit**

```bash
git add canonlint.py tests/run_tests.py tests/snapshots/world-ledger+ledger.txt
git commit -m "canonlint ledger：只读的派生状态报告（与 --impact 同纪律）"
```

---

### Task 5: 冰火夹具补期初 + 流水（dogfood）

**Files:**
- Modify: `tests/make_worlds.py`（WE 字典加条目；新增 `evm()` 助手）
- Modify: `tests/world-westeros/`（重新生成的条目，提交）
- Modify: `tests/run_tests.py`（CASES +1）
- Create: `tests/snapshots/world-westeros+ledger.txt`
- Modify: `tests/snapshots/world-westeros.txt`（--update）

**Interfaces:**
- Consumes: 全部前面的实现。
- Produces: 真实作品的派生状态快照（`canonlint ledger tests/world-westeros`）。

- [ ] **Step 1: 给 make_worlds.py 加事件助手与新条目**

在 `fm()` 后加：

```python
def evm(id, kind, when, when_sort, body, legs="", status="canon"):
    """流水事件卡（协议 1.2）。legs 是 by/to/object 的 YAML 片段；
    body 必填且 ≥200 字（canon 事件卡同样受 CA104 篇幅约束，别给快照添噪声）。"""
    return f"""---
id: {id}
title: {id}
type: event
author: dataset-v1
date: 2026-09-23
status: {status}
load_bearing: false
when: {when}
when_sort: {when_sort}
event_kind: {kind}
{legs}canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---

{body}
"""
```

`write_world()` 目前解包九元组；改成：字典值是字符串时当整卡写（`evm` 产物），是元组时走老路（十元组，末尾是 owns）：

```python
    for id, spec in entries.items():
        if isinstance(spec, str):
            (path / "entries" / f"{id}.md").write_text(spec, encoding="utf-8")
            continue
        (type_, status, layer, lb, body, refs, conflicts, deps, owns) = spec
        ...（原逻辑不变，fm(...) 多传一个 owns=owns）
```

WE 新增条目（期初断言 + 9 笔流水；每笔正文 ≥200 字，用真实冰火设定，body 直接拼在卡片字符串尾）：

新卡（走 `fm` 老路，bodies 照现有 WE 文风；每条 ≥200 字）：

`fm()` 目前没有 owns 参数。改法：给 `fm` 加关键字参数 `owns="[]"`，**只在 `owns != "[]"` 时才写出那一行**（默认值的卡一个字节不变）；WE/ME 的条目元组从九元组扩成十元组（末尾加 owns），ME 的老条目全部补 `"[]"` 默认值。验证不变量：重新生成后 `git diff --stat tests/world-middle-earth` 必须为空——中土一个字节不许动。

- `house-tully`（faction/canon/political/False）：徒利家族，奔流城公爵，`owns: [riverrun]`。
- `riverrun`（location/canon/None/False）：奔流城。
- `eddard-stark`（character/canon/None/False）：`owns: [ice-sword]`。
- `robert-baratheon`（character/canon/None/False）：`owns: [iron-throne]`。
- `stannis-baratheon`（character/canon/None/False）：`owns: [stannis-loan-gold]`。
- `ice-sword`（item/canon/None/False）：寒冰巨剑。
- `stannis-loan-gold`（item/canon/None/False）：铁金库给史坦尼斯的贷款（资金拟物）。
- `house-stark`（faction/canon/None/False）：史塔克家族。**load_bearing 必须 False**——否则 CA302/CA503 会来要 layer 与物质 critical 依赖，「审计仍绿」就破了。
- `robb-host-army`（faction/canon/None/False）：萝卜的南下大军本体。同上，lb=False。
- `the-twins`（location/canon/None/False）：孪河城。

流水（`evm`，when_sort 用故事内纪年 AC）：

| id | kind | when_sort | by | to | object |
|---|---|---|---|---|---|
| ev-wall-built | create | -8000 | — | — | the-wall-scale |
| ev-riverrun-granted | grant | 1 | iron-throne | house-tully | riverrun |
| ev-ned-born | birth | 263 | — | — | eddard-stark |
| ev-robert-crowned | grant | 283 | iron-throne | robert-baratheon | iron-throne |
| ev-ice-to-ned | transfer | 290 | house-stark | eddard-stark | ice-sword |
| ev-ice-in-keep | custody | 297 | eddard-stark | house-stark | ice-sword |
| ev-robb-marches | move | 298 | — | the-twins | robb-host-army |
| ev-ned-executed | death | 299 | — | — | eddard-stark |
| ev-stannis-loan | transfer | 300 | iron-bank | stannis-baratheon | stannis-loan-gold |

**不变量（实现者必须逐条自检，这就是「审计仍绿」的含义）：**
- 每条 owns 断言 = 该客体流水推出的最终持有者（CA704 不触发）：riverrun→house-tully ✓、iron-throne→robert-baratheon ✓、ice-sword→eddard-stark（custody 不改持有者）✓、stannis-loan-gold→stannis-baratheon ✓。
- 每笔 transfer/grant 的客体都有 owns 断言（CA703 不触发）✓。
- 没有任何事件在 299 之后把 `eddard-stark` 写进 `by`（CA705 不触发）✓。
- 既有事件卡（`crown-debt-agot`、`cersei-default` 等）不加事件字段——它们是 D9 的活证据：真实世界里「史料事件」与「流水事件」并存，审计不红。

- [ ] **Step 2: 重新生成并验证全绿**

Run:
```bash
python3 tests/make_worlds.py
git diff --stat tests/world-middle-earth   # 必须为空：中土一个字节不许动
python3 canonlint.py tests/world-westeros
python3 canonlint.py ledger tests/world-westeros
```
Expected: world-westeros exit 0；无 CA7xx finding；新条目不引入新 warning（正文都 ≥200 字；若 `house-stark`/`robb-host-army` 触发 CA301/CA503，给它们补 `layer` 与正文说明或调整 load_bearing，保持输出干净）。ledger 输出里 `riverrun` 持有者是 `house-tully`、`ice-sword` 持有者是 `eddard-stark` 且保管是 `house-stark`、`robb-host-army` 位置是 `the-twins`。

- [ ] **Step 3: 快照更新与新增**

`CASES` 末尾加：

```python
    # 真实作品的流水：冰火世界补了期初与 9 笔账，ledger 输出是 dogfood 的验收物
    ("world-westeros+ledger", ["ledger", "tests/world-westeros"]),
```

Run: `python3 tests/run_tests.py --update && python3 tests/run_tests.py`
Expected: 全 PASS。肉眼核对 `world-westeros.txt` 的 diff：条目数 +19，无新 finding；`world-westeros+ledger.txt` 派生状态可读、exit=0。

- [ ] **Step 4: Commit**

```bash
git add tests/make_worlds.py tests/world-westeros tests/run_tests.py tests/snapshots/
git commit -m "冰火夹具补期初与九笔流水：真实作品的派生状态（dogfood）"
```

---

### Task 6: 文档、版本号与全量回归收口

**Files:**
- Modify: `canonlint.py:37`（`PROTOCOL_VERSION = "1.2"`）
- Modify: `PROTOCOL.md`（第 10/12 行、§2.2 字段表、§6.3 规则表、§6.5 示例、§9 加 v1.2 修订记录第 21 条）
- Modify: `README.md`（规则条数、检查项数、命令清单、现状、全绿基准说法）
- Modify: `CONTRIBUTING.md`（规则条数、夹具与检查项数）

**Interfaces:**
- Consumes: 全部前面的实现与实测数字。

- [ ] **Step 1: PROTOCOL.md**

- 第 10 行「规则表（§6.3，**27 条**）」→「**33 条**」；第 12 行 `PROTOCOL_VERSION = "1.1"` → `"1.2"`。
- §2.2 字段表（约 135-150 行，`| type | 必须 | enum | …` 那张表）末尾追加六行：

```markdown
| `when` | 可选 | string | 故事内时间，自由文本（协议 1.2 事件流水） |
| `when_sort` | 可选 | number | 时序排序键，只用于比较先后；不给就不参与时序判定（fail-open） |
| `event_kind` | 可选 | enum | 八值：`transfer`/`custody`/`move`/`create`/`destroy`/`grant`/`birth`/`death`；`x-` 前缀实验值合法（CA102 info）。给了它才是「完整事件」，才进流水判定 |
| `by` | 可选 | id 列表 | 事件腿：施动者 |
| `to` | 可选 | id 列表 | 事件腿：受方（转移的接手人、移动的目的地） |
| `object` | 可选 | id 列表 | 事件腿：客体（被转移/移动/造/毁的那个） |
```

- §6.3 规则表：CA102 行的枚举字段清单加 `event_kind`（`x-` 实验值降为 info）；CA401 行的覆盖清单加「事件腿 `by`/`to`/`object`」；CA504 行之后追加六行（级别与判据逐字照 spec D7，并写明 when_sort 缺席 fail-open、CA701 用 ≤、CA705 用严格 <、CA704 只对有流水的客体比对最终持有者）：

```markdown
| CA701 | warning | 时序倒流：事件 A 的 `depends_on` 里有事件 B，两边都有 `when_sort` 且 B > A（要求 B ≤ A，相等合法）。任一边缺 `when_sort` 即豁免 |
| CA702 | error | 账不平：完整事件的必填腿缺失或为空（`transfer`/`custody`/`grant` 要 `by`+`to`+`object`，`move` 要 `object`+`to`，其余要 `object`）。腿形状写坏归 CA109，不双报 |
| CA703 | warning | 无源之财：`transfer`/`grant` 的客体在它之前没有任何持有者（既无 `owns` 断言，也无更早的 `transfer`/`grant` 指向它）。事件自身缺 `when_sort` 即豁免 |
| CA704 | error | 结论与流水打架：手写 `owns` 断言与流水推出的最终持有者不一致（只对有 `transfer`/`grant` 流水的客体比对；无流水的客体断言即全部历史） |
| CA705 | warning | 死人做活事：事件的 `by` 里有人在**严格更早**（`when_sort` 较小）的事件里已 `death`；同刻不算 |
| CA706 | warning | 半截事件：`when` 与 `event_kind` 只给了一个。两个都给才是完整事件，都不给就是普通史料卡（协议 1.1 的世界在 1.2 下不红） |
```

- §6.5 JSON 示例里 `"protocol_version": "1.1"` → `"1.2"`。
- §9 的 v1.1 修订记录第 20 条之后，插入新小节：

```markdown
**v1.2 修订记录（2026-10-19，事件流水；设计决定见 docs/事件流水设计.md）：**

21. **世界是账本：事件流水进核心（CA701–CA706 + `canonlint ledger`）**。一张 `type: event` 的卡可以带六个新字段（`when`/`when_sort`/`event_kind`/`by`/`to`/`object`）变成「一笔账」：卡上断言是期初，事件是变化，现在的状态是算出来的。全部字段可选，只有「完整事件」（给了 `event_kind`）才进流水判定，缺 `when_sort` 一律 fail-open——协议 1.1 的世界在 1.2 下**一条不红**（有锁）。事件腿的悬空 id 报 CA401（修订第 16 条的同一原则），`event_kind` 词表与 `type`/`kind` 同一套 `x-` 泄压阀。`ledger` 子命令是 report 级输出：永不进退出码、永不写盘。
```

- [ ] **Step 2: 版本号 + README + CONTRIBUTING**

`canonlint.py:37`：`PROTOCOL_VERSION = "1.1"` → `"1.2"`（行尾注释改「1.2：事件流水六字段与 CA7xx（新增，按 §9.1 升 minor）」）。

README.md：
- 「27 条 CA 规则（`canonlint.py`）」→「33 条 CA 规则」（两处：命令表上方与「能判」行）；
- 「规则表（§6.3，27 条）」→「33 条」；
- 命令段在 `--impact` 行后加：
  ```
  python3 canonlint.py ledger ~/worlds/grey-harbor            # 事件流水：派生状态（只读，不进退出码）
  ```
- 现状段「能判」一行补上 CA7xx；「唯一的全绿基准是 `tests/world-clean`」改为「全绿基准是 `tests/world-clean`（结构）与 `tests/world-ledger`（流水），两种模式下都 exit 0」——把那段话连同退出码钉法说明一起改通顺；
- 「36 + 12 + 23 + 20 + 14 项检查」的第一个数字换成实测（跑 `python3 tests/run_tests.py` 看末行总数）。

CONTRIBUTING.md：
- 「那是 27 条规则的清单」→「33 条」；
- 「# 11 个世界夹具 + 36 项检查」换成实测的两个数（`len(CASES)` 与 run_tests 末行总数）。

- [ ] **Step 3: 全套回归（含文档钉法）**

Run:
```bash
python3 tests/run_tests.py && python3 tests/test_schema.py && python3 tests/test_store.py && \
python3 tests/test_serve.py && python3 tests/test_docs.py && python3 classlint/tests/run_tests.py
```
Expected: 六套全 PASS。`test_docs.py` 若报数字不符，以实测为准修文档（不许改测试迁就文档）。

- [ ] **Step 4: 变异验证**

对六条新规则各做一次「手术」并确认测试变红，然后 `git checkout` 还原：
1. CA701 的 `>` 改成 `<`（方向写反）→ `check_equal_sort_boundaries` 或 `world-ledger-bad` 红；
2. CA702 的腿表删掉 `to` → world-ledger 夹具红（全绿基准出现缺腿）；
3. CA704 的 `st.holder != e.id` 改成 `==` → `check_ledger_bad_world_fires_every_rule` 红；
4. CA705 的 `<` 改成 `<=` → `check_equal_sort_boundaries` 红；
5. CA706 的 `!=` 改成「两个都没有也报」→ `check_historical_event_cards_stay_silent` 红；
6. `ledger_report` 的 `return 0` 改成按 findings 返回 → `check_ledger_command_is_readonly_report` 红。

每一处都必须真的看到红再还原；任何一处不变红，回到对应 Task 补测试。

- [ ] **Step 5: Commit**

```bash
git add canonlint.py PROTOCOL.md README.md CONTRIBUTING.md
git commit -m "协议 1.2：事件流水文档收口（CA7xx 规则表、§9 修订第 21 条、版本号）"
```

---

## 完成后状态

- 六套测试全绿；新增 6 个快照用例、6 个 extras 意图断言；`world-ledger` 成为流水族全绿基准。
- 协议 1.2 / 契约 0.3；规则总数 27 → 33。
- 旧世界（含 27 张史料事件卡）一条不红，有快照与 extras 双锁。
- spec 里「这版不做什么」（时间区间、可能世界、作者断言显式标记、界面、酒馆导入）保持不做。
