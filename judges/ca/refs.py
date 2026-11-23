"""canonlint 的 CA 引用与状态规则。"""
from __future__ import annotations

import ledger
import store
from store import Entry

from .vocab import WORLD_REF_RE, _RELATIONS_WITH_OWN_REFERENCE_RULES


def _valid_successor(e: Entry, index: dict[str, Entry]) -> str | None:
    successor = e.meta.get("superseded_by")
    if not isinstance(successor, str) or not successor or successor == e.id:
        return None
    return successor if successor in index else None


def _has_successor(e: Entry, index: dict[str, Entry]) -> bool:
    return _valid_successor(e, index) is not None


def check_ca401(e: Entry, rel: str, add, index, ref_id: str, via: str,
                broken_ids: frozenset[str] = frozenset()):
    if WORLD_REF_RE.match(ref_id):
        add("error", f"{via} 引用 {ref_id!r} 为 world:id 形式，本版协议不支持")
        return None
    target = index.get(ref_id)
    if target is None and ref_id not in broken_ids:
        add("error", f"{via} 引用指向不存在的 id `{ref_id}`")
    return target


def check_ca402(e: Entry, rel: str, add, index, ref_id: str, target: Entry) -> None:
    if target.status == "canon":
        return
    if target.status == "archived" and not _has_successor(target, index):
        return
    if target.status == "archived":
        add("error", f"canon_refs 目标 `{ref_id}` 已 archived，"
            f"请迁移至其承接条目 `{_valid_successor(target, index)}`")
    else:
        add("error", f"canon_refs 目标 `{ref_id}` 状态为 {target.status}，须为 canon")


def check_ca404(e: Entry, rel: str, add, ref_id: str, target: Entry,
                via: str = "depends_on") -> None:
    if e.status == "canon" and target.status != "canon":
        add("error", f"canon 条目的 {via} 目标 `{ref_id}` 状态为 {target.status}，须为 canon")


def check_ca109_superseded(e: Entry, rel: str, add, value) -> bool:
    if not isinstance(value, str):
        add("error", f"superseded_by={value!r} 必须是 id 字符串或 null")
        return False
    if value == e.id:
        add("error", "superseded_by 不能指向自己（承接者须是另一条目）")
        return False
    return True


def check_ca109_assertion(e: Entry, rel: str, add, assertion: str, raw, item_index=None) -> bool:
    if not isinstance(raw, list):
        add("error", f"{assertion} 必须是 id 列表")
        return False
    item = raw[item_index]
    if not isinstance(item, str):
        add("error", f"{assertion}[{item_index}] 必须是 id 字符串，得到 {item!r}")
        return False
    return True


def check_ca715(world: dict, emit) -> None:
    index = world["index"]
    for e in index.values():
        if e.parse_error or e.status != "canon":
            continue
        for edge in e.relations:
            if edge.type in ("canon_refs", "depends_on", "derives_legitimacy_from") or edge.type.startswith("x-"):
                continue
            target = index.get(edge.target)
            if target is None or target.parse_error:
                continue
            if target.status != "canon":
                emit("warning", e.rel,
                     f"canon 条目通过 `{edge.type}` 引用了非 canon 目标 "
                     f"`{edge.target}`（状态为 {target.status}）——要么把目标升格，"
                     f"要么把这条关系写成 x-")


def check_ca405(world: dict, emit) -> None:
    index = world["index"]
    for e in index.values():
        if e.parse_error or e.status != "archived":
            continue
        referenced = any(
            ref_id == e.id
            for other in index.values() if not other.parse_error
            for ref_id in (r.target for r in other.edges_of("canon_refs"))
        )
        if not referenced or _has_successor(e, index):
            continue

        successor = e.meta.get("superseded_by")
        if "superseded_by" not in e.meta:
            why = "未填 `superseded_by`"
        elif successor is None:
            why = "声称没有承接者（`superseded_by: null`）"
        elif not isinstance(successor, str) or not successor:
            why = f"`superseded_by={successor!r}` 不是合法的承接者"
        elif successor == e.id:
            why = "`superseded_by` 指向自己（承接者不能是本条目）"
        else:
            why = f"`superseded_by` 指向不存在的条目 `{successor}`"
        why += "（没有可迁移的承接条目）"
        emit("error", e.rel,
             f"archived 条目仍被 canon_refs 引用，但{why}——降级处置不完整")


def check_ca718(world: dict, emit) -> None:
    """CA718：承接链状态/类型/环（#38 承接链 P0）。

    CA405 只管「有没有可迁移的承接者」；这里管承接者本身站不站得住：
    承接者没定档、类型对不上（法典由一把剑承接）、或者互相承接成环，都报 error。
    """
    index = world["index"]
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        successor = e.meta.get("superseded_by")
        if not isinstance(successor, str) or not successor or successor == e.id:
            continue
        target = index.get(successor)
        if target is None or target.parse_error:
            continue  # 悬空由 CA401/CA405 管
        if target.meta.get("status") != "canon":
            emit("error", e.rel,
                 f"承接者未定档：`{e.id}` 的承接者 `{successor}` 状态为"
                 f" {target.meta.get('status')}——承接链要落在已定档条目上，请先升格")
        if target.meta.get("type") != e.meta.get("type"):
            emit("error", e.rel,
                 f"承接者类型不符：`{e.id}`（{e.meta.get('type')}）由 `{successor}`"
                 f"（{target.meta.get('type')}）承接——承接条目必须与原条目同类")
    # 环：沿着 superseded_by 走，回到走过的点就是死循环（draft→draft 也走）
    seen_cycles: set[frozenset[str]] = set()
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        path: list[str] = []
        cur = e
        while True:
            nxt = cur.meta.get("superseded_by")
            if not isinstance(nxt, str) or not nxt or nxt == cur.id:
                break
            if nxt in path:
                cycle = path[path.index(nxt):]
                key = frozenset(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    emit("error", cur.rel,
                         f"承接链成环：{' → '.join(cycle + [nxt])}——降级处置没有终点")
                break
            path.append(nxt)
            cur = index.get(nxt)
            if cur is None or cur.parse_error:
                break


def check_ca403(world: dict, emit) -> None:
    index = world["index"]
    for e in index.values():
        if e.parse_error:
            continue
        for ref in e.edges_of("conflicts_with"):
            target = index.get(ref.target)
            if target is None or target.parse_error:
                continue
            if any(r.target == e.id for r in target.edges_of("conflicts_with")):
                continue
            if ref.attrs.get("stance") is not None:
                continue
            emit("warning", e.rel, f"与 `{ref.target}` 的矛盾标注不对称（对方未回指）")


def apply(entries, index, run_entry, run_world) -> None:
    # 坏 YAML 的卡：id 还在原文里，别让引用方被报成「指向不存在的 id」（#40 F3）。
    broken_ids = frozenset(
        i for i in (store.salvage_id(e.path) for e in entries if e.parse_error) if i)
    for e in entries:
        if e.parse_error:
            continue
        for ref in e.edges_of("canon_refs"):
            target = run_entry("CA401", e, index=index, ref_id=ref.target, via="canon_refs",
                          broken_ids=broken_ids)
            if target is not None:
                run_entry("CA402", e, index=index, ref_id=ref.target, target=target)
        for dep in e.edges_of("depends_on"):
            target = run_entry("CA401", e, index=index, ref_id=dep.target, via="depends_on",
                               broken_ids=broken_ids)
            if target is not None:
                run_entry("CA404", e, ref_id=dep.target, target=target)
        # #38「CA111→CA404」：拆分前的 depends_on + kind: legitimacy 与规范形
        # derives_legitimacy_from 都是名分依据——canon 条目的依据目标也必须已定档。
        for edge in e.relations:
            if edge.type == "derives_legitimacy_from" or (
                    edge.type == "depends_on" and edge.kind == "legitimacy"):
                target = run_entry("CA401", e, index=index, ref_id=edge.target,
                                   via="derives_legitimacy_from", broken_ids=broken_ids)
                if target is not None:
                    run_entry("CA404", e, ref_id=edge.target, target=target,
                              via="derives_legitimacy_from")
        for relation in ("conflicts_with", "exchanges_with", "derives_legitimacy_from"):
            for ref in e.edges_of(relation):
                run_entry("CA401", e, index=index, ref_id=ref.target, via=relation,
                          broken_ids=broken_ids)
        for edge in e.relations:
            if edge.type not in _RELATIONS_WITH_OWN_REFERENCE_RULES:
                run_entry("CA401", e, index=index, ref_id=edge.target, via=edge.type,
                          broken_ids=broken_ids)

        successor = e.meta.get("superseded_by")
        if successor is not None:
            valid = run_entry("CA109", e, phase="superseded_by", value=successor)
            if valid:
                run_entry("CA401", e, index=index, ref_id=successor, via="superseded_by",
                          broken_ids=broken_ids)

        view = ledger.event_view(e)
        for leg in ledger.LEG_FIELDS:
            for ref_id in view.legs.get(leg, []):
                run_entry("CA401", e, index=index, ref_id=ref_id, via=leg,
                      broken_ids=broken_ids)

        for assertion in ("custody_of", "member_of"):
            raw = e.meta.get(assertion)
            if raw is None:
                continue
            if not isinstance(raw, list):
                run_entry("CA109", e, phase="assertion", assertion=assertion, raw=raw)
                continue
            for item_index in range(len(raw)):
                valid = run_entry("CA109", e, phase="assertion", assertion=assertion,
                                  raw=raw, item_index=item_index)
                if valid:
                    run_entry("CA401", e, index=index, ref_id=raw[item_index], via=assertion,
                              broken_ids=broken_ids)

    run_world("CA715")
    run_world("CA405")
    run_world("CA403")
    run_world("CA718")
