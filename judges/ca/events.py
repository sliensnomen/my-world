"""canonlint 的单条目事件形状与完整性规则。"""
from __future__ import annotations

import ledger
from store import Entry


def check_ca109(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        return
    if not ledger.is_event_card(e):
        if "event_kind" in e.meta or any(leg in e.meta for leg in ledger.LEG_FIELDS):
            add("error",
                f"事件字段只能出现在 `type: event` 的卡上（本卡 type={e.meta.get('type')!r}）；"
                "要记账请建 event 卡，史料卡上不要放 event_kind/腿")
        return
    for message in ledger.event_view(e).shape_errors:
        add("error", message)


def check_ca102(e: Entry, rel: str, add) -> None:
    if e.parse_error or not ledger.is_event_card(e):
        return
    view = ledger.event_view(e)
    if "event_kind" not in e.meta:
        return
    if not isinstance(view.kind, str):
        add("error", f"event_kind={view.kind!r} 必须是字符串")
    elif view.kind not in ledger.EVENT_KINDS:
        if ledger.is_experimental_kind(view.kind):
            add("info", f"event_kind={view.kind!r} 为实验值（x- 前缀），已计入案例收集")
        else:
            add("error", f"event_kind={view.kind!r} 非法，须为 {sorted(ledger.EVENT_KINDS)}"
                "（实验值须形如 `x-<命名空间>-<名称>`）")


def check_ca706(e: Entry, rel: str, add) -> None:
    if e.parse_error or not ledger.is_event_card(e):
        return
    if ("when" in e.meta) != ("event_kind" in e.meta):
        add("warning", "半截事件：`when` 与 `event_kind` 只给了一个"
            "（两个都给才进流水判定，都不给就是普通史料卡）")


def check_ca702(e: Entry, rel: str, add, leg: str) -> None:
    if e.parse_error or not ledger.is_event_card(e):
        return
    view = ledger.event_view(e)
    if not ledger.is_complete_event(view):
        return
    if leg not in view.declared:
        add("error", f"{view.kind} 事件缺腿 `{leg}`"
            f"（必填：{list(ledger.REQUIRED_LEGS[view.kind])}）——账不平")
    elif leg in view.legs and not view.legs[leg] and leg not in view.bad_legs:
        add("error", f"{view.kind} 事件的 `{leg}` 是空列表——账不平")


def apply(entries, run_entry) -> None:
    for e in entries:
        run_entry("CA109", e, phase="events")
        if not ledger.is_event_card(e):
            continue
        run_entry("CA102", e, phase="events")
        run_entry("CA706", e)
        view = ledger.event_view(e)
        if not ledger.is_complete_event(view):
            continue
        for leg in ledger.REQUIRED_LEGS[view.kind]:
            run_entry("CA702", e, leg=leg)
