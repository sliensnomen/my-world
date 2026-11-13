"""canonlint 的跨条目事件时序与流水对账规则。"""
from __future__ import annotations

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


def check_ca703(world: dict, emit) -> None:
    index = world["index"]
    events = event_ledger.ordered_events(index)
    held = set()
    for e in index.values():
        if not e.parse_error:
            held.update(ref.target for ref in e.edges_of("owns"))
    for e, view in events:
        if view.kind in ("transfer", "grant"):
            for obj in view.legs.get("object", []):
                if obj not in held:
                    emit("warning", e.rel,
                         f"无源之财：{view.kind} 的客体 `{obj}` 在它之前没有任何持有者"
                         "（既无 owns 断言，也无更早的 transfer/grant 指向它）")
            held.update(view.legs.get("object", []))


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
                         f"`{e.id}`——未定序时断言必须同时落在全部候选里（交集：{shown}），"
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
        if view.kind in ("birth", "create", "death", "destroy", "transform"):
            continue
        seen: set[str] = set()
        for leg, label in (("object", "客体"), ("by", "施动者"),
                           ("from", "起点"), ("to", "终点")):
            for obj in view.legs.get(leg, []):
                if obj in seen:
                    continue
                if leg == "by" and obj in deaths and deaths[obj] < view.when_sort:
                    continue  # 死后/毁后当施动者由 CA705 负责
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
                         f"custody_of `{e.id}`——未定序时断言必须同时落在全部候选里"
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
        for org in event_ledger.member_of_assertions(e):
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


SCHEDULE = ("CA701", "CA703", "CA704", "CA705", "CA707", "CA708",
            "CA709", "CA710", "CA712", "CA711", "CA713")


def apply(run_world) -> None:
    for rule_id in SCHEDULE:
        run_world(rule_id)
