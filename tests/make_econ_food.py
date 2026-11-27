#!/usr/bin/env python3
"""生成 1.4 econ 食物链夹具世界 world-econ-food（协议 1.34，CA603）。

卡片分工（PROTOCOL-ECON.md §4）：
- food-gap：1000 人口 × 0.6 = 600 需求，粮 500 → warning
- food-partial-import：粮 500 + 进口 50 = 550 < 600 → warning（含进口量）
- food-imported：粮 500 + 进口 100 = 600 → 不报
- food-justified：粮 500，grain_supply 带 justification → 不报
- food-enough：粮 700 → 不报
- food-unmeasured：只有人口，没有口粮 → 不报（缺数据不是违规）
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent

_i = [0]


def card(id, figures):
    """一张合法实体卡。正文每张卡铺不同的字，避免 CA201 刷屏（同 make_ledger.py）。"""
    _i[0] += 1
    body = f"{id} 的夹具正文。\n" + chr(0x4E00 + _i[0]) * 220 + "\n"
    return f"""---
id: {id}
title: {id}
type: location
author: fixture
date: 2026-01-01
status: canon
load_bearing: false
figures:
{figures}canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---

{body}"""


def figures(population, supply=None, imported=None, justification=None):
    lines = [f"  population: {{value: {population}, unit: persons}}"]
    if supply is not None:
        suffix = f", justification: \"{justification}\"" if justification else ""
        lines.append(f"  grain_supply: {{value: {supply}, unit: kg_grain/day{suffix}}}")
    if imported is not None:
        lines.append(f"  grain_import: {{value: {imported}, unit: kg_grain/day}}")
    return "\n".join(lines) + "\n"


CARDS = {
    "food-gap": card("food-gap", figures(1000, 500)),
    "food-partial-import": card("food-partial-import", figures(1000, 500, imported=50)),
    "food-imported": card("food-imported", figures(1000, 500, imported=100)),
    "food-justified": card("food-justified", figures(
        1000, 500, justification="海运未到，账上先记缺口")),
    "food-enough": card("food-enough", figures(1000, 700)),
    "food-unmeasured": card("food-unmeasured", figures(1000)),
}

ECON = """params:
  food_per_person_day:
    value: 0.6
    unit: kg_grain/person/day
"""


def main():
    path = ROOT / "world-econ-food"
    if path.exists():
        shutil.rmtree(path)
    (path / "entries").mkdir(parents=True)
    (path / "econ.yaml").write_text(ECON, encoding="utf-8")
    for id, text in CARDS.items():
        (path / "entries" / f"{id}.md").write_text(text, encoding="utf-8")
    print(f"world-econ-food: {len(CARDS)} entries")


if __name__ == "__main__":
    main()
