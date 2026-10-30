"""canonlint 的 CA 结构规则；执行日程由 core-ca 驱动拥有。"""
from __future__ import annotations

from datetime import date, datetime
import re

import store
from store import Entry, ID_RE


REQUIRED_FIELDS = [
    "id", "title", "type", "author", "date", "status", "load_bearing",
    "canon_refs", "conflicts_with", "ai_assisted",
]
KNOWN_FIELDS = store.FIELD_TABLE
VALID_TYPES = {"location", "faction", "character", "event", "item"}
X_TYPE_RE = re.compile(r"^x-[a-z0-9]+-[a-z0-9-]+$")
VALID_STATUS = {"draft", "trial", "canon", "archived"}
VALID_STANCE = {"official", "heretic", "unknown"}
LAYERS = ["geo", "resource", "production", "economy", "fiscal", "military",
          "political", "ideology"]
LAYER_INDEX = {name: i for i, name in enumerate(LAYERS)}
KIND_INITIAL_SET = {"resource", "production", "economy", "fiscal", "manpower"}


def is_valid_date(value) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True
    return False


def check_ca100(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        add("error", e.parse_error)


def check_ca101(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        return
    for field in REQUIRED_FIELDS:
        if field not in e.meta:
            add("error", f"缺少必填字段 `{field}`")
    if e.meta.get("status") == "archived" and "superseded_by" not in e.meta:
        add("error", "archived 条目缺少 `superseded_by`（无承接者时填 null）")


def check_ca102(e: Entry, rel: str, add, phase: str = "all") -> None:
    if e.parse_error:
        return
    if phase in ("all", "fields"):
        if "type" in e.meta and (not isinstance(e.meta["type"], str)
                                 or e.meta["type"] not in VALID_TYPES):
            if isinstance(e.meta["type"], str) and X_TYPE_RE.match(e.meta["type"]):
                add("info", f"type={e.meta['type']!r} 为实验类型（x- 前缀），已计入案例收集")
            else:
                add("error", f"type={e.meta['type']!r} 非法，须为 {sorted(VALID_TYPES)}"
                    f"（实验类型须形如 `x-<命名空间>-<名称>`，如 `x-mine-weather`）")
        if "status" in e.meta and (not isinstance(e.meta["status"], str)
                                   or e.meta["status"] not in VALID_STATUS):
            add("error", f"status={e.meta['status']!r} 非法，须为 {sorted(VALID_STATUS)}")
        if "layer" in e.meta and (not isinstance(e.meta["layer"], str)
                                  or e.meta["layer"] not in LAYER_INDEX):
            add("error", f"layer={e.meta['layer']!r} 非法，须为 {LAYERS}")
    if phase in ("all", "stance"):
        for ref in e.edges_of("conflicts_with"):
            stance = ref.attrs.get("stance")
            if stance is not None and (not isinstance(stance, str)
                                       or stance not in VALID_STANCE):
                add("error", f"stance={stance!r} 非法，须为 {sorted(VALID_STANCE)}")


def check_ca103(e: Entry, rel: str, add) -> None:
    if not e.parse_error and "date" in e.meta and not is_valid_date(e.meta["date"]):
        add("error", f"date={e.meta['date']!r} 不是合法日期（须为 YYYY-MM-DD）")


def check_ca105(e: Entry, rel: str, add) -> None:
    if e.parse_error or "id" not in e.meta:
        return
    if not isinstance(e.meta["id"], str) or not ID_RE.match(e.meta["id"]):
        add("error", f"id={e.meta['id']!r} 非法（仅允许小写字母/数字/连字符）")


def check_ca106(e: Entry, rel: str, add, known_fields=KNOWN_FIELDS) -> None:
    if e.parse_error:
        return
    for key in e.meta:
        if key in known_fields or str(key).startswith("x-"):
            continue
        if isinstance(key, str) and store.canonical_relation_name(key) in known_fields:
            continue
        add("error", f"未定义字段 `{key}`（扩展字段须 x- 前缀）")


def check_ca112(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        return
    for key in e.duplicate_keys:
        add("error", f"字段 `{key}` 在 frontmatter 里出现了不止一次：YAML 只保留最后一个，"
            f"写在前面的那条等于没写")


def _schema_errors(e: Entry):
    yield from e.deps[1]
    yield from e.conflicts[1]
    yield from e.canon_ref_ids[1]
    yield from e.named_relation_errors
    yield from e.relation_errors


def check_ca107(e: Entry, rel: str, add, error=None) -> None:
    if e.parse_error:
        return
    errors = (error,) if error is not None else _schema_errors(e)
    for err in errors:
        if err.rule == "CA107":
            add("error", err.msg)


def check_ca108(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        return
    for dep in e.edges_of("depends_on"):
        kind = dep.attrs.get("kind")
        if kind is None or kind in KIND_INITIAL_SET:
            continue
        if isinstance(kind, str) and kind.startswith("x-"):
            add("info", f"kind={kind!r} 为实验值，已计入案例收集")
        else:
            add("error", f"kind={kind!r} 不在初始集且未带 x- 前缀")


def check_ca109(e: Entry, rel: str, add, phase: str = "all", error=None) -> None:
    if e.parse_error:
        return
    if error is not None:
        if error.rule == "CA109":
            add("error", error.msg)
        return
    if phase in ("all", "booleans"):
        for field in ("load_bearing", "ai_assisted"):
            if field in e.meta and not isinstance(e.meta[field], bool):
                add("error", f"{field}={e.meta[field]!r} 必须是 bool（true/false）")
    if phase in ("all", "schema"):
        for err in _schema_errors(e):
            if err.rule == "CA109":
                add("error", err.msg)


def check_ca110(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        return
    for raw_name in e.raw_relation_names:
        near = store.nearest_relation_name(raw_name)
        if near is not None:
            add("warning", f"关系名 `{raw_name}` 与规范名 `{near}` 只差一个字符，"
                f"疑似拼写错误，已按 `{near}` 判定；"
                f"确是新关系请改用其它名字或加 `x-` 前缀")


def check_ca111(e: Entry, rel: str, add) -> None:
    if e.parse_error:
        return
    for err in e.relation_migrations:
        add("warning", err.msg)


def check_ca114(world: dict, emit) -> None:
    for issue in world.get("issues", ()):
        if issue.rule == "CA114":
            emit("error", issue.rel, issue.message)
