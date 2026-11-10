"""classlint 的无判定扫描与 CL100–CL108 逐规则实现。"""
from __future__ import annotations

from store import ID_RE
from store import parse as shared


REQUIRED_FIELDS = ["id", "title", "type"]

# 流量层数据模型（协议 v0.2，与 classlint.py 的 legacy 实现逐字同构）。
# 两套实现必须给出逐条相同的 Finding——双跑测试（check_registry_cl_pe_dual_run）守着。
FLOW_LINES = ("logistics", "violence", "information", "people")
FLOW_COMMON_FIELDS = {"line", "from", "to", "note", "trend"}
FLOW_LINE_FIELDS = {
    "logistics": {"what", "amount", "unit"},
    "violence": {"amount", "unit", "supply_radius", "radius_unit"},
    "information": {"delay"},
    "people": {"what", "amount", "unit"},
}
FLOW_FIELDS = set(FLOW_COMMON_FIELDS) | set().union(*FLOW_LINE_FIELDS.values())
FLOW_TRENDS = ("rising", "flat", "falling")


def _is_finite_number(value) -> bool:
    """bool 是 int 的子类，不能当数字收下（同 canonlint 的 CA601）。"""
    return (isinstance(value, int | float) and not isinstance(value, bool)
            and value == value and value not in (float("inf"), float("-inf")))


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def flow_schema_errors(entry) -> list[str]:
    """CL108 的全部消息（非 flow 条目返回空）；顺序与 legacy 的 flow_schema_findings 相同。"""
    if entry.meta.get("type") != "flow":
        return []

    errors: list[str] = []

    line = entry.meta.get("line")
    if line is None:
        errors.append("流量条目必须声明 `line`（logistics/violence/information/people）")
    elif line not in FLOW_LINES:
        errors.append(f"`line` 必须是 logistics/violence/information/people 之一，收到 {line!r}")

    for leg, label in (("from", "起点"), ("to", "终点")):
        value = entry.meta.get(leg)
        if value is None:
            errors.append(f"流量条目缺少必填字段 `{leg}`（{label} id）")
        elif not isinstance(value, str):
            errors.append(f"`{leg}` 必须是字符串 id")

    if isinstance(line, str) and line in FLOW_LINES:
        allowed = FLOW_COMMON_FIELDS | FLOW_LINE_FIELDS[line]
        for key in entry.meta:
            if key in FLOW_FIELDS and key not in allowed:
                errors.append(f"line={line} 的流量不接受字段 `{key}`")
        for key in sorted(FLOW_LINE_FIELDS[line]):
            if key not in entry.meta:
                errors.append(f"{line} 流量缺少必填字段 `{key}`")
            elif key == "amount":
                value = entry.meta[key]
                if not _is_finite_number(value) or value <= 0:
                    errors.append("`amount` 必须是大于 0 的数字")
            elif key in ("supply_radius", "delay"):
                value = entry.meta[key]
                if not _is_finite_number(value) or value < 0:
                    errors.append(f"`{key}` 必须是 ≥0 的数字")
            elif key in ("unit", "radius_unit", "what"):
                if not _nonempty_str(entry.meta[key]):
                    errors.append(f"`{key}` 必须是非空字符串")

    trend = entry.meta.get("trend")
    if trend is not None and trend not in FLOW_TRENDS:
        errors.append("`trend` 只能是 rising/flat/falling")
    if "note" in entry.meta and not isinstance(entry.meta["note"], str):
        errors.append("`note` 必须是字符串")
    return errors



def scan(root, parse_entry, entry_root="codex", skip_dirs=frozenset({".git"})):
    """只扫描和建索引，不发射 Finding；首个合法 id 按路径序入索引。"""
    entries = []
    codex = root / entry_root
    if codex.is_dir():
        for path in sorted(codex.rglob("*.md")):
            if not path.is_file():
                continue
            if set(skip_dirs) & set(path.relative_to(root).parts):
                continue
            entries.append(parse_entry(path, root))

    index = {}
    for entry in entries:
        if entry.parse_error or entry.id is None or not ID_RE.match(entry.id):
            continue
        if entry.id not in index:
            index[entry.id] = entry
    return entries, index


def check_cl100(entry, rel, add) -> None:
    if entry.parse_error:
        add("error", entry.parse_error)


def check_cl101(entry, rel, add) -> None:
    for field in REQUIRED_FIELDS:
        if field not in entry.meta:
            add("error", f"缺少必填字段 `{field}`")


def check_cl102(entry, rel, add, index) -> None:
    if entry.id is not None and not ID_RE.match(entry.id):
        add("error", f"id={entry.id!r} 非法（仅允许小写字母/数字/连字符）")
    elif entry.id is not None and index.get(entry.id) is not entry:
        add("error", f"id `{entry.id}` 重复：{index[entry.id].rel} 与 {entry.rel}")


def check_cl103(entry, rel, add, known_fields) -> None:
    for key in entry.meta:
        if key not in known_fields and not str(key).startswith("x-"):
            # 流量层字段只在 `type: flow` 的条目上合法（协议 v0.2 §2.3）。
            if entry.meta.get("type") == "flow" and key in FLOW_FIELDS:
                continue
            add("error", f"未定义字段 `{key}`（扩展字段须 x- 前缀）")


def check_cl104(entry, rel, add) -> None:
    for error in entry.edges[1]:
        add("error", error.message)


def check_cl105(context, emit) -> None:
    model = context["model"]
    index = context["index"]
    for _src, edge, src_rel in model.edges:
        if edge.target not in index:
            emit("error", src_rel, f"{edge.rel} 目标 `{edge.target}` 不存在")
    # 流量条目的 from/to 同样是跨条目引用（协议 v0.2 §2.3）。
    for entry in context["all_entries"]:
        if entry.meta.get("type") != "flow":
            continue
        for leg, label in (("from", "流量起点"), ("to", "流量终点")):
            target = entry.meta.get(leg)
            if isinstance(target, str) and target not in index:
                emit("error", entry.rel, f"{label} `{target}` 不存在")


def check_cl106(entry, rel, add) -> None:
    for error in entry.relation_migrations:
        add("warning", error.msg)


def check_cl107(entry, rel, add) -> None:
    for raw_name in entry.raw_relation_names:
        near = shared.nearest_relation_name(raw_name)
        if near is not None:
            add("warning", f"关系名 `{raw_name}` 与规范名 `{near}` 只差一个字符，疑似拼写错误，"
                f"已按 `{near}` 判定；确是新关系请改用其它名字或加 `x-` 前缀")


def check_cl108(entry, rel, add) -> None:
    for message in flow_schema_errors(entry):
        add("error", message)
