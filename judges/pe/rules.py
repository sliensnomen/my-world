"""classlint 的 PE 独立规则；World 模型与执行日程由引擎提供。"""
from __future__ import annotations

from store import parse as shared

from judges.cl.structure import _is_finite_number, _nonempty_str, flow_schema_errors


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


def _flow_entries(world, line: str) -> list:
    """与 legacy `_flow_entries` 同口径：只收完整、形状合法的流量条目。"""
    out = []
    for entry in world.entries:
        if entry.meta.get("type") != "flow" or entry.meta.get("line") != line:
            continue
        frm, to = entry.meta.get("from"), entry.meta.get("to")
        if not isinstance(frm, str) or not isinstance(to, str):
            continue
        if frm not in world.index or to not in world.index:
            continue
        if flow_schema_errors(entry):
            continue
        out.append(entry)
    return out


def check_pe010(world, emit) -> None:
    """物流守恒：同单位流入必须满足 demand；数据不足时报 warning，不静默。"""
    logistics = _flow_entries(world, "logistics")

    for entry in world.entries:
        if entry.id is None or entry.meta.get("type") == "flow":
            continue
        demand = entry.meta.get("demand")
        if not isinstance(demand, dict):
            continue
        for what, spec in demand.items():
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not (_is_finite_number(amount) and _nonempty_str(unit)):
                continue
            incoming = [f for f in logistics
                        if f.meta.get("to") == entry.id and f.meta.get("what") == what]
            same = [f for f in incoming if f.meta.get("unit") == unit]
            if same:
                inflow = sum(f.meta["amount"] for f in same)
                if inflow < amount:
                    emit("error", entry.rel,
                         f"物流守恒：`{entry.id}` 对 `{what}` 的需求是 {amount:g} {unit}，"
                         f"同单位流入只有 {inflow:g} {unit}——断供")
            elif incoming:
                units = "、".join(sorted({str(f.meta.get("unit")) for f in incoming}))
                emit("warning", entry.rel,
                     f"物流守恒：`{entry.id}` 对 `{what}` 的需求单位是 `{unit}`，"
                     f"流入线单位是 {units}——单位不可比，无法判定")
            else:
                emit("error", entry.rel,
                     f"物流守恒：`{entry.id}` 声明了 `{what}` 需求 {amount:g} {unit}，"
                     f"但没有任何物流线流入——断供")

    for flow in logistics:
        to, what = flow.meta.get("to"), flow.meta.get("what")
        target_demand = world.index[to].meta.get("demand")
        if isinstance(target_demand, dict) and what in target_demand:
            continue
        emit("warning", flow.rel,
             f"物流守恒：`{to}` 没有声明对 `{what}` 的需求，这条流入无法对账"
             f"（给 `{to}` 加 demand，或确认它不需要）")


def check_pe011(world, emit) -> None:
    """补给律：暴力线的驻军地必须有物流线到达。"""
    logistics = _flow_entries(world, "logistics")
    for violence in _flow_entries(world, "violence"):
        to = violence.meta.get("to")
        if any(flow.meta.get("to") == to for flow in logistics):
            continue
        emit(None, violence.rel,
             f"补给律：暴力线驻守 `{to}`，但没有任何物流线送到 `{to}`——军队跨线无补给")


def check_pe012(world, emit) -> None:
    """人口律：流失必须有可对账的端点。"""
    for flow in _flow_entries(world, "people"):
        frm, to = flow.meta.get("from"), flow.meta.get("to")
        if frm == to:
            emit(None, flow.rel, "人口律：起点与终点是同一实体——流失没有去向")
            continue

        def has_population(eid: str) -> bool:
            value = world.index[eid].meta.get("population")
            return _is_finite_number(value) and value > 0

        if not has_population(frm) and not has_population(to):
            emit(None, flow.rel,
                 f"人口律：`{frm}` 与 `{to}` 都没有声明 population——流失规模无法对账"
                 f"（给至少一端加 population）")
