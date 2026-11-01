"""classlint 的无判定扫描与 CL100–CL107 逐规则实现。"""
from __future__ import annotations

from store import ID_RE
from store import parse as shared


REQUIRED_FIELDS = ["id", "title", "type"]


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


def check_cl106(entry, rel, add) -> None:
    for error in entry.relation_migrations:
        add("warning", error.msg)


def check_cl107(entry, rel, add) -> None:
    for raw_name in entry.raw_relation_names:
        near = shared.nearest_relation_name(raw_name)
        if near is not None:
            add("warning", f"关系名 `{raw_name}` 与规范名 `{near}` 只差一个字符，疑似拼写错误，"
                f"已按 `{near}` 判定；确是新关系请改用其它名字或加 `x-` 前缀")
