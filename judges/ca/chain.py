"""canonlint 的 CA 依赖链与影响报告规则。"""
from __future__ import annotations

from collections import deque

from store import Entry

from .structure import KIND_INITIAL_SET, LAYER_INDEX


CA503_LAYERS = {"economy", "fiscal", "military", "political"}
CA505_TRIGGER_LAYERS = {"military", "political"}


def check_ca501(e: Entry, rel: str, add, index, dep) -> None:
    if e.meta.get("load_bearing") is not True:
        return
    layer = e.meta.get("layer")
    if layer not in LAYER_INDEX or dep.attrs.get("kind") not in KIND_INITIAL_SET:
        return
    target = index.get(dep.target)
    if target is None:
        return
    target_layer = target.meta.get("layer")
    if target_layer in LAYER_INDEX and LAYER_INDEX[target_layer] > LAYER_INDEX[layer]:
        add("error", f"depends_on 目标 `{dep.target}` 层级 {target_layer}"
            f"（序号 {LAYER_INDEX[target_layer]}）高于本条目 {layer}（序号 {LAYER_INDEX[layer]}）")


def check_ca503(e: Entry, rel: str, add) -> None:
    if e.meta.get("load_bearing") is not True:
        return
    layer = e.meta.get("layer")
    if layer not in LAYER_INDEX:
        return
    deps = e.edges_of("depends_on")
    if layer in CA503_LAYERS and not any(
            dep.attrs.get("critical") and dep.attrs.get("kind") in KIND_INITIAL_SET
            for dep in deps):
        add("warning", f"{layer} 层承重墙条目无任何物质族 critical 依赖（空中楼阁提示）")


def check_ca505(world: dict, emit) -> None:
    index = world["index"]
    layers_present = {e.meta.get("layer") for e in index.values() if not e.parse_error}
    load_bearing_layers = {
        e.meta.get("layer") for e in index.values()
        if not e.parse_error and e.meta.get("load_bearing") is True}
    if load_bearing_layers & CA505_TRIGGER_LAYERS and "fiscal" not in layers_present:
        emit("warning", "(仓库级)",
             "存在 military/political 层承重墙条目，但全库无 layer=fiscal 条目"
             "——财政维度可能缺失（刚铎型盲区）")


def check_ca502(world: dict, emit) -> None:
    index = world["index"]
    graph = {
        e.id: [dep.target for dep in e.edges_of("depends_on")
               if dep.target in index and dep.attrs.get("kind") in KIND_INITIAL_SET]
        for e in index.values() if not e.parse_error and e.id
    }
    white, gray, black = 0, 1, 2
    color = {key: white for key in graph}
    reported_cycles = set()
    for start in graph:
        if color[start] != white:
            continue
        stack = [(start, [start])]
        color[start] = gray
        while stack:
            node, path = stack[-1]
            advanced = False
            for next_id in graph.get(node, []):
                if color.get(next_id) == gray:
                    cycle = path[path.index(next_id):] + [next_id]
                    key = frozenset(cycle)
                    if key not in reported_cycles:
                        reported_cycles.add(key)
                        emit("error", index[node].rel,
                             f"depends_on 存在环（物质族）: {' → '.join(cycle)}")
                elif color.get(next_id) == white:
                    color[next_id] = gray
                    stack.append((next_id, path + [next_id]))
                    advanced = True
                    break
            if not advanced:
                stack.pop()
                color[node] = black


def check_ca504(world: dict, emit) -> list[dict]:
    index = world["index"]
    dependents = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for dep in e.edges_of("depends_on"):
            dependents.setdefault(dep.target, []).append(e.id)

    reports = []
    for subject in world["subjects"]:
        seen, order = set(), []
        queue = deque([subject])
        while queue:
            current = queue.popleft()
            for dependent in dependents.get(current, []):
                if dependent not in seen:
                    seen.add(dependent)
                    order.append(dependent)
                    queue.append(dependent)
        order = [entry_id for entry_id in order if entry_id != subject]

        def layer_key(entry_id):
            e = index.get(entry_id)
            layer = e.meta.get("layer") if e else None
            return LAYER_INDEX.get(layer, -1)

        order.sort(key=layer_key, reverse=True)
        reports.append({"rule": "CA504", "subject": subject, "downstream": order})
    return reports


def apply(index, run_entry, run_world) -> None:
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for dep in e.edges_of("depends_on"):
            run_entry("CA501", e, index=index, dep=dep)
        run_entry("CA503", e)
    run_world("CA505")
    run_world("CA502")
