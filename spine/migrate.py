#!/usr/bin/env python3
"""卡面世界 → 事件账本的一次性迁移工具（协议 2.0，骨架）。

语义边界（先读这个再用）：

- `type: event` 卡**直译**为账本事件：腿（by/to/object/from/result）、
  `when`/`when_sort`、`event_kind` → `type`。
- 实体卡的 `owns`/`custody_of`/`member_of` 断言转为**期初事件**：
  `type: import`，带 `x-import-kind`（owns/custody/member）、`source: import`、
  `evidence: attested`。**期初事件不是世界内事件**——世界里什么也没「发生」，
  它是期初建台的账目：不进抽取基准的评分（CHARTER.md §5），只供 L1 规则包
  与投影引擎恢复期初状态。
- 其余卡面字段（状态机、承重墙声明、八层链、canon_refs 等治理层字段）不迁移
  （CHARTER.md §6：治理层不是世界事实）。
- 只读源世界，永不在源世界写盘（宪章 §4：永不开第二条写通道）。

跨界豁免：本工具是依赖方向条款唯一允许的跨界者，只读 `store`（宪章 §4）。

用法:  python3 spine/migrate.py <卡面世界根> <输出账本根>
退出码: 0=迁移完成（含跳过项报告） 2=用法错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import store  # 跨界豁免：迁移工具只读 store 读卡（宪章 §4 依赖方向条款）

LEG_FIELDS = ("by", "to", "object", "from", "result")
ASSERTION_FIELDS = ("owns", "custody_of", "member_of")
ASSERTION_IMPORT_KIND = {"owns": "owns", "custody_of": "custody", "member_of": "member"}
NON_ID_CHARS = re.compile(r"[^a-z0-9-]+")


def _slug(text: str) -> str:
    return NON_ID_CHARS.sub("-", text.lower()).strip("-") or "x"


def _frontmatter(fields: list[tuple[str, object]]) -> str:
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _assertion_targets(e: store.Entry, field: str) -> list[str]:
    """断言字段的元素归一化为 id 列表（简式字符串或对象式 {id: ...} 都收）。"""
    raw = e.meta.get(field)
    if not isinstance(raw, list):
        return []
    targets = []
    for item in raw:
        if isinstance(item, str):
            targets.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            targets.append(item["id"])
    return targets


def migrate(root: Path, out: Path) -> dict:
    """迁移一个卡面世界。返回报告字典（供 CLI 打印与测试断言）。"""
    entries, _index, issues = store.collect(root)
    report = {"events": 0, "imports": 0, "skipped": [], "parse_errors": []}
    for issue in issues:
        report["parse_errors"].append(issue.rel)

    (out / "events").mkdir(parents=True, exist_ok=True)
    written: set[str] = set()

    def write_event(eid: str, fields: list[tuple[str, object]], body: str) -> bool:
        if eid in written:
            report["skipped"].append(f"{eid}（id 冲突，后者跳过）")
            return False
        written.add(eid)
        text = _frontmatter(fields) + "\n" + body.strip() + "\n"
        (out / "events" / f"{eid}.md").write_text(text, encoding="utf-8")
        return True

    for e in entries:
        if e.parse_error:
            continue
        if e.meta.get("type") == "event":
            fields: list[tuple[str, object]] = [
                ("id", e.id),
                ("type", e.meta.get("event_kind") or "x-untyped"),
            ]
            for leg in LEG_FIELDS:
                if isinstance(e.meta.get(leg), list):
                    fields.append((leg, e.meta[leg]))
            if isinstance(e.meta.get("when"), str):
                fields.append(("when", e.meta["when"]))
            if isinstance(e.meta.get("when_sort"), (int, float)):
                fields.append(("when_sort", e.meta["when_sort"]))
            fields.append(("source", "import"))
            fields.append(("evidence", "attested"))
            if write_event(e.id, fields, e.body):
                report["events"] += 1
            continue

        # 实体卡：断言 → 期初事件（type: import）；其余字段是治理层，不迁移
        for field in ASSERTION_FIELDS:
            for target in _assertion_targets(e, field):
                iid = _slug(f"import-{ASSERTION_IMPORT_KIND[field]}-{e.id}-{target}")
                fields = [("id", iid), ("type", "import"),
                          ("x-import-kind", ASSERTION_IMPORT_KIND[field]),
                          ("source", "import"), ("evidence", "attested")]
                if field == "member_of":
                    fields[2:2] = [("by", [e.id]), ("to", [target])]
                else:
                    fields[2:2] = [("to", [e.id]), ("object", [target])]
                body = f"期初建台：{e.id} 的 {field} 断言（迁移自卡面世界）。"
                if write_event(iid, fields, body):
                    report["imports"] += 1

        if (e.meta.get("type") != "event"
                and not any(_assertion_targets(e, f) for f in ASSERTION_FIELDS)):
            report["skipped"].append(f"{e.rel}（无事件、无断言，治理层字段不迁移）")

    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="卡面世界 → 事件账本的一次性迁移工具")
    ap.add_argument("root", type=Path, help="卡面世界根目录（只读）")
    ap.add_argument("out", type=Path, help="输出账本根目录")
    a = ap.parse_args(argv)
    if not (a.root / "entries").is_dir():
        print(f"error: {a.root} 不是卡面世界（缺 entries/）", file=sys.stderr)
        return 2
    report = migrate(a.root, a.out)
    print(f"迁移完成：{report['events']} 笔事件 + {report['imports']} 笔期初建台"
          f"（跳过 {len(report['skipped'])}，解析失败 {len(report['parse_errors'])}）")
    for line in report["skipped"]:
        print(f"  跳过: {line}")
    for line in report["parse_errors"]:
        print(f"  解析失败: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
