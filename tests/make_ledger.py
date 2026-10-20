#!/usr/bin/env python3
"""生成事件流水夹具世界：world-ledger（全绿）与 world-ledger-bad（每条 CA7xx 至少踩一次）。

world-ledger 是流水族的**全绿基准**：owns 断言与流水推出的最终持有者全部对得上。
world-ledger-bad 的每个违规都保持契约形状合法（字段类型正确、id 语法正确），
只踩语义——形状违规归 tests/run_tests.py 的 extras 临时世界管。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


def card(id, type_, extra="", depends="[]", _i=[0]):
    """一张合法卡。正文用每张卡不同的字铺够 200+ 字——同一段样板会让 CA201 刷屏。"""
    _i[0] += 1
    body = f"{id} 的夹具正文。\n" + chr(0x4E00 + _i[0]) * 220 + "\n"
    return f"""---
id: {id}
title: {id}
type: {type_}
author: fixture
date: 2026-01-01
status: canon
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: {depends}
superseded_by: null
ai_assisted: false
{extra}---

{body}"""


def event(id, kind, when_sort, legs="", depends="[]"):
    return card(id, "event",
                f"when: 第 {when_sort:g} 年\nwhen_sort: {when_sort}\n"
                f"event_kind: {kind}\n{legs}",
                depends=depends)


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
        depends="\n  - {id: ev-blade-forged, kind: production, critical: false}"),
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
    # CA401：腿指向幽灵 id（契约形状合法：id 语法正确，只是不存在）
    "ev-ghost": event("ev-ghost", "move", 11,
                      "object:\n  - sword-y\nto:\n  - ghost-place\n"),
    # CA701：when_sort=9 的事件 depends_on when_sort=11 的事件（时序倒流，B > A）
    "ev-late-dep": event(
        "ev-late-dep", "destroy", 9, "object:\n  - sword-y\n",
        depends="\n  - {id: ev-ghost, kind: resource, critical: false}"),
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
