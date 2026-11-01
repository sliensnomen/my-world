"""classlint 的 PE 独立规则；World 模型与执行日程由引擎提供。"""
from __future__ import annotations

from store import parse as shared


def _load_material_kinds() -> frozenset[str]:
    fallback = {"resource", "production", "economy", "fiscal", "manpower"}
    return frozenset(shared.contract_strict_vocabulary("depends_on.kind")) or frozenset(fallback)


MATERIAL_KINDS: frozenset[str] = _load_material_kinds()


def _cyclic_sccs(adj: dict[str, set[str]]) -> list[list[str]]:
    """有向图的环状强连通分量（含自环）。"""
    def reachable(start: str) -> set[str]:
        seen, stack = set(), [start]
        while stack:
            for nxt in adj.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    parent = {n: n for n in adj}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    reach = {n: reachable(n) for n in adj}
    for u in adj:
        for v in adj[u]:
            if u in reach[v]:
                parent[find(u)] = find(v)

    groups: dict[str, list[str]] = {}
    for n in adj:
        groups.setdefault(find(n), []).append(n)
    return [m for m in groups.values()
            if len(m) > 1 or any(n in adj[n] for n in m)]


def check_pe001(world, emit) -> None:
    for src, edge, src_rel in world.edges_of("extracts"):
        if edge.target not in world.index:
            continue
        if world.find_edge(src, {"controls", "coerces", "owns"}, edge.target) is None:
            emit(None, src_rel,
                 f"extracts → `{edge.target}` 无基础：对该目标没有任何 controls/coerces/owns 边")


def check_pe002(world, emit) -> None:
    for src, edge, src_rel in world.edges_of("coerces"):
        dep = world.find_edge(src, {"depends_on"}, edge.target)
        if dep is None:
            continue
        if dep.attrs.get("critical") is True:
            emit("error", src_rel,
                 f"一边 coerces → `{edge.target}`，一边对其 critical 依赖（断供即崩）"
                 "——镇压自己的供养者")
        else:
            emit("warning", src_rel,
                 f"一边 coerces → `{edge.target}`，一边对其 depends_on（非 critical）"
                 "——镇压与供养重叠，请确认")


def check_pe003(world, emit) -> None:
    """无外部输入的 legitimizes 环状 SCC 是无锚闭环。"""
    adj: dict[str, set[str]] = {}
    for _src, edge, _src_rel in world.edges_of("legitimizes"):
        if edge.target in world.index:
            adj.setdefault(_src, set()).add(edge.target)
            adj.setdefault(edge.target, set())

    for members in _cyclic_sccs(adj):
        ms = set(members)
        anchored = any(u not in ms for u in adj for v in adj[u] if v in ms)
        if anchored:
            continue
        rep = min(members)
        loop = " ↔ ".join(sorted(members)) if len(members) > 1 else f"{members[0]}（自环）"
        emit(None, world.rel_of[rep],
             f"legitimizes 闭环无外部锚点: {loop}——合法性不能凭空互证")


def check_pe004(world, emit) -> None:
    """extracts 的环状 SCC 表示剩余互相抽取而不落地于生产。"""
    adj: dict[str, set[str]] = {}
    for _src, edge, _src_rel in world.edges_of("extracts"):
        if edge.target in world.index:
            adj.setdefault(_src, set()).add(edge.target)
            adj.setdefault(edge.target, set())

    for members in _cyclic_sccs(adj):
        rep = min(members)
        loop = " ↔ ".join(sorted(members)) if len(members) > 1 else f"{members[0]}（自环）"
        emit(None, world.rel_of[rep],
             f"extracts 存在环: {loop}——剩余在循环中不落地于生产（黑洞）")


def check_pe005(world, emit) -> None:
    """被抽取者必须声明物质来源侧边，否则再生产不可见。"""
    def has_material_source(src: str) -> bool:
        for owner, edge, _rel in world.edges:
            if owner != src:
                continue
            if edge.rel in ("extracts", "exchanges_with"):
                return True
            if edge.rel == "depends_on" and edge.attrs.get("kind") in MATERIAL_KINDS:
                return True
        return False

    for src, edge, _src_rel in world.edges_of("extracts"):
        if edge.target not in world.index:
            continue
        if not has_material_source(edge.target):
            emit(None, world.index[edge.target].rel,
                 f"被 `{src}` 抽取，但本条目没有任何**物质**来源侧边（不抽取谁、不交换、"
                 f"也不靠带类别的物质依赖活着）——剩余从哪来不可见（请标注本条的 "
                 f"extracts/exchanges_with/带 kind 的 depends_on，或确认为终端生产者）")


def check_pe009(world, emit) -> None:
    """债权必须有支配、强制、抽取、正当性或承重依赖的兑现通道。"""
    for src, edge, src_rel in world.edges_of("owes"):
        if edge.target not in world.index:
            continue
        claim = world.find_edge(edge.target, {"controls", "coerces", "extracts",
                                              "legitimizes"}, src)
        if claim is not None:
            continue
        dep = world.find_edge(src, {"depends_on"}, edge.target)
        if dep is not None and (dep.attrs.get("critical") is True
                                or dep.attrs.get("kind") in MATERIAL_KINDS):
            continue
        emit(None, src_rel,
             f"欠 `{edge.target}` 债务，但看不到任何收得回来的途径：`{edge.target}` 不指挥、不强制、"
             f"不抽取、也不为这条提供正当性，这条自己也不依赖 `{edge.target}`"
             "——债权关系要有能兑现它的结构，否则只是记账")
