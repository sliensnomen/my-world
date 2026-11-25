#!/usr/bin/env python3
"""生成 1.4「事件优先」夹具世界 world-event-first（协议 1.33，CA721）。

卡片分工（docs/1.4-事件优先卡模型.md §5.5）：
- 被事件腿引用的实体卡（不报）：grey-town / blacksmith-tom / sword-a / buyer-jane
- 被事件卡 canon_refs 引用的实体卡（不报）：old-oak
- 未被任何事件引用的实体卡（报 CA721）：hermit-sage（trial）、draft-potion（draft）
- archived 实体卡未被引用（豁免，降级处置已终结它的账）：archived-banner
- 带治理字段（status / load_bearing + layer + 显式空 depends_on）的事件卡：ev-town-founded
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent

_i = [0]


def card(id, type_, extra="", status="canon", canon_refs="[]", depends="[]",
         load_bearing=False):
    """一张合法卡。正文每张卡铺不同的字，避免 CA201 刷屏（同 make_ledger.py）。"""
    _i[0] += 1
    lb = "true" if load_bearing else "false"
    body = f"{id} 的夹具正文。\n" + chr(0x4E00 + _i[0]) * 220 + "\n"
    return f"""---
id: {id}
title: {id}
type: {type_}
author: fixture
date: 2026-01-01
status: {status}
load_bearing: {lb}
{extra}canon_refs: {canon_refs}
conflicts_with: []
depends_on: {depends}
superseded_by: null
ai_assisted: false
---

{body}"""


def event(id, kind, when_sort, legs="", status="canon", load_bearing=False,
          layer=None, canon_refs="[]"):
    layer_line = f"layer: {layer}\n" if layer else ""
    extra = (layer_line
             + f"when: 第 {when_sort:g} 年\nwhen_sort: {when_sort}\n"
             + f"event_kind: {kind}\n{legs}")
    return card(id, "event", extra=extra, status=status,
                load_bearing=load_bearing, canon_refs=canon_refs)


CARDS = {
    # —— 被事件引用的实体卡（CA721 静默）——
    "grey-town": card("grey-town", "location"),          # ev-town-founded 的 object
    "blacksmith-tom": card("blacksmith-tom", "character"),  # ev-sword-sold 的 by
    "sword-a": card("sword-a", "item"),                  # create + transfer 的 object
    "buyer-jane": card("buyer-jane", "character"),       # ev-sword-sold 的 to
    "old-oak": card("old-oak", "location"),              # ev-sword-sold 的 canon_refs
    # —— 未被引用的实体卡：CA721 恰好两条 ——
    "hermit-sage": card("hermit-sage", "character", status="trial"),
    "draft-potion": card("draft-potion", "item", status="draft"),  # draft 也报（口径）
    # archived 未被引用：豁免
    "archived-banner": card("archived-banner", "faction", status="archived"),
    # —— 事件卡 ——
    # 带治理字段的事件卡样板（load_bearing + layer + 显式空 depends_on 声明）
    "ev-town-founded": event(
        "ev-town-founded", "create", 0, "object:\n  - grey-town\n",
        load_bearing=True, layer="geo"),
    "ev-sword-forged": event(
        "ev-sword-forged", "create", 1, "object:\n  - sword-a\n"),
    # 事件卡的 canon_refs 引用实体卡：old-oak 由此被「事件引用」
    "ev-sword-sold": event(
        "ev-sword-sold", "transfer", 2,
        "by:\n  - blacksmith-tom\nto:\n  - buyer-jane\nobject:\n  - sword-a\n",
        canon_refs="[old-oak]"),
}


def main():
    path = ROOT / "world-event-first"
    if path.exists():
        shutil.rmtree(path)
    (path / "entries").mkdir(parents=True)
    for id, text in CARDS.items():
        (path / "entries" / f"{id}.md").write_text(text, encoding="utf-8")
    print(f"world-event-first: {len(CARDS)} entries")


if __name__ == "__main__":
    main()
