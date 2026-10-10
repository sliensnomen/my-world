"""存储层 · 条目模型与解析。

本模块的天职只有一件事：**文件里写了什么 → 内存里是什么**。

它不认识任何理论：

  * 不知道「层级」是什么，不知道哪一层该养哪一层；
  * 不知道 `kind` 的取值有什么含义（`fiscal` 与 `manpower` 都只是普通字符串）；
  * 不知道什么叫「承重墙」，也不知道哪里算盲区；
  * 不知道哪些关系「讲得通」——那要懂政治经济学。

它只认识三类东西：

  1. **字段名与字段形状**（`FIELD_TABLE`、`CORE_REQUIRED_FIELDS`）；
  2. **id 语法**（`ID_RE`）；
  3. **一条边长什么样**（`Dep` / `ConflictRef` / `Relation`）。

判定（什么组合算错）在 canonlint.py 的规则里。本模块只按**格式**报形状不合规，并且把
规则编号（CA100/CA105/CA107/CA109）当作格式规则来报——那些编号描述的是「文件写得对不对」，
不是「道理讲不讲得通」。

规范形与兼容别名
----------------
契约（`world.schema.json` 的 `x-relation-source`）规定的规范形是
`relations: [{type, target, …}]`。旧文件里的具名字段 `depends_on` / `conflicts_with` /
`canon_refs` 仍然可读，读取时归一化到同一组内部对象上（`Entry.relations`）。
两者同时出现时**旧字段在前、`relations` 在后**，顺序确定，不依赖字典遍历顺序。

已知漂移（PR#3 收口）
--------------------
契约的 `x-relation-source.aliases` 列了九个别名，本层目前能读三种
（`LEGACY_RELATION_FIELDS`）。其余六种（`owns` / `controls` / `extracts` / `coerces` /
`legitimizes` / `owes`）**尚未**进入本工具的字段表，所以今天的 canonlint 会把它们报成
CA106「未定义字段」。这不是疏忽，而是刻意留着的收口点：见
`tests/test_store.py::check_relation_alias_drift`。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

# ---- id 语法 --------------------------------------------------------------

ID_RE = re.compile(r"^[a-z0-9-]+$")


def _type_hint(want: str) -> str:
    """报错文案的既有习惯：中文类型名紧跟「必须是」，英文类型名前留一个空格。"""
    return want if not want.isascii() else f" {want}"

# ---- 字段表（**格式**，不是理论）------------------------------------------
# 表里出现 `layer` 只说明「有这么一个键」，不说明任何一层该养哪一层。

CORE_REQUIRED_FIELDS = ("id", "title", "type", "author", "date", "status",
                        "load_bearing", "canon_refs", "conflicts_with", "ai_assisted")
ANNOTATION_FIELDS = ("layer", "depends_on", "superseded_by")
RELATIONS_FIELD = "relations"

FIELD_TABLE = (frozenset(CORE_REQUIRED_FIELDS) | frozenset(ANNOTATION_FIELDS)
               | {RELATIONS_FIELD})

# 能读的旧具名字段（`Entry.relations` 会把它们归一化）；其余别名见模块 docstring 的「已知漂移」
LEGACY_RELATION_FIELDS = ("depends_on", "conflicts_with", "canon_refs")

# 规范形边允许的键（契约 $defs/relation；`x-` 前缀的键永远是允许的）
CANONICAL_RELATION_ITEMS = ("type", "target", "kind", "critical", "stance", "note", "what")

# ---- 结构 ----------------------------------------------------------------


@dataclass
class Dep:
    id: str
    kind: str
    critical: bool


@dataclass
class ConflictRef:
    id: str
    stance: str | None  # None = 简式


@dataclass
class SchemaError:
    """形状不合规：规则编号 + 说明（不带级别——级别由报告层决定）。"""
    rule: str
    msg: str


@dataclass
class ShapeIssue:
    """扫描期发现：规则编号 + 相对路径 + 说明。"""
    rule: str
    rel: str
    message: str


@dataclass
class Relation:
    """一条边：关系名 + 目标 + 注解。

    规范形只要求 `type` 与 `target`；注解（`kind`/`critical`/`stance`/`note`/`what`）
    可以缺席——**「还没想好」是合法状态，不是错误**。判定器按「缺数据不报错」处理（PR#3）。
    """
    type: str
    target: str
    attrs: dict

    @property
    def kind(self) -> str | None:
        v = self.attrs.get("kind")
        return v if isinstance(v, str) else None

    @property
    def critical(self) -> bool | None:
        v = self.attrs.get("critical")
        return v if isinstance(v, bool) else None

    @property
    def stance(self) -> str | None:
        v = self.attrs.get("stance")
        return v if isinstance(v, str) else None

    @property
    def undeclared(self) -> tuple[str, ...]:
        """本边缺哪些注解。`depends_on` 关心 `kind`/`critical`；其余关系今天不要求注解。"""
        if self.type != "depends_on":
            return ()
        return tuple(k for k in ("kind", "critical") if k not in self.attrs)


@dataclass
class Entry:
    path: Path
    rel: str
    meta: dict
    body: str
    parse_error: str | None = None

    @property
    def id(self) -> str | None:
        v = self.meta.get("id")
        return v if isinstance(v, str) else None

    @property
    def status(self) -> str | None:
        v = self.meta.get("status")
        return v if isinstance(v, str) else None

    @cached_property
    def clean_body(self) -> str:
        """§6.6 预处理：剥代码块、HTML 注释、空白与 Unicode 标点。"""
        t = CODE_FENCE_RE.sub("", self.body)
        t = HTML_COMMENT_RE.sub("", t)
        return "".join(c for c in t
                       if not c.isspace() and not unicodedata.category(c).startswith("P"))

    # ---- 旧具名字段（保持原样；`deps`/`conflicts`/`canon_ref_ids` 是规则的现有输入）----

    @cached_property
    def deps(self) -> tuple[list[Dep], list[SchemaError]]:
        """解析 depends_on（§5.4 schema），结果缓存。"""
        raw = self.meta.get("depends_on")
        if raw is None:
            return [], []
        if not isinstance(raw, list):
            return [], [SchemaError("CA109", "depends_on 必须是列表")]
        deps, errs = [], []
        for i, item in enumerate(raw):
            where = f"depends_on[{i}]"
            if not isinstance(item, dict):
                errs.append(SchemaError("CA107", f"{where} 必须是对象"))
                continue
            extra = [k for k in item if k not in ("id", "kind", "critical")
                     and not str(k).startswith("x-")]
            missing = [k for k in ("id", "kind", "critical") if k not in item]
            for m in missing:
                errs.append(SchemaError("CA107", f"{where} 缺字段 `{m}`"))
            for x in extra:
                errs.append(SchemaError("CA107", f"{where} 含未定义字段 `{x}`（扩展须 x- 前缀）"))
            if missing or extra:
                continue
            if not isinstance(item["critical"], bool):
                errs.append(SchemaError("CA109", f"{where}.critical 必须是 bool"))
                continue
            if not isinstance(item["id"], str) or not ID_RE.match(item["id"]):
                errs.append(SchemaError("CA109", f"{where}.id={item['id']!r} 不符合 id 格式 ^[a-z0-9-]+$"))
                continue
            if not isinstance(item["kind"], str):
                errs.append(SchemaError("CA109", f"{where}.kind 必须是字符串"))
                continue
            deps.append(Dep(item["id"], item["kind"], item["critical"]))
        return deps, errs

    @cached_property
    def conflicts(self) -> tuple[list[ConflictRef], list[SchemaError]]:
        """解析 conflicts_with（§4.1：简式字符串或带 stance 的对象），结果缓存。"""
        raw = self.meta.get("conflicts_with")
        if raw is None:
            return [], []
        if not isinstance(raw, list):
            return [], [SchemaError("CA109", "conflicts_with 必须是列表")]
        refs, errs = [], []
        for i, item in enumerate(raw):
            if isinstance(item, str):
                refs.append(ConflictRef(item, None))
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                refs.append(ConflictRef(item["id"], item.get("stance")))
            else:
                errs.append(SchemaError("CA109", f"conflicts_with[{i}] 必须是 id 字符串或含 id 的对象"))
        return refs, errs

    @cached_property
    def canon_ref_ids(self) -> tuple[list[str], list[SchemaError]]:
        """canon_refs 必须是字符串列表，结果缓存。"""
        raw = self.meta.get("canon_refs")
        if raw is None:
            return [], []
        if not isinstance(raw, list):
            return [], [SchemaError("CA109", "canon_refs 必须是列表")]
        ids, errs = [], []
        for i, item in enumerate(raw):
            if isinstance(item, str):
                ids.append(item)
            else:
                errs.append(SchemaError("CA109", f"canon_refs[{i}] 必须是 id 字符串，得到 {item!r}"))
        return ids, errs

    # ---- 规范形 `relations` --------------------------------------------------

    @cached_property
    def canonical_relations(self) -> tuple[list[Relation], list[SchemaError]]:
        """解析规范形 `relations`（契约 `x-relation-source.canonical`）。

        只做形状校验。**不判断 `type` 是否是已知关系**——关系名是理论词表，原样保留，
        交给判定器（未来 PR#3 的注册表）。
        """
        raw = self.meta.get(RELATIONS_FIELD)
        if raw is None:
            return [], []
        if not isinstance(raw, list):
            return [], [SchemaError("CA109", "relations 必须是列表")]
        out, errs = [], []
        for i, item in enumerate(raw):
            where = f"relations[{i}]"
            if not isinstance(item, dict):
                errs.append(SchemaError("CA107", f"{where} 必须是对象"))
                continue
            extra = [k for k in item if k not in CANONICAL_RELATION_ITEMS
                     and not str(k).startswith("x-")]
            missing = [k for k in ("type", "target") if k not in item]
            for m in missing:
                errs.append(SchemaError("CA107", f"{where} 缺字段 `{m}`"))
            for x in extra:
                errs.append(SchemaError("CA107", f"{where} 含未定义字段 `{x}`（扩展须 x- 前缀）"))
            if missing or extra:
                continue
            bad = False
            for key in ("type", "target"):
                if not isinstance(item[key], str) or not item[key]:
                    errs.append(SchemaError("CA109", f"{where}.{key} 必须是字符串"))
                    bad = True
            for key, want_type, want in (("kind", str, "字符串"), ("stance", str, "字符串"),
                                         ("note", str, "字符串"), ("what", str, "字符串"),
                                         ("critical", bool, "bool")):
                if key in item and not isinstance(item[key], want_type):
                    errs.append(SchemaError(
                        "CA109", f"{where}.{key} 必须是{_type_hint(want)}"))
                    bad = True
            if bad:
                continue
            if item["type"] == "depends_on" and not ID_RE.match(item["target"]):
                errs.append(SchemaError(
                    "CA109", f"{where}.target={item['target']!r} 不符合 id 格式 ^[a-z0-9-]+$"))
                continue
            attrs = {k: v for k, v in item.items() if k not in ("type", "target")}
            out.append(Relation(item["type"], item["target"], attrs))
        return out, errs

    @cached_property
    def relations(self) -> list[Relation]:
        """**统一视图**：全部边，旧具名字段在前、规范形 `relations` 在后。

        这是存储层对外的边接口；规则今天仍然读 `deps`/`conflicts`/`canon_ref_ids`
        （逐字节不变），PR#3 再把判定器接到本视图上。
        """
        out: list[Relation] = []
        for dep in self.deps[0]:
            out.append(Relation("depends_on", dep.id,
                                {"kind": dep.kind, "critical": dep.critical}))
        for ref in self.conflicts[0]:
            attrs = {} if ref.stance is None else {"stance": ref.stance}
            out.append(Relation("conflicts_with", ref.id, attrs))
        for ref_id in self.canon_ref_ids[0]:
            out.append(Relation("canon_refs", ref_id, {}))
        out.extend(self.canonical_relations[0])
        return out

    @cached_property
    def relation_errors(self) -> list[SchemaError]:
        """规范形 `relations` 的形状问题（旧字段的问题仍在 `deps`/`conflicts`/`canon_ref_ids` 里）。"""
        return self.canonical_relations[1]

    @property
    def uses_canonical_relations(self) -> bool:
        return RELATIONS_FIELD in self.meta

    @property
    def uses_legacy_relations(self) -> bool:
        return any(f in self.meta for f in LEGACY_RELATION_FIELDS)

    @property
    def mixed_relation_forms(self) -> bool:
        """同一份文件里两种写法都有。存储层如实记录；怎么判是判定器的事（PR#3）。"""
        return self.uses_canonical_relations and self.uses_legacy_relations

    @property
    def undeclared_annotations(self) -> list[Relation]:
        """缺注解的边——「还没想好」是合法状态，不是错误。"""
        return [r for r in self.relations if r.undeclared]


# ---- 解析 ----------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def parse_entry(path: Path, root: Path) -> Entry:
    rel = str(path.relative_to(root))
    try:
        # utf-8-sig：容忍 BOM，避免把带 BOM 的文件误判为「缺少 frontmatter」
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as e:
        # 无法读取也是「文件无法解析」，按 §6.3 CA100 报，而不是让 traceback 逃逸
        return Entry(path, rel, {}, "", parse_error=f"文件无法读取: {e}")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return Entry(path, rel, {}, text,
                     parse_error="缺少 frontmatter（文件须以 --- 包裹的 YAML 头开始）")
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return Entry(path, rel, {}, "", parse_error=f"frontmatter YAML 解析失败: {e}")
    if not isinstance(meta, dict):
        return Entry(path, rel, {}, "", parse_error="frontmatter 必须是键值映射")
    return Entry(path, rel, meta, text[m.end():])
