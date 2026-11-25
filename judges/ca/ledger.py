"""canonlint 的跨条目事件时序与流水对账规则。"""
from __future__ import annotations

import re

import ledger as event_ledger


def _is_event(view) -> bool:
    return event_ledger.is_complete_event(view) or event_ledger.is_experimental_kind(view.kind)


def check_ca701(world: dict, emit) -> None:
    index = world["index"]
    for e in index.values():
        if not event_ledger.is_event_card(e):
            continue
        view_a = event_ledger.event_view(e)
        if view_a.when_sort is None or not _is_event(view_a):
            continue
        for dep in e.edges_of("depends_on"):
            b = index.get(dep.target)
            if b is None or not event_ledger.is_event_card(b):
                continue
            view_b = event_ledger.event_view(b)
            if view_b.when_sort is None or not _is_event(view_b):
                continue
            if view_b.when_sort > view_a.when_sort:
                emit("warning", e.rel,
                     f"时序倒流：本事件 when_sort={view_a.when_sort:g}，"
                     f"depends_on 的事件 `{b.id}` when_sort={view_b.when_sort:g}（要求 ≤ 本事件）")


def _numeric_when(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            return float(text)
    return None


def _entity_type(world: dict, eid: str) -> str:
    """腿目标的 type（只认 strict vocabulary 五类；未知类型返回空串，fail-open）。"""
    entry = world["index"].get(eid)
    if entry is None or entry.parse_error:
        return ""
    t = entry.meta.get("type")
    return t if isinstance(t, str) else ""


LEG_TYPE_TABLE: dict[str, dict[str, frozenset[str]]] = {
    "transfer": {
        "by": frozenset({"character", "faction"}),
        "from": frozenset({"character", "faction"}),
        "to": frozenset({"character", "faction"}),
        "object": frozenset({"character", "faction", "item", "location"}),
    },
    "grant": {
        "by": frozenset({"character", "faction"}),
        "from": frozenset({"character", "faction"}),
        "to": frozenset({"character", "faction"}),
        "object": frozenset({"character", "faction", "item", "location"}),
    },
    "custody": {
        "by": frozenset({"character", "faction"}),
        "to": frozenset({"character", "faction"}),
        "object": frozenset({"character", "faction", "item", "location"}),
    },
    "move": {
        "object": frozenset({"character", "faction", "item"}),
        "to": frozenset({"location"}),
        "from": frozenset({"location"}),
    },
    "join": {"by": frozenset({"character"}), "to": frozenset({"faction"})},
    "leave": {"by": frozenset({"character"}), "from": frozenset({"faction"})},
    "birth": {"object": frozenset({"character"})},
    "create": {"object": frozenset({"character", "faction", "item", "location"})},
    "death": {"object": frozenset({"character", "item"})},
    "destroy": {"object": frozenset({"item", "location"})},
    "transform": {
        "object": frozenset({"character", "item", "location"}),
        "result": frozenset({"character", "item", "location"}),
    },
}


def check_ca717(world: dict, emit) -> None:
    """CA717：事件腿指向的实体类型必须与事件语义相符（#38 腿类型表）。"""
    index = world["index"]
    for event, view in event_ledger.ordered_events(index):
        if not _is_event(view):
            continue
        table = LEG_TYPE_TABLE.get(view.kind)
        if table is None:
            continue
        for leg, allowed in table.items():
            for target in view.legs.get(leg, []):
                t = _entity_type(world, target)
                if t and t not in allowed:
                    emit("error", event.rel,
                         f"腿类型不匹配：`{view.kind}` 的 {leg} `{target}` 是 {t}，"
                         f"该位置只收 {'/'.join(sorted(allowed))}——事件语义对不上"
                         "（类型写错请改；特殊关系请用 x- 事件）")


def check_ca716(world: dict, emit) -> None:
    index = world["index"]
    by_object: dict[str, list[tuple[float, float, object, str]]] = {}
    for event, view in event_ledger.ordered_events(index):
        if not _is_event(view):
            continue
        when = _numeric_when(event.meta.get("when"))
        if when is None:
            continue
        for obj in list(view.legs.get("object", [])) + list(view.legs.get("result", [])):
            by_object.setdefault(obj, []).append(
                (view.when_sort, when, event, view.kind))
    for obj, events in by_object.items():
        events.sort(key=lambda item: item[0])
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                ts_a, when_a, ev_a, _ = events[i]
                ts_b, when_b, ev_b, _ = events[j]
                if when_a > when_b:
                    emit("warning", ev_b.rel,
                         f"when 与 when_sort 反向：`{obj}` 的事件 `{ev_a.id}`"
                         f"（when={when_a:g}，when_sort={ts_a:g}）排在 `{ev_b.id}`"
                         f"（when={when_b:g}，when_sort={ts_b:g}）之前，故事时间却更晚"
                         "——排序号与 when 相反，请对齐两者")
                    break
            else:
                continue
            break


def check_ca703(world: dict, emit) -> None:
    index = world["index"]
    events = event_ledger.ordered_events(index)
    holder_sets: dict[str, set[str]] = {}
    created: set[str] = set()
    handed_over: set[str] = set()
    for e in index.values():
        if e.parse_error or e.meta.get("status") != "canon":
            continue
        for ref in e.edges_of("owns"):
            holder_sets.setdefault(ref.target, set()).add(e.id)
    for _e, view in events:
        if view.kind in ("birth", "create"):
            for obj in view.legs.get("object", []):
                created.add(obj)
    for e, view in events:
        if view.kind not in ("transfer", "grant"):
            continue
        for obj in view.legs.get("object", []):
            if obj not in created and obj not in holder_sets:
                emit("warning", e.rel,
                     f"无源之财：{view.kind} 的客体 `{obj}` 在它之前没有任何持有者"
                     "（既无 canon 卡的 owns 断言，也无更早的 transfer/grant 指向它）")
            current = holder_sets.get(obj)
            first_handover = obj in created and obj not in handed_over
            if current and not first_handover:
                for frm in view.legs.get("from", []):
                    if frm not in current:
                        emit("warning", e.rel,
                             f"交出者不是持有人：本笔 {view.kind} 声称从 `{frm}` 交出 `{obj}`，"
                             f"但该笔之前 `{obj}` 的持有证据是 {sorted(current)}"
                             "（owns 断言或更早流水）")
        for obj in view.legs.get("object", []):
            if obj in holder_sets or obj in created:
                holder_sets[obj] = set(view.legs.get("to", []))
            else:
                holder_sets.setdefault(obj, set(view.legs.get("to", [])))
            handed_over.add(obj)


def check_ca704(world: dict, emit) -> None:
    index = world["index"]
    states = event_ledger.derive_state(index)
    # 未定序与有无断言无关（协议 1.10）：同刻多笔且受方集合不同就报，每客体一条。
    final_acts = event_ledger.final_acts_by_object(index, ("transfer", "grant"))
    ambiguous = set()
    for obj in sorted(final_acts):
        when, acts = final_acts[obj]
        recipient_sets = {frozenset(to) for _event, _view, to in acts}
        if len(recipient_sets) <= 1:
            continue
        ambiguous.add(obj)
        peers = "、".join(sorted(event.id or event.rel
                                 for event, _view, _to in acts))
        first = min(acts, key=lambda act: act[0].id or "")[0]
        emit("warning", first.rel,
             f"归属未定序：`{obj}` 在 when_sort={when:g} 同时有 "
             f"{len(acts)} 笔转让（{peers}），受方集合不同——同刻没有先后，"
             "id 序只用于展示；请拆开 when_sort 或让受方一致")
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for ref in e.edges_of("owns"):
            if ref.target not in final_acts:
                continue
            when, acts = final_acts[ref.target]
            if ref.target in ambiguous:
                # 未定序不挑赢家，但也不许把断言对账整个跳掉（漏洞审计 §2.1）：
                # 断言者必须同时落在全部候选受方里（交集），否则照样报 error。
                common = set.intersection(*(set(to) for _event, _view, to in acts))
                if e.id not in common:
                    shown = "、".join(f"`{x}`" for x in sorted(common)) or "空"
                    emit("error", e.rel,
                         f"结论与流水打架：`{ref.target}` 在 when_sort={when:g} 归属未定序"
                         f"（同刻 {len(acts)} 笔转让，受方集合不同），卡上却断言 owns "
                         f"`{ref.target}`——未定序时断言必须同时落在全部候选里（交集：{shown}），"
                         "请拆开 when_sort、统一受方，或删掉这条断言")
                continue
            recipients = set().union(*(set(to) for _event, _view, to in acts))
            state = states.get(ref.target)
            if (state is not None and state.holder is not None and state.holder != e.id
                    and e.id not in recipients):
                emit("error", e.rel,
                     f"结论与流水打架：卡上断言 owns `{ref.target}`，但流水推出的"
                     f"最终持有者是 `{state.holder}`（来自 `{state.holder_source}`）")


def check_ca705(world: dict, emit) -> None:
    events = event_ledger.ordered_events(world["index"])
    deaths = {}
    for _e, view in events:
        # 审计 §1.1：destroy 也关存在窗口，记为「死」的角色不许再当施动者。
        if view.kind in ("death", "destroy"):
            for obj in view.legs.get("object", []):
                deaths[obj] = min(deaths.get(obj, view.when_sort), view.when_sort)
    for e, view in events:
        for actor in view.legs.get("by", []):
            if actor in deaths and deaths[actor] < view.when_sort:
                emit("warning", e.rel,
                     f"死人做活事：`{actor}` 在 when_sort={deaths[actor]:g} 的事件里"
                     f"已死亡/被毁，却在更晚的本事件（when_sort={view.when_sort:g}）的 by 里")


def check_ca707(world: dict, emit) -> None:
    index = world["index"]
    claims = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for ref in e.edges_of("owns"):
            claims.setdefault(ref.target, []).append(e)
    for obj in sorted(claims):
        holders = claims[obj]
        if len(holders) < 2:
            continue
        first = min(holder.id for holder in holders)
        for holder in sorted(holders, key=lambda item: item.rel):
            if holder.id == first:
                continue
            emit("warning", holder.rel,
                 f"owns 断言互搏：`{obj}` 同时被 `{first}` 与本卡断言持有"
                 f"（派生状态按 id 序取 `{first}`；请统一到一张卡上断言，或用流水表达流转）")


def check_ca708(world: dict, emit) -> None:
    index = world["index"]
    windows = event_ledger.existence_windows(index)
    deaths = {}
    for _e, view in event_ledger.ordered_events(index):
        if view.kind in ("death", "destroy"):
            for obj in view.legs.get("object", []):
                deaths[obj] = min(deaths.get(obj, view.when_sort), view.when_sort)
    for e, view in event_ledger.ordered_events(index):
        endpoint = view.kind in ("birth", "create", "death", "destroy", "transform")
        seen: set[str] = set()
        legs = (("by", "施动者"),) if endpoint else (
            ("object", "客体"), ("by", "施动者"),
            ("from", "起点"), ("to", "终点"))
        for leg, label in legs:
            for obj in view.legs.get(leg, []):
                if obj in seen:
                    continue
                if (leg == "by" and obj in deaths
                        and deaths[obj] < view.when_sort):
                    continue  # 非端点事件的死后施动者由 CA705 负责
                start, end = windows.get(obj, (None, None))
                if start is not None and view.when_sort < start:
                    seen.add(obj)
                    emit("warning", e.rel,
                         f"不存在的东西在动弹：`{obj}` 在 when_sort={start:g} 才被造出来/出生/转化出来，"
                         f"本事件却在 when_sort={view.when_sort:g} 拿它当{label}")
                elif end is not None and view.when_sort > end:
                    seen.add(obj)
                    emit("warning", e.rel,
                         f"不存在的东西在动弹：`{obj}` 在 when_sort={end:g} 已死亡/被毁/被转化，"
                         f"本事件却在更晚的 when_sort={view.when_sort:g} 拿它当{label}")


def check_ca709(world: dict, emit) -> None:
    index = world["index"]
    states = event_ledger.derive_state(index)
    # 未定序与有无断言无关（协议 1.10）：同刻多笔且保管人集合不同就报，每客体一条。
    custody_final = event_ledger.final_acts_by_object(index, ("custody",))
    ambiguous = set()
    for obj in sorted(custody_final):
        when, acts = custody_final[obj]
        recipient_sets = {frozenset(to) for _event, _view, to in acts}
        if len(recipient_sets) <= 1:
            continue
        ambiguous.add(obj)
        peers = "、".join(sorted(event.id or event.rel
                                 for event, _view, _to in acts))
        first = min(acts, key=lambda act: act[0].id or "")[0]
        emit("warning", first.rel,
             f"归属未定序：`{obj}` 在 when_sort={when:g} 同时有 "
             f"{len(acts)} 笔 custody（{peers}），保管人集合不同——同刻没有先后，"
             "id 序只用于展示；请拆开 when_sort 或让保管人一致")
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for obj in event_ledger.custody_assertions(e):
            if obj not in custody_final:
                continue
            when, acts = custody_final[obj]
            if obj in ambiguous:
                # 同 CA704（漏洞审计 §2.1）：未定序不挑赢家，但断言对账不许整个跳过。
                common = set.intersection(*(set(to) for _event, _view, to in acts))
                if e.id not in common:
                    shown = "、".join(f"`{x}`" for x in sorted(common)) or "空"
                    emit("error", e.rel,
                         f"结论与流水打架：`{obj}` 在 when_sort={when:g} 归属未定序"
                         f"（同刻 {len(acts)} 笔 custody，保管人集合不同），卡上却断言 "
                         f"custody_of `{obj}`——未定序时断言必须同时落在全部候选里"
                         f"（交集：{shown}），请拆开 when_sort、统一保管人，或删掉这条断言")
                continue
            recipients = set().union(*(set(to) for _event, _view, to in acts))
            state = states.get(obj)
            if (state is not None and state.custodian is not None
                    and state.custodian != e.id and e.id not in recipients):
                emit("error", e.rel,
                     f"结论与流水打架：卡上断言 custody_of `{obj}`，但流水推出的"
                     f"最终保管人是 `{state.custodian}`（custody 不改变持有者，只改保管）")


def check_ca710(world: dict, emit) -> None:
    index = world["index"]
    custody_claims = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for obj in event_ledger.custody_assertions(e):
            custody_claims.setdefault(obj, []).append(e)
    for obj in sorted(custody_claims):
        keepers = custody_claims[obj]
        if len(keepers) < 2:
            continue
        first = min(keeper.id for keeper in keepers)
        for keeper in sorted(keepers, key=lambda item: item.rel):
            if keeper.id == first:
                continue
            emit("warning", keeper.rel,
                 f"custody_of 断言互搏：`{obj}` 同时被 `{first}` 与本卡断言保管"
                 f"（派生状态按 id 序取 `{first}`；请统一到一张卡上断言，或用 custody 流水表达移交）")


def check_ca712(world: dict, emit) -> None:
    index = world["index"]
    membership_acts = {}
    for _e, view in event_ledger.ordered_events(index):
        if view.kind not in ("join", "leave"):
            continue
        orgs = view.legs.get("to" if view.kind == "join" else "from", [])
        for person in view.legs.get("by", []):
            for org in orgs:
                membership_acts.setdefault((person, org), []).append(
                    (view.when_sort, view.kind))
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        subject_type = e.meta.get("type")
        for org in event_ledger.member_of_assertions(e):
            org_entry = index.get(org)
            org_type = org_entry.meta.get("type") if org_entry is not None else None
            if subject_type not in ("character", "faction"):
                emit("error", e.rel,
                     f"member_of 的主体类型必须是 character/faction（当前 `{subject_type}`）"
                     "——这不是成员关系")
            if org_entry is not None and org_type != "faction":
                emit("error", e.rel,
                     f"member_of 的目标 `{org}` 必须是组织（type: faction），当前是 `{org_type}`"
                     "——方向或类型写反了")
            acts = membership_acts.get((e.id, org))
            if not acts:
                continue
            last_when = max(when for when, _kind in acts)
            last_kinds = {kind for when, kind in acts if when == last_when}
            if len(last_kinds) > 1:
                continue
            if "leave" in last_kinds:
                emit("error", e.rel,
                     f"结论与流水打架：卡上断言 member_of `{org}`，但流水里本条目"
                     "对该组织的最后一个动作是 leave——要么补一笔 join，要么把断言撤了")


def check_ca719(world: dict, emit) -> None:
    """CA719：成员链 join/leave 必须配对（#38 成员链 P0）。

    leave 之前必须有过 join；卡上的 `member_of` 断言可作初始成员（世界开始时
    已经在会里）。同刻 join/leave 并存时不排序，fail-open。
    """
    index = world["index"]
    ordered = list(event_ledger.ordered_events(index))
    # 每个 (person, org) 的同一 when_sort 若同时出现 join 与 leave，视为未定序
    instant: dict[tuple[str, str, float], set[str]] = {}
    for _e, view in ordered:
        if view.kind not in ("join", "leave"):
            continue
        orgs = view.legs.get("to" if view.kind == "join" else "from", [])
        for person in view.legs.get("by", []):
            for org in orgs:
                instant.setdefault((person, org, view.when_sort), set()).add(view.kind)
    initial: set[tuple[str, str]] = set()
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for org in event_ledger.member_of_assertions(e):
            initial.add((e.id, org))
    member: dict[tuple[str, str], bool] = {}
    for e, view in ordered:
        if view.kind not in ("join", "leave"):
            continue
        orgs = view.legs.get("to" if view.kind == "join" else "from", [])
        for person in view.legs.get("by", []):
            for org in orgs:
                key = (person, org)
                kinds = instant.get((person, org, view.when_sort), set())
                if len(kinds) > 1:
                    member[key] = True  # 同刻未定，fail-open，不据此判错
                    continue
                if view.kind == "join":
                    member[key] = True
                    continue
                if member.get(key) or key in initial:
                    member[key] = False
                    continue
                emit("error", e.rel,
                     f"无入会的退会：`{person}` 在 when_sort={view.when_sort:g} 从 "
                     f"`{org}` 退出，但此前没有加入记录，卡上也没有 member_of 断言"
                     "——成员链断了，请补 join 或用断言说明她是初始成员")





def check_ca720(world: dict, emit) -> None:
    """#38：转让/授予的起点与终点是同一个实体——账面上自己转给自己。"""
    index = world["index"]
    for e, view in event_ledger.ordered_events(index):
        if view.kind != "transfer":
            continue
        both = sorted(set(view.legs.get("from", [])) & set(view.legs.get("to", [])))
        if both:
            emit("error", e.rel,
                 f"自己转给自己：transfer 的起点与终点都是 {both}——"
                 "转让必须换持有者；只是想更新位置请用 move")


def check_ca721(world: dict, emit) -> None:
    """1.4 事件优先：实体卡未被任何事件引用（事件五腿 ∪ 事件卡 canon_refs）。

    只判「有 type: event 卡的世界」——没有事件卡的 1.x 存量世界整体沉默
    （与协议 1.2「旧世界一条不红」同一套 fail-open）。archived 实体卡豁免：
    降级处置（CA405/CA718）已终结它的账，不再收新债。事件卡自身不是检查
    对象——它是主叙述，不要求被别的事件引用。写坏的腿由 CA109 负责，这里
    不捡进引用集；悬空 id 的存在性由 CA401 负责，这里只管「引用有没有发生」。
    """
    index = world["index"]
    event_cards = [e for e in index.values() if event_ledger.is_event_card(e)]
    if not event_cards:
        return
    referenced: set[str] = set()
    for e in event_cards:
        view = event_ledger.event_view(e)
        for leg in event_ledger.LEG_FIELDS:
            referenced.update(view.legs.get(leg, ()))
        referenced.update(r.target for r in e.edges_of("canon_refs"))
    for e in index.values():
        if e.parse_error or not e.id or event_ledger.is_event_card(e):
            continue
        if e.meta.get("status") == "archived":
            continue
        if e.id in referenced:
            continue
        emit("warning", e.rel,
             "实体卡未被任何事件引用（口径：事件腿 by/to/object/from/result 与 "
             "事件卡 canon_refs）——把它编进事件，或确认它是有意的背景声明")


def check_ca711(world: dict, emit) -> None:
    index = world["index"]
    windows = event_ledger.existence_windows(index)
    undetermined = object()
    position = {}
    for e, view in event_ledger.ordered_events(index):
        if view.kind != "move":
            continue
        for obj in view.legs.get("object", []):
            start, end = windows.get(obj, (None, None))
            in_window = not ((start is not None and view.when_sort < start)
                             or (end is not None and view.when_sort > end))
            to = view.legs.get("to", [])
            from_ = view.legs.get("from", [])
            current = position.get(obj)
            if (in_window and from_ and current is not None
                    and current[0] is not undetermined
                    and current[1] < view.when_sort
                    and current[0] not in from_):
                emit("warning", e.rel,
                     f"轨迹断裂：`{obj}` 上一笔账落在 `{current[0]}`（when_sort={current[1]:g}），"
                     f"本笔却声称从 `{from_[0]}` 出发（不写 from 就不查；同刻 move 不排序）")
            if to:
                location = to[0] if len(to) == 1 else undetermined
                if current is not None and current[1] == view.when_sort:
                    if current[0] is undetermined or location is undetermined or current[0] != location:
                        location = undetermined
                position[obj] = (location, view.when_sort)


def check_ca713(world: dict, emit) -> None:
    index = world["index"]
    undetermined = object()
    recipient = {}
    for e, view in event_ledger.ordered_events(index):
        if view.kind not in ("transfer", "grant"):
            continue
        for obj in view.legs.get("object", []):
            to = view.legs.get("to", [])
            from_ = view.legs.get("from", [])
            current = recipient.get(obj)
            if (from_ and current is not None
                    and current[0] is not undetermined
                    and current[1] < view.when_sort
                    and current[0] not in from_):
                emit("warning", e.rel,
                     f"转让起点断裂：`{obj}` 上一笔账落在 `{current[0]}`（when_sort={current[1]:g}），"
                     f"本笔却声称从 `{from_[0]}` 交出（不写 from 就不查；同刻转让不排序）")
            if to:
                holder = to[0] if len(to) == 1 else undetermined
                if current is not None and current[1] == view.when_sort:
                    if (current[0] is undetermined or holder is undetermined
                            or current[0] != holder):
                        holder = undetermined
                recipient[obj] = (holder, view.when_sort)


def check_ca714(world: dict, emit) -> None:
    """端点事件不唯一或顺序矛盾（#38 端点类）。"""
    index = world["index"]
    events = event_ledger.ordered_events(index)
    created: dict[str, tuple[float, str]] = {}
    ended: dict[str, tuple[float, str]] = {}
    for e, view in events:
        if view.kind in ("birth", "create"):
            for obj in view.legs.get("object", []):
                if obj in created:
                    emit("error", e.rel,
                         f"端点事件不唯一：`{obj}` 已有开始事件 `{created[obj][1]}`"
                         f"（when_sort={created[obj][0]:g}），又出现 `{e.id}`"
                         f"（when_sort={view.when_sort:g}）——出生/创造只能发生一次")
                elif obj in ended:
                    emit("error", e.rel,
                         f"先死后生：`{obj}` 在 when_sort={ended[obj][0]:g} 已死/被毁"
                         f"（`{ended[obj][1]}`），when_sort={view.when_sort:g} 又出生")
                created.setdefault(obj, (view.when_sort, e.id))
        elif view.kind in ("death", "destroy"):
            for obj in view.legs.get("object", []):
                if obj in ended:
                    emit("error", e.rel,
                         f"端点事件不唯一：`{obj}` 已有结束事件 `{ended[obj][1]}`"
                         f"（when_sort={ended[obj][0]:g}），又出现 `{e.id}`"
                         f"（when_sort={view.when_sort:g}）——死亡/销毁只能发生一次")
                ended.setdefault(obj, (view.when_sort, e.id))
        elif view.kind == "transform":
            for obj in view.legs.get("object", []):
                if obj in ended and ended[obj][0] < view.when_sort:
                    emit("error", e.rel,
                         f"已销毁的客体又被 transform：`{obj}` 在 when_sort="
                         f"{ended[obj][0]:g} 已死/被毁（`{ended[obj][1]}`）")
            for res in view.legs.get("result", []):
                if res in created and created[res][0] <= view.when_sort:
                    emit("error", e.rel,
                         f"transform 的 result 早已存在：`{res}` 在 when_sort="
                         f"{created[res][0]:g} 已有开始事件（`{created[res][1]}`），"
                         f"transform（`{e.id}` when_sort={view.when_sort:g}）不能再创造它")
                if res in ended and ended[res][0] <= view.when_sort:
                    emit("error", e.rel,
                         f"transform 的 result 已经终结：`{res}` 在 when_sort="
                         f"{ended[res][0]:g} 已死/被毁（`{ended[res][1]}`）")


SCHEDULE = ("CA701", "CA703", "CA704", "CA705", "CA707", "CA708",
            "CA709", "CA710", "CA712", "CA711", "CA713", "CA714", "CA716", "CA717",
            "CA719", "CA720", "CA721")


def apply(run_world) -> None:
    for rule_id in SCHEDULE:
        run_world(rule_id)
