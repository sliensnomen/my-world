"""事件流水（协议 1.2）——事件字段解析与派生状态。

卡片是账户，事件是流水，现在的状态是算出来的（docs/事件流水设计.md）。
本模块只提供判定原料：事件长什么样、流水按什么顺序、每个客体最后在谁手里。
它不发射任何发现（findings）——判语（什么算错）与规则编号都在 canonlint.py。
"""
from __future__ import annotations

EVENT_KINDS = {"transfer", "custody", "move", "create", "destroy",
               "grant", "birth", "death", "join", "leave", "transform"}

from dataclasses import dataclass  # noqa: E402
import math  # noqa: E402

from store import Entry  # noqa: E402

REQUIRED_LEGS: dict[str, tuple[str, ...]] = {
    "transfer": ("by", "to", "object"),
    "custody": ("by", "to", "object"),
    "grant": ("by", "to", "object"),
    "move": ("object", "to"),
    "create": ("object",),
    "destroy": ("object",),
    "birth": ("object",),
    "death": ("object",),
    # join/leave（协议 1.6）：人写 by（白拿 CA705 的死人检查），组织写 to/from。
    # 不为「组织同意」单独立腿——v0 只记事实侧（人进了/出了）
    "join": ("by", "to"),
    "leave": ("by", "from"),
    # transform（协议 1.7）：object 是旧身份（关窗），result 是新身份列表（开窗，
    # 多值 = 一生多）。新 id 不自动继承旧 id 的持有者与位置——账接不接由作者写清
    "transform": ("object", "result"),
}
LEG_FIELDS = ("by", "to", "object", "from", "result")


@dataclass
class EventView:
    """一张卡作为「事件」的视图。字段缺席与写坏是两回事：写坏的腿由判定层
    报 CA109，但它仍算「声明过」（CA702 不双报），只是取不出 id。"""
    kind: object                 # event_kind 原值（非字符串也留着，给 CA102 报）
    when: object                 # when 原值
    when_sort: float | None      # 合法数字才是数字，否则 None（fail-open）
    legs: dict[str, list[str]]   # 形状合法的腿 → id 列表
    declared: set[str]           # 作者写过的腿（含写坏的、含空列表）
    bad_legs: set[str]           # 写坏的腿（含「是列表但元素全坏」）——CA702 的空列表分支不看它
    shape_errors: list[str]      # 人读的形状问题（判定层包成 CA109）


def event_view(e: Entry) -> EventView:
    meta = e.meta
    legs: dict[str, list[str]] = {}
    declared: set[str] = set()
    bad_legs: set[str] = set()
    errors: list[str] = []
    for leg in LEG_FIELDS:
        if leg not in meta:
            continue
        declared.add(leg)
        raw = meta[leg]
        if not isinstance(raw, list):
            bad_legs.add(leg)
            errors.append(f"事件的 `{leg}` 必须是 id 列表")
            continue
        ids: list[str] = []
        for i, item in enumerate(raw):
            if not isinstance(item, str):
                bad_legs.add(leg)
                errors.append(f"事件的 `{leg}[{i}]` 必须是 id 字符串，得到 {item!r}")
                continue
            ids.append(item)
        legs[leg] = ids
    ws = meta.get("when_sort")
    if ws is not None and (not isinstance(ws, (int, float)) or isinstance(ws, bool)
                           or math.isnan(ws) or math.isinf(ws)):
        # NaN 是 float 却没有任何比较结论（NaN > x 恒 False）：放它进流水，
        # 时序规则会对它整体静默——给了排序键反而拿到比「不给」更彻底的豁免
        errors.append(f"when_sort={ws!r} 必须是有限数字（可选排序键，不给就不参与时序判定）")
        ws = None
    when = meta.get("when")
    if when is not None and not isinstance(when, str):
        errors.append(f"when={when!r} 必须是字符串（故事内时间，自由文本）")
    return EventView(meta.get("event_kind"), when, ws, legs, declared, bad_legs, errors)


def is_experimental_kind(kind) -> bool:
    return isinstance(kind, str) and kind.startswith("x-")


def is_complete_event(v: EventView) -> bool:
    """完整事件 = event_kind 落在词表里。x- 实验值是事件但腿表未知（不判腿）。"""
    return v.kind in EVENT_KINDS


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
            if st.holder is None:  # 多个 owns 断言并存时按 id 序取第一个——
                # 这只是给派生状态一个确定答案，不是裁决；互搏本身由判定层报 CA707
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


def custody_assertions(e: Entry) -> list[str]:
    """`custody_of` 断言里形状合法的 id（形状问题由判定层报 CA109，这里不丢也不报）。"""
    raw = e.meta.get("custody_of")
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, str)]


def member_of_assertions(e: Entry) -> list[str]:
    """`member_of` 断言里形状合法的 id（同 custody_assertions 的口径）。

    多值合法：一个人可以同时在多个组织，所以成员关系没有互搏规则。
    """
    raw = e.meta.get("member_of")
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, str)]


def derive_membership(index: dict[str, Entry]) -> dict[str, dict[str, str]]:
    """{人: {组织: "join"|"leave"}}——每个人对每个组织、流水里的最后一个动作。

    只读有 when_sort 的完整事件（fail-open）；同刻两笔按 id 序，确定。
    """
    last: dict[str, dict[str, str]] = {}
    for e, v in ordered_events(index):
        if v.kind not in ("join", "leave"):
            continue
        orgs = v.legs.get("to" if v.kind == "join" else "from", [])
        for person in v.legs.get("by", []):
            for org in orgs:
                last.setdefault(person, {})[org] = v.kind
    return last


def existence_windows(index: dict[str, Entry]) -> dict[str, tuple[float | None, float | None]]:
    """每个客体的存在窗口 (起点, 终点)：birth/create 开窗，death/destroy 关窗。

    transform（协议 1.7）是窗口的交接点：旧身份（object）的窗口止于它，
    每个新身份（result）的窗口始于它——旧身份死、新身份生，物质延续。
    只读有 when_sort 的完整事件（缺排序键的边界不产生边界——fail-open）。
    同一端点出现多次取最早：先死先算。
    """
    windows: dict[str, list] = {}
    for e, v in ordered_events(index):
        if v.kind in ("birth", "create"):
            for obj in v.legs.get("object", []):
                w = windows.setdefault(obj, [None, None])
                w[0] = v.when_sort if w[0] is None else min(w[0], v.when_sort)
        elif v.kind in ("death", "destroy"):
            for obj in v.legs.get("object", []):
                w = windows.setdefault(obj, [None, None])
                w[1] = v.when_sort if w[1] is None else min(w[1], v.when_sort)
        elif v.kind == "transform":
            for obj in v.legs.get("object", []):
                w = windows.setdefault(obj, [None, None])
                w[1] = v.when_sort if w[1] is None else min(w[1], v.when_sort)
            for new_id in v.legs.get("result", []):
                w = windows.setdefault(new_id, [None, None])
                w[0] = v.when_sort if w[0] is None else min(w[0], v.when_sort)
    return {k: (w[0], w[1]) for k, w in windows.items()}
