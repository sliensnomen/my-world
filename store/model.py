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

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

# ---- id 语法 --------------------------------------------------------------

ID_RE = re.compile(r"^[a-z0-9-]+$")

# ---- 关系名归一化（契约是唯一真值）------------------------------------------
# 本层不认识任何关系名的**含义**；它只负责「同一个关系的所有历史拼法 → 一个规范名」。
# 真值表在契约 world.schema.json 的 x-relation-vocabulary；本模块读它，不自己再写一份。

SCHEMA_NAME = "world.schema.json"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / SCHEMA_NAME


def _contract_relation_names() -> dict[str, tuple[str, ...]]:
    """读契约的关系名词表：{规范名: (契约声明的全部可接受拼法…)}。"""
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        return {name: tuple(spec["accept"])
                for name, spec in schema["x-relation-vocabulary"]["names"].items()}
    except (OSError, ValueError, KeyError, TypeError):
        # 契约不在树里（单独拷走 store/）时不静默：退化到只认既有三个字段名，
        # 下面 _shape_variants 仍保证连字符/下划线互通。
        return {}


def _shape_variants(word: str) -> set[str]:
    """一个关系名的历史形状：原样、连字符、下划线、去掉分隔符。"""
    return {word, word.replace("-", "_"), word.replace("_", "-"),
            word.replace("-", "").replace("_", "")}


RELATION_VOCABULARY: dict[str, tuple[str, ...]] = _contract_relation_names()
_ALL_RELATION_NAMES: tuple[str, ...] = tuple(RELATION_VOCABULARY) or (
    "canon_refs", "conflicts_with", "depends_on")

# 任意拼法 → 规范名。契约变体优先，机械变体兜底。
RELATION_TYPE_NAMES: dict[str, str] = {}
for _name in _ALL_RELATION_NAMES:
    for _variant in (RELATION_VOCABULARY.get(_name) or ()) or _shape_variants(_name):
        RELATION_TYPE_NAMES[_variant] = _name
    for _variant in _shape_variants(_name):
        RELATION_TYPE_NAMES.setdefault(_variant, _name)


def canonical_relation_name(name: str) -> str:
    """把任意历史拼法归一到规范名；未知名原样返回（自由档允许自定义关系名）。

    契约 x-relation-vocabulary.spelling-guard 规定：与已知名编辑距离 ≤1 的 type 值
    由判定层记 warning（CA110），不是在这里报错——存储层只归一化，不下判语。
    """
    return RELATION_TYPE_NAMES.get(name, name)


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein 距离（两行滚动）。只用于拼写近失守卫，作用域小、无依赖。"""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def nearest_relation_name(name: str) -> str | None:
    """`name` 不是已知拼法、但与某个规范名只差一个字符时返回那个规范名，否则 None。

    这是**标记**不是**拒绝**：契约 world.schema.json:16-17 的自由档允许用户自定义关系名，
    所以真正的新词必须继续 fail-open；只有「看着像打错」的名字才提示。
    """
    if not isinstance(name, str) or not name or name.startswith("x-"):
        return None
    if name in _ALL_RELATION_NAMES:
        return None  # 本身就是规范名
    if RELATION_TYPE_NAMES.get(name) is not None:
        return None  # 是已知历史拼法，已经归一化，不必提示
    for canonical in _ALL_RELATION_NAMES:
        if _edit_distance(name, canonical) <= 1:
            return canonical
    return None


def _type_hint(want: str) -> str:
    """报错文案的既有习惯：中文类型名紧跟「必须是」，英文类型名前留一个空格。"""
    return want if not want.isascii() else f" {want}"

# ---- 字段表（**格式**，不是理论）------------------------------------------
# 表里出现 `layer` 只说明「有这么一个键」，不说明任何一层该养哪一层。

CORE_REQUIRED_FIELDS = ("id", "title", "type", "author", "date", "status",
                        "load_bearing", "canon_refs", "conflicts_with", "ai_assisted")
ANNOTATION_FIELDS = ("layer", "depends_on", "superseded_by")
RELATIONS_FIELD = "relations"

# 能读的旧具名字段（`Entry.relations` 把它们归一化到同一视图）。
# 契约 x-relation-source.aliases 列了十个，这里读全十个——收口完成（旧「已知漂移」关闭）。
LEGACY_RELATION_FIELDS = ("depends_on", "conflicts_with", "canon_refs", "exchanges_with",
                          "owns", "controls", "extracts", "coerces", "legitimizes", "owes")

# 三个「自古就有」的具名字段有各自的解析器与错误文案，判定侧也按各自的规则报；
# 其余七个是接线补上的，形状错误统一走 `Entry.named_relation_errors`。
CLASSIC_RELATION_FIELDS = ("canon_refs", "conflicts_with", "depends_on")

FIELD_TABLE = (frozenset(CORE_REQUIRED_FIELDS) | frozenset(ANNOTATION_FIELDS)
               | frozenset(LEGACY_RELATION_FIELDS) | {RELATIONS_FIELD})

# 规范形边允许的键（契约 $defs/relation；`x-` 前缀的键永远是允许的）
CANONICAL_RELATION_ITEMS = ("type", "target", "kind", "critical", "stance", "note", "what")

# 具名字段 → 它携带的注解键（契约 x-relation-source.aliases[*].attrs）
NAMED_RELATION_ATTRS: dict[str, tuple[str, ...]] = {
    "canon_refs": (),
    "conflicts_with": ("stance",),
    "depends_on": ("kind", "critical", "note"),
    "exchanges_with": ("what", "note"),
    "owns": ("note",),
    "controls": ("note",),
    "extracts": ("what", "note"),
    "coerces": ("note",),
    "legitimizes": ("note",),
    "owes": ("what", "note"),
}

# 规范名 → 具名字段，用来把契约里的关系名对回字段（两者今天同名，但不假设这一点）
_RELATION_FIELD_OF: dict[str, str] = {}
for _field in LEGACY_RELATION_FIELDS:
    _RELATION_FIELD_OF.setdefault(canonical_relation_name(_field), _field)

# 具名字段 → (规范名, 允许的注解键)。注解键从契约 attrs 推；depends_on 之所以多一个
# `kind`，是因为契约把它同时列进 depends_on.kind 词表（CA108），不是本层在讲理论。
_ANNOTATION_KEYS: dict[str, tuple[str, ...]] = {
    key: tuple(attrs) for key, attrs in NAMED_RELATION_ATTRS.items()}
_RELATION_FIELD_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {}
for _field in LEGACY_RELATION_FIELDS:
    _name = _RELATION_FIELD_OF.get(canonical_relation_name(_field), _field)
    _keys = _ANNOTATION_KEYS.get(_name, ())
    if _name == "depends_on":
        _keys = _keys + ("kind",)
    _RELATION_FIELD_SPECS[_field] = (_name, _keys)

# 具名字段的对象项允许的键（`id` + 该关系的注解键；x- 前缀永远允许）
_NAMED_RELATION_ITEM_KEYS: tuple[str, ...] = ("id", "kind")

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


def _parse_named_relation(raw, field: str, name: str,
                          keys: tuple[str, ...]) -> tuple[list[Relation], list[SchemaError]]:
    """解析一个具名关系字段（字符串简式或 `{id, …}` 对象式）。

    只做形状校验，不判断关系名的含义。允许的键 = `id` + 契约给这个族声明的注解键
    （`x-` 前缀永远允许）。

    形状坏掉时**照旧建边**（坏值留给判定层报），这条规矩来自 `conflicts_with`：
    `stance` 写成列表时边仍然进图，由 CA102 报取值非法——如果这里把边丢掉，一条
    写坏的引用就会对所有规则隐形，那正是本模块刚修掉的那类缺陷。
    """
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [SchemaError("CA109", f"{field} 必须是列表")]
    edges: list[Relation] = []
    errs: list[SchemaError] = []
    for i, item in enumerate(raw):
        where = f"{field}[{i}]"
        if isinstance(item, str):
            # 简式字符串一律建边：id 语法与 world:id 超出本层的形状职责，
            # 由判定层的 CA401/CA105 报（漏掉这一步会让这类引用对所有规则隐形）。
            edges.append(Relation(name, item, {}))
            continue
        if not isinstance(item, dict):
            errs.append(SchemaError("CA107", f"{where} 必须是 id 字符串或对象"))
            continue
        extra = [k for k in item
                 if k not in ("id",) + keys + _NAMED_RELATION_ITEM_KEYS
                 and not str(k).startswith("x-")]
        missing = [k for k in ("id",) if k not in item]
        for m in missing:
            errs.append(SchemaError("CA107", f"{where} 缺字段 `{m}`"))
        for x in extra:
            errs.append(SchemaError("CA107", f"{where} 含未定义字段 `{x}`（扩展须 x- 前缀）"))
        if missing or extra:
            continue
        if not isinstance(item["id"], str) or not ID_RE.match(item["id"]):
            errs.append(SchemaError("CA109", f"{where}.id={item['id']!r} 不符合 id 格式 ^[a-z0-9-]+$"))
            continue
        for k, want in (("kind", str), ("critical", bool), ("stance", str),
                        ("note", str), ("what", str)):
            if k in item and k in keys and not isinstance(item[k], want):
                errs.append(SchemaError("CA109", f"{where}.{k} 必须是"
                                        + (" bool" if want is bool else "字符串")))
        attrs = {k: v for k, v in item.items() if k != "id"}
        edges.append(Relation(name, item["id"], attrs))
    return edges, errs


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
            if not isinstance(item["type"], str) or not item["type"]:
                errs.append(SchemaError("CA109", f"{where}.type 必须是字符串"))
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
            canonical_type = canonical_relation_name(item["type"])
            if canonical_type == "depends_on":
                # §5.4：depends_on 对象的 kind / critical **必填**（缺 = CA107）。
                # 这条以前只对旧写法生效，于是规范形省掉 kind 就能让 CA501（层级方向）
                # 整条静默跳过——同一句话两种写法两个结果（评审 F2）。
                for m in ("kind", "critical"):
                    if m not in item:
                        errs.append(SchemaError(
                            "CA107", f"{where} 是 depends_on 边，缺必填字段 `{m}`（§5.4）"))
                if "kind" not in item or "critical" not in item:
                    continue
                if not ID_RE.match(item["target"]):
                    errs.append(SchemaError(
                        "CA109", f"{where}.target={item['target']!r} 不符合 id 格式 ^[a-z0-9-]+$"))
                    continue
            attrs = {k: v for k, v in item.items() if k not in ("type", "target")}
            # 归一化关系名：契约自己声明的每一种拼法都必须与具名字段等价
            out.append(Relation(canonical_type, item["target"], attrs))
        return out, errs

    @cached_property
    def named_relations(self) -> tuple[list[Relation], list[SchemaError]]:
        """契约 aliases 的九个具名字段 → 边，`type` 一定是规范名。

        canon_refs/conflicts_with/depends_on 沿用各自的老解析器（错误文案更细，判定侧按
        各自规则报）；其余六个 classlint 专有字段第一次真正进统一视图，它们的形状错误
        记在 `named_relation_errors` 里——接线不许顺手把错误吞掉。
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
        errs: list[SchemaError] = []
        for field in LEGACY_RELATION_FIELDS:
            if field in CLASSIC_RELATION_FIELDS:
                continue
            name, attrs = _RELATION_FIELD_SPECS[field]
            edges, field_errs = _parse_named_relation(
                self.meta.get(field), field, name, attrs)
            out.extend(edges)
            errs.extend(field_errs)
        return out, errs

    @property
    def named_relation_errors(self) -> list[SchemaError]:
        """六个新接线具名字段的形状问题（三个老字段的问题仍在各自访问器里）。"""
        return self.named_relations[1]

    @cached_property
    def relations(self) -> list[Relation]:
        """**统一视图**：全部边，旧具名字段在前、规范形 `relations` 在后。

        具名字段与规范形 `relations` 都在这里；`type` 一律是契约规范名，
        所以「同一条边写在哪」对任何 `edges_of()` 调用者都不可见。
        """
        out: list[Relation] = list(self.named_relations[0])
        out.extend(self.canonical_relations[0])
        return out

    @property
    def declares_dependencies(self) -> bool:
        """作者是否就「依赖」这件事做了声明（PROTOCOL §5.3「字段必须在」）。

        两种写法必须是同一句话，所以这里的判据是**声明**而不是「有没有边」：

        - 旧写法 `depends_on: []` —— 字段在，声明了「没有依赖」；
        - 规范形 `relations: []` —— 整张关系表是空的，同样是声明了「没有依赖」；
        - 规范形里只有别的边（例如只有一条 `conflicts-with`）—— 作者对依赖**什么都没说**，
          与旧写法只写 `conflicts_with:` 一样，不算声明。注意「写了 depends_on 边但形状
          写错」**算**声明（`relations:` 里有这一项就够）：那种错由 CA107 罚，不该再叠一条
          CA302，否则同一句话两种写法的输出条数就不一样了。

        「空依赖 + 别的边」用混用写法表达（`relations:` 放别的边、`depends_on: []` 显式声明空），
        混用是契约支持的写法，见 `mixed_relation_forms`。
        """
        if "depends_on" in self.meta:
            return True
        raw = self.meta.get(RELATIONS_FIELD)
        if not isinstance(raw, list):
            return False
        if not raw:
            return True
        return any(isinstance(i, dict)
                   and canonical_relation_name(str(i.get("type") or "")) == "depends_on"
                   for i in raw)

    @property
    def raw_relation_names(self) -> list[str]:
        """规范形 `relations` 里**原样写下**的 type 值（未归一化）。

        只有这个字段携带用户自选的关系名——具名字段的「名字」就是字段名，写错会撞
        CA106。CA110 拼写近失守卫据此工作：看的是作者写下的那个词，不是归一化结果。
        """
        raw = self.meta.get(RELATIONS_FIELD)
        if not isinstance(raw, list):
            return []
        return [item["type"] for item in raw
                if isinstance(item, dict) and isinstance(item.get("type"), str)]

    def edges_of(self, type_: str) -> list[Relation]:
        """按关系名取边：**判定层只应该读这里**，别自己去翻旧具名字段。

        入参接受任意历史拼法（`canon-ref` / `canon_refs` …），内部比的是规范名——
        契约里写 `canon-ref` 还是 `canon_refs` 都取得到同一批边。
        """
        want = canonical_relation_name(type_)
        return [r for r in self.relations if r.type == want]

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
