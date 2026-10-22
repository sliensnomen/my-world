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

其中 id 语法、一条边、frontmatter 切分与关系名词表这几件「两个引擎都要做、做法必须一样」的
事，实现只在 `store/parse.py` 一份（本模块转发出来）；本模块负责的是**存储层自己的字段视图**：
哪些字段算必填、多少个具名字段、怎么归一到 `Entry.relations`。

判定（什么组合算错）在 canonlint.py 的规则里。本模块只按**格式**报形状不合规，并且把
规则编号（CA100/CA105/CA107/CA109）当作格式规则来报——那些编号描述的是「文件写得对不对」，
不是「道理讲不讲得通」。

规范形与兼容别名
----------------
契约（`world.schema.json` 的 `x-relation-source`）规定的规范形是
`relations: [{type, target, …}]`。旧文件里的具名字段（`LEGACY_RELATION_FIELDS` 十一个）仍然
可读，读取时归一化到同一组内部对象上（`Entry.relations`）。
两者同时出现时**旧字段在前、`relations` 在后**，顺序确定，不依赖字典遍历顺序。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

# ---- 共享解析核心 ----------------------------------------------------------
# 读卡这一步（id 语法、frontmatter 切分、关系名词表、规范名归一化、一条边长什么样）
# 只有一份实现，在 store/parse.py：classlint 用的是同一份。本模块把它接进来再导出，
# 于是 `store.ID_RE` / `store.Relation` 这些既有名字都不变。
from .parse import (  # noqa: E402  (import 位置：与下面的常量定义同属于模块头)
    ALL_RELATION_NAMES,
    CANONICAL_RELATION_ITEMS,
    CODE_FENCE_RE,
    CONTRACT_ATTESTED,
    FRONTMATTER_RE,
    HTML_COMMENT_RE,
    ID_RE,
    RELATION_TYPE_NAMES,
    RELATION_VOCABULARY,
    SCHEMA_NAME,
    SCHEMA_PATH,
    RawEntry,
    Relation,
    canonical_relation_name,
    contract_deprecations,
    contract_relation_names,
    judged_relation_name,
    nearest_relation_name,
    read_frontmatter,
    shape_variants,
)

# ---- 搬家表（契约 `x-relation-vocabulary.deprecations`）---------------------

DEPRECATED_KIND_MIGRATIONS = contract_deprecations()
_MIGRATED_RELATIONS: tuple[str, ...] = tuple(b for _, _, b in DEPRECATED_KIND_MIGRATIONS)
# 「作者就依赖说过话」判据里算数的关系名：物质承重，以及从它搬出去的那些名字
_DEPENDENCY_DECLARING_RELATIONS: tuple[str, ...] = ("depends_on",) + _MIGRATED_RELATIONS


def _type_hint(want: str) -> str:
    """报错文案的既有习惯：中文类型名紧跟「必须是」，英文类型名前留一个空格。"""
    return want if not want.isascii() else f" {want}"

# ---- 字段表（**格式**，不是理论）------------------------------------------
# 表里出现 `layer` 只说明「有这么一个键」，不说明任何一层该养哪一层。

CORE_REQUIRED_FIELDS = ("id", "title", "type", "author", "date", "status",
                        "load_bearing", "canon_refs", "conflicts_with", "ai_assisted")
ANNOTATION_FIELDS = ("layer", "depends_on", "superseded_by")
RELATIONS_FIELD = "relations"

# 事件流水字段（协议 1.2/1.4/1.6）：存储层只认「有这些键」，词表与腿表是判定层的事。
# custody_of（保管断言）与 member_of（组织归属断言）不是事件腿，但同属流水族字段面，
# 一并登记在这里。
EVENT_FIELDS = ("when", "when_sort", "event_kind", "by", "to", "object", "from",
                "custody_of", "member_of")

# 能读的旧具名字段（`Entry.relations` 把它们归一化到同一视图）。
# 契约 x-relation-source.aliases 列了十一个，这里读全十一个——收口完成（旧「已知漂移」关闭）。
LEGACY_RELATION_FIELDS = ("depends_on", "conflicts_with", "canon_refs", "exchanges_with",
                          "owns", "controls", "extracts", "coerces", "legitimizes",
                          "derives_legitimacy_from", "owes")

# 三个「自古就有」的具名字段有各自的解析器与错误文案，判定侧也按各自的规则报；
# 其余七个是接线补上的，形状错误统一走 `Entry.named_relation_errors`。
CLASSIC_RELATION_FIELDS = ("canon_refs", "conflicts_with", "depends_on")

FIELD_TABLE = (frozenset(CORE_REQUIRED_FIELDS) | frozenset(ANNOTATION_FIELDS)
               | frozenset(LEGACY_RELATION_FIELDS) | {RELATIONS_FIELD}
               | frozenset(EVENT_FIELDS))

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
    "derives_legitimacy_from": ("critical", "note"),
    "owes": ("what", "note"),
}

# 规范名 → 具名字段，用来把契约里的关系名对回字段（两者今天同名，但不假设这一点）
_RELATION_FIELD_OF: dict[str, str] = {}
for _field in LEGACY_RELATION_FIELDS:
    _RELATION_FIELD_OF.setdefault(canonical_relation_name(_field), _field)

# 具名字段 → (规范名, 允许的注解键)。注解键从契约 attrs 推；depends_on 之所以多一个
# `kind`，是因为契约把它同时列进 depends_on.kind 词表（CA108），不是本层在讲理论。
# （`depends_on` 今天不走 `_parse_named_relation`，但保留这条 spec 是为了让
# 「契约 aliases 与代码表一致」这把锁能拿它比对。）
_ANNOTATION_KEYS: dict[str, tuple[str, ...]] = {
    key: tuple(attrs) for key, attrs in NAMED_RELATION_ATTRS.items()}
_RELATION_FIELD_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {}
for _field in LEGACY_RELATION_FIELDS:
    _name = _RELATION_FIELD_OF.get(canonical_relation_name(_field), _field)
    _keys = _ANNOTATION_KEYS.get(_name, ())
    if _name == "depends_on":
        _keys = _keys + ("kind",)
    _RELATION_FIELD_SPECS[_field] = (_name, tuple(dict.fromkeys(_keys)))

# 具名字段的对象项允许的键（`id` + 该关系的注解键；x- 前缀永远允许）
_NAMED_RELATION_ITEM_KEYS: tuple[str, ...] = ("id",)

# ---- 结构 ----------------------------------------------------------------


@dataclass
class Dep:
    id: str
    kind: str
    critical: bool
    note: str | None = None  # 契约 `x-relation-source.aliases.depends_on.attrs` 里有它


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


# `Relation`（一条边）在 store/parse.py，已随共享核心一起导入——classlint 用的是同一个类。


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


def _parse_contract_dep_items(raw) -> tuple[list[Relation], list[SchemaError]]:
    """**契约级**的 `depends_on` 项解析：只要求 `id`，`kind`/`critical` 可选。

    契约 `x-relation-source.aliases.depends_on.item` 写的是「id 字符串 或
    {id, kind?, critical?}」，`x-stricter-than-contract` 记着 canonlint 额外要求
    对象式且两个注解给全（CA107），classlint 的协议 §2.2 明确把二者降为可选。
    这是**契约自己登记的差异**，所以两个引擎各自用声明的口径，但建边只有这一份代码
    （开关见 `Entry.depends_on_requires_annotations`）。
    """
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [SchemaError("CA109", "depends_on 必须是列表")]
    edges: list[Relation] = []
    errs: list[SchemaError] = []
    for i, item in enumerate(raw):
        where = f"depends_on[{i}]"
        if isinstance(item, str):
            # 简式字符串一律建边：id 语法与 world:id 由判定层报
            edges.append(Relation("depends_on", item, {}))
            continue
        if not isinstance(item, dict):
            errs.append(SchemaError("CA107", f"{where} 必须是 id 字符串或对象"))
            continue
        extra = [k for k in item if k not in ("id", "kind", "critical", "note")
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
        for k, want in (("kind", str), ("critical", bool), ("note", str)):
            if k in item and not isinstance(item[k], want):
                errs.append(SchemaError("CA109", f"{where}.{k} 必须是"
                                        + (" bool" if want is bool else "字符串")))
        edges.append(Relation("depends_on", item["id"],
                              {k: v for k, v in item.items() if k != "id"}))
    return edges, errs


# 拆分前的旧写法（清单在契约 `x-relation-vocabulary.deprecations`）：某个关系的某个注解值，
# 后来成了一个独立的关系名。迁移做在**存储层**，所以两个引擎看到的是同一条边
# （CONTRIBUTING §7：同一份数据必须得到同一份判定）。


def migrate_legacy_kind(name: str, attrs: dict) -> tuple[str, dict]:
    """按契约的搬家表把「旧关系 + 旧注解值」换成新的关系名。

    这是纯粹的名字搬家：边的两端、其余注解（`critical`/`note`）与判定结果都不变，
    只是「算不算承重」不再由那个注解值决定。没有可搬运的内容就原样返回。
    """
    for old_rel, old_kind, becomes in DEPRECATED_KIND_MIGRATIONS:
        if name == old_rel and attrs.get("kind") == old_kind:
            return becomes, {k: v for k, v in attrs.items() if k != "kind"}
    return name, attrs


def _migration_message(where: str, old_rel: str, old_kind: str, becomes: str,
                       target: str, *, kind_style: bool) -> str:
    fix = (f"请改写为 {becomes}: [`{target}`]" if kind_style
           else f"请把 type 改写为 {becomes}")
    return (f"{where} 用的是拆分前的写法（{old_rel} + kind={old_kind}）："
            f"「{becomes}」现在是关系名，本条已按它判定。{fix}")


@dataclass
class Entry(RawEntry):
    """条目 + 存储层的字段视图。文件层字段（path/rel/meta/body/parse_error/id）继承自
    `RawEntry`——两个引擎的条目对象从同一个文件层结果长出来。"""

    # depends_on 项的**口径**。契约的 `x-stricter-than-contract` 第一条自己登记了这处差异：
    # 「本契约只要求 id；canonlint 额外要求 kind 与 critical 一并给全（CA107），classlint
    # 只要求 id」（classlint 侧写在自己的协议 §2.2：八层链与 kind 分族是 WGP 治理层的建模
    # 工具，审计只关心边的存在性与方向）。既然是**声明的**口径而不是漂移，就把它做成一个
    # 开关：两条口径各有一个名字，但建边只有这一份代码。
    # 注意：这里**不能**写类型标注——`@dataclass` 会把带标注的类属性变成字段，字段默认值
    # 会在 `__init__` 里覆盖子类的类属性，开关就永远关不掉。
    depends_on_requires_annotations = True

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

    def meta_field(self, field: str):
        """按字段名取值：规范键优先，其次契约登记的历史拼法（`canon-ref:` / `depends-on:`）。

        契约 `x-relation-vocabulary.value.accept` 说这些拼法「工具必须一并认下」，以前
        只有 `relations[].type` 那条路认（`canonical_relation_name`），**字段名这条路
        完全没认**：`canon-ref: [b]` 在 canonlint 报 CA106「未定义字段」，在 classlint
        被收下却不建边——同一张卡一个硬错误、一个整族规则静默失效。认下的范围严格等于
        契约的登记表（`canonical_relation_name`），不顺手放宽到编辑距离 ≤1 的机械变体：
        字段名拼错该报错，不该被猜。
        """
        if field in self.meta:
            return self.meta[field]
        for key in self.meta:
            if isinstance(key, str) and canonical_relation_name(key) == field:
                return self.meta[key]
        return None

    @cached_property
    def deps(self) -> tuple[list[Dep], list[SchemaError]]:
        """解析 depends_on（§5.4 schema），结果缓存。"""
        raw = self.meta_field("depends_on")
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
            extra = [k for k in item if k not in ("id", "kind", "critical", "note")
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
            # `note` 是仅供人读的注解：取值不合格式也要报，但**照旧建边**（形状坏掉时
            # 不吞边，是本模块的既定分工；没有别的规则在看 note 的取值）。
            if "note" in item and not isinstance(item["note"], str):
                errs.append(SchemaError("CA109", f"{where}.note 必须是字符串"))
            deps.append(Dep(item["id"], item["kind"], item["critical"], item.get("note")))
        return deps, errs

    @cached_property
    def conflicts(self) -> tuple[list[ConflictRef], list[SchemaError]]:
        """解析 conflicts_with（§4.1：简式字符串或带 stance 的对象），结果缓存。

        契约 `x-relation-source.aliases.conflicts_with` 只给了 `stance` 一个注解，而
        `$defs/legacyItem` 是 `additionalProperties: false`——所以这里要检查未声明的属性
        （以前对象式写什么键都收下，写错的注解既不报错也不进边）。但**取值**不管：
        `stance` 写成列表也必须照旧建边，由判定层的 CA102 报「取值非法」——这是本模块
        的既定分工（形状坏掉时照旧建边，坏值留给判定层）。存储层抢着报会把 CA102 变成
        CA109，等于把一条判定规则悄悄搬走。
        """
        raw = self.meta_field("conflicts_with")
        if raw is None:
            return [], []
        if not isinstance(raw, list):
            return [], [SchemaError("CA109", "conflicts_with 必须是列表")]
        refs, errs = [], []
        for i, item in enumerate(raw):
            where = f"conflicts_with[{i}]"
            if isinstance(item, str):
                refs.append(ConflictRef(item, None))
                continue
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                errs.append(SchemaError("CA109", f"{where} 必须是 id 字符串或含 id 的对象"))
                continue
            extra = [k for k in item if k not in ("id", "stance")
                     and not str(k).startswith("x-")]
            for x in extra:
                errs.append(SchemaError("CA107", f"{where} 含未定义字段 `{x}`（扩展须 x- 前缀）"))
            refs.append(ConflictRef(item["id"], item.get("stance")))
        return refs, errs

    @cached_property
    def canon_ref_ids(self) -> tuple[list[str], list[SchemaError]]:
        """canon_refs 必须是字符串列表，结果缓存。"""
        raw = self.meta_field("canon_refs")
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
            # 归一化分两级：契约登记的历史拼法 + 编辑距离 ≤1 的近失（`depend_on`）。
            # 第二级必须**真的换名建边**，否则 CA110 说「已按规范名判定」而那条边根本
            # 没进图（评审 blocker：漏判 CA401/CA501/CA504，冤报 CA302/CA503）。
            canonical_type = judged_relation_name(item["type"])
            if canonical_type == "depends_on" and self.depends_on_requires_annotations:
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
            # 再搬一次家：`kind: legitimacy` 是拆分前的写法（见 migrate_legacy_kind）
            canonical_type, attrs = migrate_legacy_kind(canonical_type, attrs)
            out.append(Relation(canonical_type, item["target"], attrs))
        return out, errs

    @cached_property
    def contract_dep_relations(self) -> tuple[list[Relation], list[SchemaError]]:
        """**契约级**的 depends_on 边：只有 `id` 必填（classlint 的口径）。

        与 `deps` 走的是同一个字段、同一份契约，区别只在口径：`deps` 是 canonlint 的严格
        视图（kind/critical 必填，缺一个整条不进图），这里是契约本身写下的形状。判定侧要
        哪一份由 `depends_on_requires_annotations` 决定。

        **搬家在这里也要做**：`kind: legitimacy` 是拆分前的写法，要变成关系名
        `derives_legitimacy_from`。两条口径各建一次边，搬迁就得分两处执行——漏一处就是
        评审 blocker 3 的复现（同一份数据两个引擎判得不一样）。新锁
        `check_both_engines_build_the_same_graph` 钉住了这一点。
        """
        edges, errs = _parse_contract_dep_items(self.meta.get("depends_on"))
        out: list[Relation] = []
        for edge in edges:
            name, attrs = migrate_legacy_kind(edge.type, edge.attrs)
            out.append(Relation(name, edge.target, attrs))
        return out, errs

    @cached_property
    def named_relations(self) -> tuple[list[Relation], list[SchemaError]]:
        """契约 aliases 的十一个具名字段 → 边，`type` 一定是规范名。

        canon_refs/conflicts_with/depends_on 沿用各自的老解析器（错误文案更细，判定侧按
        各自规则报）；其余六个 classlint 专有字段第一次真正进统一视图，它们的形状错误
        记在 `named_relation_errors` 里——接线不许顺手把错误吞掉。
        """
        out: list[Relation] = []
        if self.depends_on_requires_annotations:
            for dep in self.deps[0]:
                attrs = {"kind": dep.kind, "critical": dep.critical}
                if dep.note is not None:
                    attrs["note"] = dep.note
                name, attrs = migrate_legacy_kind("depends_on", attrs)
                out.append(Relation(name, dep.id, attrs))
        else:
            out.extend(self.contract_dep_relations[0])
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
                self.meta_field(field), field, name, attrs)
            out.extend(edges)
            errs.extend(field_errs)
        return out, errs

    @property
    def named_relation_errors(self) -> list[SchemaError]:
        """六个新接线具名字段的形状问题（三个老字段的问题仍在各自访问器里）。"""
        return self.named_relations[1]

    @cached_property
    def relation_migrations(self) -> list[SchemaError]:
        """旧写法的搬家记录（CA111，只提示、不改结论）。

        判定已经按契约 `deprecations` 里声明的新关系名走（存储层归一），这里只是让作者
        在输出里看见「这种写法以后别用了，该改成什么」——废弃如果完全静默，就等于留了
        一条只有工具知道的新关系名。
        """
        out: list[SchemaError] = []
        relations_raw = self.meta.get(RELATIONS_FIELD)
        for old_rel, old_kind, becomes in DEPRECATED_KIND_MIGRATIONS:
            raw = self.meta.get(old_rel)
            if isinstance(raw, list):
                for i, item in enumerate(raw):
                    if (isinstance(item, dict) and item.get("kind") == old_kind
                            and isinstance(item.get("id"), str)):
                        out.append(SchemaError("CA111", _migration_message(
                            f"{old_rel}[{i}]", old_rel, old_kind, becomes,
                            item["id"], kind_style=True)))
            if not isinstance(relations_raw, list):
                continue
            for i, item in enumerate(relations_raw):
                if not isinstance(item, dict) or not isinstance(item.get("target"), str):
                    continue
                raw_type = str(item.get("type") or "")
                if (item.get("kind") == old_kind
                        and canonical_relation_name(raw_type) == old_rel):
                    out.append(SchemaError("CA111", _migration_message(
                        f"relations[{i}]", old_rel, old_kind, becomes,
                        item["target"], kind_style=True)))
                elif raw_type == old_kind:
                    # 把注解的**取值**当成了关系名（`type: legitimacy`）。归一化会把它接到
                    # 新关系上，所以判定是对的；但文案不能再说「depends_on + kind=」——
                    # 卡里根本没有 depends_on，作者照着这句去找会找不到（评审：判得对、话说错）。
                    out.append(SchemaError("CA111", (
                        f"relations[{i}] 把注解的取值当成了关系名（type={old_kind}）："
                        f"「{becomes}」现在是独立的关系名，本条已按它判定。"
                        f"请把 type 改写为 {becomes}")))
        return out

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

        「名分依据」也算一种关于依赖的声明：它以前就写在 `depends_on` 里（`kind: legitimacy`），
        拆成关系名之后若不算，迁移过的条目会凭空多一条 CA302——而 CA503「承重墙须有物质
        来源」的义务仍由那条规则自己承担，不需要 CA302 代劳。

        「空依赖 + 别的边」用混用写法表达（`relations:` 放别的边、`depends_on: []` 显式声明空），
        混用是契约支持的写法，见 `mixed_relation_forms`。
        """
        if "depends_on" in self.meta:
            return True
        if any(isinstance(k, str) and canonical_relation_name(k) in _MIGRATED_RELATIONS
               for k in self.meta):
            return True
        raw = self.meta.get(RELATIONS_FIELD)
        if not isinstance(raw, list):
            return False
        if not raw:
            return True
        return any(isinstance(i, dict)
                   and canonical_relation_name(str(i.get("type") or "")) in
                   _DEPENDENCY_DECLARING_RELATIONS
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

    @cached_property
    def relation_shape_errors(self) -> list[SchemaError]:
        """**全部**关系形状问题，顺序固定：三个老字段 → 其余具名字段 → 规范形。

        两个引擎都从这里取。在此之前 classlint 自己建边、自己校验，于是同一份
        frontmatter 在一边是边、在另一边是错：契约声明合法的 `conflicts_with: [{id, stance}]`
        与 `exchanges_with: [{id, what}]` 被它当成「未定义的属性」，整条边消失
        （评审 blocker：契约声明合法的写法在一边变成硬错误）。
        """
        out: list[SchemaError] = []
        out.extend(self.deps[1] if self.depends_on_requires_annotations
                   else self.contract_dep_relations[1])
        out.extend(self.conflicts[1])
        out.extend(self.canon_ref_ids[1])
        out.extend(self.named_relation_errors)
        out.extend(self.relation_errors)
        return out

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
# 读文件这一步在 store/parse.py（`read_frontmatter`）——classlint 用的是同一份。
# 这里只把结果装进本引擎的 `Entry`。


def parse_entry(path: Path, root: Path) -> Entry:
    return read_frontmatter(path, root).as_entry(Entry)
