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
    """剩余必须收敛：抽取不能超过剩余（定量：surplus 声明）。"""
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

    logistics = _flow_entries(world, "logistics")
    for entity in world.entries:
        if entity.meta.get("type") == "flow":
            continue  # flow 卡写 surplus 由 CL103 报，不拿它下判
        surplus = entity.meta.get("surplus")
        if not isinstance(surplus, dict):
            continue
        outflows = [flow for flow in logistics if flow.meta.get("from") == entity.id]
        for what, spec in surplus.items():
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not _is_finite_number(amount) or not _nonempty_str(unit):
                continue
            outs = [flow for flow in outflows if flow.meta.get("what") == what]
            same = [flow for flow in outs if flow.meta.get("unit") == unit]
            total = sum(float(flow.meta["amount"]) for flow in same
                        if _is_finite_number(flow.meta.get("amount")))
            if total > amount + 1e-9:
                emit("error", entity.rel,
                     f"抽取超过剩余：`{entity.id}` 的 `{what}` 剩余只有 {amount:g} {unit}，"
                     f"但有 {total:g} {unit} 被抽走（{', '.join(flow.id for flow in same)}）"
                     f"——剩余不收敛")
            elif outs and not same:
                units = sorted({str(flow.meta.get("unit")) for flow in outs})
                emit("warning", entity.rel,
                     f"抽取超过剩余：`{entity.id}` 的 `{what}` 剩余单位是 `{unit}`，"
                     f"抽走线单位是 {units}——单位不可比，无法判定")

def check_pe005(world, emit) -> None:
    """被抽取者必须声明物质来源侧边，否则再生产不可见；定量版：剩余要有流入。"""
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

    logistics = _flow_entries(world, "logistics")
    warned: set[tuple[str, str]] = set()
    for entity in world.entries:
        target = entity.id
        if target is None or entity.meta.get("type") == "flow":
            continue
        surplus = entity.meta.get("surplus")
        if not isinstance(surplus, dict):
            continue
        for what in surplus:
            if not _nonempty_str(what) or (target, what) in warned:
                continue
            has_inflow = any(flow.meta.get("to") == target and flow.meta.get("what") == what
                             for flow in logistics)
            if not has_inflow:
                warned.add((target, what))
                emit("warning", entity.rel,
                     f"声称 `{what}` 有剩余，但没有任何 `{what}` 物流线流入"
                     f"——剩余从哪来不可见（定量版；请标注来源线，或确认为终端生产者）")

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
        if entry.id is None:
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
            if not isinstance(what, str):
                continue  # 坏键由 CL108 报，不拿它下判
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
    """补给律：暴力线驻军地必须有物流线到达；有 needs 时按量判。"""
    logistics = _flow_entries(world, "logistics")
    for violence in _flow_entries(world, "violence"):
        to = violence.meta.get("to")
        needs = violence.meta.get("needs")
        if isinstance(needs, dict):
            what, amount, unit = (needs.get("what"), needs.get("amount"),
                                  needs.get("unit"))
            if not (_nonempty_str(what) and _is_finite_number(amount)
                    and _nonempty_str(unit)):
                continue
            ins = [flow for flow in logistics
                   if flow.meta.get("to") == to and flow.meta.get("what") == what]
            same = [flow for flow in ins if flow.meta.get("unit") == unit]
            total = sum(float(flow.meta["amount"]) for flow in same
                        if _is_finite_number(flow.meta.get("amount")))
            if not ins:
                emit("error", violence.rel,
                     f"驻军补给不足：`{to}` 需要 {amount:g} {unit} `{what}`，"
                     f"但没有任何 `{what}` 物流线送到——断粮")
            elif not same:
                units = sorted({str(flow.meta.get("unit")) for flow in ins})
                emit("warning", violence.rel,
                     f"驻军补给不足：`{to}` 需要 {amount:g} {unit}，"
                     f"流入线单位是 {units}——单位不可比，无法判定")
            elif total < amount - 1e-9:
                emit("error", violence.rel,
                     f"驻军补给不足：`{to}` 的 `{what}` 需要 {amount:g} {unit}，"
                     f"同单位流入只有 {total:g} {unit}——断粮")
            continue
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


def check_pe006(world, emit) -> None:
    """危机积累：剩余刚好够活 + 抽取在上升。"""
    logistics = _flow_entries(world, "logistics")
    for entry in world.entries:
        if entry.id is None or entry.meta.get("type") == "flow":
            continue
        demand = entry.meta.get("demand")
        if not isinstance(demand, dict):
            continue
        extraction = sorted((flow for flow in logistics
                             if flow.meta.get("from") == entry.id
                             and flow.meta.get("what") in ("tax", "tribute")
                             and flow.meta.get("trend") == "rising"),
                            key=lambda flow: flow.id or "")
        if not extraction:
            continue
        for what in sorted(k for k in demand if isinstance(k, str)):
            spec = demand[what]
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not (_is_finite_number(amount) and _nonempty_str(unit)):
                continue
            inflow = sum(flow.meta["amount"] for flow in logistics
                         if flow.meta.get("to") == entry.id and flow.meta.get("what") == what
                         and flow.meta.get("unit") == unit)
            if not (inflow >= amount and inflow < amount * 1.1):
                continue
            flow = extraction[0]
            margin = (inflow - amount) / amount if amount else 0.0
            emit("warning", entry.rel,
                 f"危机积累：`{entry.id}` 的 `{what}` 需求 {amount:g} {unit} 只有同单位流入 "
                 f"{inflow:g} {unit}（余量 {margin:.0%}），而抽往 `{flow.meta.get('to')}` 的 "
                 f"`{flow.meta.get('what')}` 线还在 rising——剩余刚好够活，抽取再加就断")
            break


def check_pe007(world, emit) -> None:
    """结构性压力：人口在增长 + 占有关系未变。"""
    growing = sorted({flow.meta.get("to") for flow in _flow_entries(world, "people")
                      if flow.meta.get("trend") == "rising"
                      and flow.meta.get("to") in world.index})
    for eid in growing:
        involved = any((src == eid or edge.target == eid)
                       for src, edge, _rel in world.edges if edge.rel == "owns")
        if not involved:
            continue
        emit("warning", world.index[eid].rel,
             f"结构性压力：`{eid}` 人口在增长（people 流入 trend=rising），"
             f"但占有关系未变——人多了，占有格局还是旧的")


def check_pe008(world, emit) -> None:
    """镇压自己的基础：暴力镇压的对象同时是物流供养来源。"""
    logistics = _flow_entries(world, "logistics")
    seen: set[tuple[str, str]] = set()
    for src, edge, src_rel in world.edges_of("coerces"):
        if edge.target not in world.index:
            continue
        key = (src, edge.target)
        if key in seen:
            continue
        seen.add(key)
        if not any(flow.meta.get("from") == edge.target and flow.meta.get("to") == src
                   for flow in logistics):
            continue
        emit("error", src_rel,
             f"镇压自己的基础：`{src}` 镇压 `{edge.target}`，但 `{edge.target}` 的物流线"
             f"在供养 `{src}`——镇压自己的供养来源")


def _personal_edge(world, a: str, b: str, rel: str):
    """个人关系是语境边，方向不承诺：A↔B 任一方向有这条关系就算数。"""
    for src, edge, _r in world.edges:
        if edge.rel != rel:
            continue
        if (src == a and edge.target == b) or (src == b and edge.target == a):
            return edge
    return None


def check_pe013(world, emit) -> None:
    """亲情与镇压矛盾：被镇压的供养者与镇压者有亲缘。"""
    for src, edge, src_rel in world.edges_of("coerces"):
        if edge.target not in world.index:
            continue
        if world.find_edge(src, {"depends_on"}, edge.target) is None:
            continue
        kin = _personal_edge(world, src, edge.target, "kin")
        if kin is None:
            continue
        label = (kin.attrs.get("what") or "").strip()
        note = f"`{label}`" if label else "亲缘"
        emit("warning", src_rel,
             f"亲情与镇压矛盾：`{src}` 镇压供养自己的 `{edge.target}`（PE002 报的结构矛盾），"
             f"但双方有{note}关系——私人关系可能让镇压被容忍或延迟，审计不应按纯经济人读")


def check_pe014(world, emit) -> None:
    """庇护关系可能缓冲危机：抽取者与被抽取者有效忠关系。"""
    logistics = _flow_entries(world, "logistics")
    for flow in logistics:
        what, trend = flow.meta.get("what"), flow.meta.get("trend")
        if what not in ("tax", "tribute") or trend != "rising":
            continue
        frm, to = flow.meta.get("from"), flow.meta.get("to")
        if frm not in world.index or to not in world.index:
            continue
        # 只在 PE006 的触发面上报：被抽取方有需求且同单位余量 < 10%。
        demand = world.index[frm].meta.get("demand")
        if not isinstance(demand, dict):
            continue
        crisis = None
        for dwhat in sorted(k for k in demand if isinstance(k, str)):
            spec = demand[dwhat]
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not (_is_finite_number(amount) and _nonempty_str(unit)):
                continue
            inflow = sum(f.meta["amount"] for f in logistics
                         if f.meta.get("to") == frm and f.meta.get("what") == dwhat
                         and f.meta.get("unit") == unit)
            if inflow >= amount and inflow < amount * 1.1:
                crisis = (dwhat, amount, inflow)
                break
        if crisis is None:
            continue
        allegiance = _personal_edge(world, frm, to, "allegiance")
        if allegiance is None:
            continue
        dwhat, amount, inflow = crisis
        label = (allegiance.attrs.get("what") or "").strip()
        note = f"`{label}`" if label else "效忠"
        margin = (inflow - amount) / amount if amount else 0.0
        emit("warning", flow.rel,
             f"庇护关系可能缓冲危机：`{to}` 从 `{frm}` 抽取 `{what}`（线在 rising），"
             f"而 `{frm}` 的 `{dwhat}` 只剩 {margin:.0%} 余量，但双方有{note}关系"
             f"——危机可能被庇护网络吸收，不应按纯市场读")


def check_pe015(world, emit) -> None:
    """时延律：消息抵达前发生的变故，命令管不到。"""
    moments = [e for e in world.entries
               if e.meta.get("type") == "moment"
               and _is_finite_number(e.meta.get("at"))]
    if not moments:
        return
    for flow in _flow_entries(world, "information"):
        when, delay = flow.meta.get("when"), flow.meta.get("delay")
        if not _is_finite_number(when) or not _is_finite_number(delay):
            continue
        arrival = when + delay
        to = flow.meta.get("to")
        for moment in moments:
            affects = moment.meta.get("affects")
            if not isinstance(affects, list) or to not in affects:
                continue
            at = moment.meta["at"]
            if when <= at < arrival:
                emit("warning", flow.rel,
                     f"时延倒挂：`{to}` 在 `{moment.id}`（at={at:g}）发生变故，"
                     f"但 `{flow.id}` 的消息 when={when:g} + delay={delay:g} = {arrival:g} 才抵达"
                     f"——命令晚于政变，抵达前发生的事它管不到")
