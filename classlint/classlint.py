#!/usr/bin/env python3
"""classlint — 马克思主义政治经济学审计工具，协议 v0.6（生产关系层 + 流量层 + 个人关系层语境 + 时间线层）

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
Git + Markdown 是唯一事实来源：条目 = codex/ 下一个带 YAML frontmatter 的 Markdown 文件。
规则编号即协议：本文件实现 PROTOCOL.md 全部规则（CL1xx 结构 + PE001–PE014）。

用法:
  classlint.py init [目录]        初始化世界仓库（目录结构 + classlint.yaml + git）
  classlint.py check [目录]       审计（--json 机器可读输出）
退出码: 0=无 error 1=存在 error 2=用法/环境/配置错误
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

# 读卡代码（id 语法、frontmatter 切分、关系名词表与归一化、一条边）在 store/parse.py，
# 与 canonlint **共用同一份**。本引擎是判定层，存储/解析层是它的上游——所以 classlint
# 必须与仓库一起使用（单独拷走这一个文件不再支持）。
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from store import model as shared_model  # noqa: E402
from store import parse as shared  # noqa: E402

VERSION = "0.6"

# ---- 协议常量（改动 = 协议变更，须升版本号）----------------------------------

# 实体 ID 规范：小写字母/数字/连字符，全库唯一，一旦发布永不更改、永不复用。
# 实现在 store/parse.py（与 canonlint 共用一份）。
ID_RE = shared.ID_RE

# ---- 关系名词表：唯一真值在契约 world.schema.json ------------------------------
# 契约 `x-relation-vocabulary` 是唯一真值。读取与归一化（「同一关系的所有历史拼法」
# canon-ref / canon_refs … → 一个规范名）的实现在 store/parse.py，**与 canonlint 共用
# 同一份**：两个引擎把同一条边认成两个名字，就没有「同一份数据同一份判定」可言。
# 契约列过的关系名一律照单收下（不再报 CL103）；契约读不到时退化为机械变换
# （连字符↔下划线），仍然让各族关系互通。
CANONICAL_RELATION_ITEMS = shared.CANONICAL_RELATION_ITEMS


def _load_material_kinds() -> frozenset[str]:
    """从契约读 `depends_on` 的物资类别表（x-strict-vocabulary.depends_on.kind）。

    契约是唯一真值（tests/test_store.py 钉着它与 canonlint.KIND_INITIAL_SET 相等）。
    读不到时退化为这份内置表——PE005 收紧消音条件必须依赖它，宁可退化也不静默放过。
    """
    fallback = {"resource", "production", "economy", "fiscal", "manpower"}
    return frozenset(shared.contract_strict_vocabulary("depends_on.kind")) or frozenset(fallback)


RELATION_VOCABULARY: dict[str, tuple[str, ...]] = shared.RELATION_VOCABULARY
ALL_RELATION_NAMES: tuple[str, ...] = shared.ALL_RELATION_NAMES
CONTRACT_ATTESTED: frozenset[str] = shared.CONTRACT_ATTESTED


def canonical_rel(name: str) -> str:
    """把任意历史拼法的关系名归一到规范名；未知名原样返回（自由档保留自定义关系）。"""
    return shared.canonical_relation_name(name)


# F14 修复：契约列过的九种关系及其历史拼法不再报 CL103；契约之外的关系名仍然报。
# 判据是契约认证拼法 ∪ 规范名（而非机械变体）：自由档的自定义字段仍该被 CL103 拦下。
# ---- 个人关系层（协议 v0.5） ---------------------------------------------------
# 五种个人关系是 classlint 自己的语境层，不进 WGP 契约：字段只在本引擎的字段表里认，
# 形状非法一律 CL104。每条边可带 `what` 性质标签（如「兄弟」「庇护」）与 `note`。
PERSONAL_RELATIONS = ("kin", "allegiance", "bond", "affinity", "history")
PERSONAL_RELATION_ATTRS = ("what", "note")

KNOWN_FIELDS = ({"id", "title", "type", "relations"}
                | set(ALL_RELATION_NAMES) | set(CONTRACT_ATTESTED)
                | set(PERSONAL_RELATIONS))
REQUIRED_FIELDS = ["id", "title", "type"]

# ---- 流量层数据模型（协议 v0.2）----------------------------------------------
# 四条线共用一套「流量条目」：`type: flow` 的卡片声明一笔有方向的流量。
# 字段分两层：四线公有（line/from/to/note/trend）与每条线自己的必填字段。
# 这些字段**只在 type: flow 的条目上合法**——写在别的卡上仍是 CL103，
# 否则「流量」就成了任何条目都能长出来的自由字段。
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

# ---- 时间线层（协议 v0.6） -----------------------------------------------------
# 世界内历史：点事件与结构变迁。不是 canonlint 的 `type: event`（那是事件流水，
# 带 event_kind 与必填腿）；时间线条目只回答「什么时候、发生了什么、牵动谁」。
TIMELINE_TYPES = ("moment", "shift")
TIMELINE_MOMENT_FIELDS = {"at", "text", "affects", "source", "note"}
TIMELINE_SHIFT_FIELDS = {"begin", "end", "change", "before", "after", "source", "note"}
TIMELINE_FIELDS = (TIMELINE_MOMENT_FIELDS | TIMELINE_SHIFT_FIELDS) - {"note"}

# ---- 需求侧数据模型（协议 v0.3，给 Sprint 5 的守恒律用）------------------------
# 实体卡可以声明自己的需求（`demand: {what: {amount, unit}}`）与人口基数
# （`population: 数字`）。这两个字段只允许出现在**非 flow** 的条目上——需求属于消费方，
# 流量条目自己不带需求（写在 flow 卡上仍是 CL103）。格式由 CL108 校验。
FLOW_ENTITY_FIELDS = {"demand", "population"}


def _is_finite_number(value) -> bool:
    """bool 是 int 的子类，不能当数字收下（同 canonlint 的 CA601）。"""
    return (isinstance(value, int | float) and not isinstance(value, bool)
            and value == value and value not in (float("inf"), float("-inf")))


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""

# 物资类别表（契约 x-strict-vocabulary.depends_on.kind）。PE005 用它判断「来源侧边算不算数」。
MATERIAL_KINDS: frozenset[str] = _load_material_kinds()

ENTRY_ROOT = "codex"   # 条目唯一位置；目录纯组织，身份只认 frontmatter
SKIP_DIRS = {".git"}

CONFIG_SKELETON = """\
# classlint 世界配置
name: {name}
classlint: "{version}"   # 创建工具版本
rules: {{}}                # PE 规则开关（CL 结构规则不可关），如：{{PE003: off}}
"""

ENTITIES_SKELETON = """\
# 实体注册表：稳定 ID 与别名。
# 条目正文可用别名指代实体，审计时统一解析到这里的稳定 ID（正文提及见 check --json 的 mentions）。
# 格式：
# entities:
#   gray-harbor:           # 稳定 ID（= 条目 frontmatter 的 id）
#     aliases: [灰港, 灰港城]
entities: {}
"""

WORLD_DIRS = [
    "rules",
    "lore",
    "codex/characters",
    "codex/locations",
    "codex/factions",
    "stories",
    "timeline",
    "records",
]

# ---- 数据模型与解析（读卡代码与 canonlint 共用 store/parse.py）----------------

# 一条边：src 条目 —rel→ target。`rel` **一律是契约规范名**（见 canonical_rel）。
# 类型本身在 store/parse.py（`Relation`，带 `.rel` 别名），两个引擎建的是同一种边。
Edge = shared.Relation


def _personal_relation_edges(e: "Entry") -> tuple[list[Edge], list[str]]:
    """解析五种个人关系：简式 id 或对象式 `{id, what?, note?}`。返回 (边, 形状错误)。

    这五种关系**不在**契约词表里——它们是 classlint 的语境层，所以在本引擎建边，
    不往 store/model.py 里加（加进去会污染 canonlint 的契约面）。
    """
    edges: list[Edge] = []
    errors: list[str] = []
    for rel in PERSONAL_RELATIONS:
        raw = e.meta.get(rel)
        if raw is None:
            continue
        if not isinstance(raw, list):
            errors.append(f"`{rel}` 必须是列表")
            continue
        for item in raw:
            if isinstance(item, str):
                if item.strip():
                    edges.append(Edge(rel, item, {}))
                else:
                    errors.append(f"`{rel}` 的 id 不能是空串")
                continue
            if not isinstance(item, dict):
                errors.append(f"`{rel}` 的元素必须是 id 或对象")
                continue
            target = item.get("id")
            if not isinstance(target, str) or not target.strip():
                errors.append(f"`{rel}` 的对象式元素必须含字符串 `id`")
                continue
            extra = sorted(set(item) - {"id", *PERSONAL_RELATION_ATTRS})
            if extra:
                errors.append(f"`{rel}` 关系属性 `{extra[0]}` 未定义"
                              f"（允许 {'、'.join(PERSONAL_RELATION_ATTRS)}）")
            attrs: dict[str, str] = {}
            for key in PERSONAL_RELATION_ATTRS:
                if key not in item:
                    continue
                if not isinstance(item[key], str):
                    errors.append(f"`{rel}` 的 `{key}` 必须是字符串")
                else:
                    attrs[key] = item[key]
            edges.append(Edge(rel, target, attrs))
    return edges, errors


@dataclass
class Finding:
    rule: str
    level: str  # error | warning
    entry: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.level:7s} {self.entry}: {self.message}"


@dataclass
class Entry(shared_model.Entry):
    """一个条目 = 一个带 YAML frontmatter 的 Markdown 文件。

    文件层字段（path/rel/meta/body/parse_error/id）与**边层**（关系视图、形状校验、
    旧写法搬家）都继承自 `store/model.py`——两个引擎从同一份结果长出来。本类只剩
    「形状问题要说成本引擎的编号」和「depends_on 按本引擎的口径」这两件事。
    """

    # 契约 `x-stricter-than-contract` 第一条登记的口径差：本引擎的协议 §2.2 明确把
    # `kind`/`critical` 降为可选（八层链与 kind 分族是 WGP 治理层的建模工具，审计只关心
    # 边的存在性与方向）。所以这里把开关关掉——**不是**另写一份建边代码。
    depends_on_requires_annotations = False

    @cached_property
    def edges(self) -> tuple[list[Edge], list[Finding]]:
        """全部边 = 存储层的统一视图（契约是唯一真值表），结果缓存。

        本引擎**不再自己建边**。以前它自带一套约 90 行的建边与形状校验，于是同一份
        frontmatter 两个引擎给出两种结果：契约声明合法的 `conflicts_with: [{id, stance}]`
        与 `exchanges_with: [{id, what}]` 被本引擎当成「未定义的属性」，**整条边消失**；
        `depends_on` 的裸字符串与缺 `critical` 在 canonlint 报错、在本引擎却是边；
        `depends_on + kind: legitimacy` 的搬家只在 canonlint 侧执行，PE002/PE003 因此
        对同一份数据判得不一样（评审 blocker）。

        形状问题一律映射成 CL104：本引擎只有这一个形状编号，存储层用的是 canonlint 的
        CA107/CA109（契约 x-stricter-than-contract 记着这条；文案两个引擎逐字相同）。
        """
        errs = [Finding("CL104", "error", self.rel, e.msg)
                for e in self.relation_shape_errors]
        edges = list(self.relations)
        personal, perrors = _personal_relation_edges(self)
        edges.extend(personal)
        errs.extend(Finding("CL104", "error", self.rel, msg) for msg in perrors)
        return edges, errs


def parse_entry(path: Path, root: Path) -> Entry:
    # 读文件这一步在 store/parse.py（与 canonlint 共用一份）；这里只装进本引擎的 Entry。
    return shared.read_frontmatter(path, root).as_entry(Entry)


def _demand_findings(e: Entry) -> list[Finding]:
    """CL108（v0.3 扩展）：实体卡的需求侧声明格式。

    只审非 flow 条目；`demand` 是 `{物资名: {amount, unit}}`，`population` 是正数。
    形状坏了由这里报 error——PE010/PE012 只在形状合法时才拿它做守恒判定，
    否则会出现「用坏数据下重判」的误导。
    """
    findings: list[Finding] = []

    def bad(msg: str) -> None:
        findings.append(Finding("CL108", "error", e.rel, msg))

    if "population" in e.meta:
        value = e.meta["population"]
        if not _is_finite_number(value) or value <= 0:
            bad("`population` 必须是大于 0 的数字")

    demand = e.meta.get("demand")
    if demand is None:
        return findings
    if not isinstance(demand, dict):
        bad("`demand` 必须是映射（物资名 → {amount, unit}）")
        return findings
    for what, spec in demand.items():
        if not _nonempty_str(what):
            bad("`demand` 的物资名必须是非空字符串")
            continue
        if not isinstance(spec, dict):
            bad(f"`demand.{what}` 必须是映射（含 amount/unit）")
            continue
        amount = spec.get("amount")
        if not _is_finite_number(amount) or amount <= 0:
            bad(f"`demand.{what}.amount` 必须是大于 0 的数字")
        if not _nonempty_str(spec.get("unit")):
            bad(f"`demand.{what}.unit` 必须是非空字符串")
        for key in spec:
            if key not in ("amount", "unit"):
                bad(f"`demand.{what}` 不接受字段 `{key}`")
    return findings


def _timeline_fields_for(kind: str) -> set[str]:
    return TIMELINE_MOMENT_FIELDS if kind == "moment" else TIMELINE_SHIFT_FIELDS


def timeline_schema_findings(e: Entry) -> list[Finding]:
    """CL109：时间线条目格式（协议 §2.6）。只审 `type: moment` / `type: shift`。"""
    kind = e.meta.get("type")
    if kind not in TIMELINE_TYPES:
        return []
    findings: list[Finding] = []

    def bad(msg: str) -> None:
        findings.append(Finding("CL109", "error", e.rel, msg))

    allowed = _timeline_fields_for(kind)
    for key in e.meta:
        if key in TIMELINE_FIELDS and key not in allowed:
            bad(f"{kind} 不接受字段 `{key}`")
    if kind == "moment":
        if not _is_finite_number(e.meta.get("at")):
            bad("`at` 必须是数字（世界内时间轴，越大越晚）")
        if not _nonempty_str(e.meta.get("text")):
            bad("`text` 必须是非空字符串（事件描述）")
        affects = e.meta.get("affects")
        if not isinstance(affects, list) or not affects:
            bad("`affects` 必须是非空列表（受影响实体的 id）")
        else:
            for item in affects:
                if not _nonempty_str(item):
                    bad("`affects` 的元素必须是字符串 id")
    else:
        for key in ("begin", "end"):
            if not _is_finite_number(e.meta.get(key)):
                bad(f"`{key}` 必须是数字（区间端点）")
        begin, end = e.meta.get("begin"), e.meta.get("end")
        if _is_finite_number(begin) and _is_finite_number(end) and begin > end:
            bad("`begin` 不能晚于 `end`")
        for key in ("change", "before", "after"):
            if not _nonempty_str(e.meta.get(key)):
                bad(f"`{key}` 必须是非空字符串")
    source = e.meta.get("source")
    if source is not None and not _nonempty_str(source):
        bad("`source` 必须是字符串 id（第一条目世界外历史/设定来源，不进时间线）")
    if "note" in e.meta and not isinstance(e.meta["note"], str):
        bad("`note` 必须是字符串")
    return findings


def flow_schema_findings(e: Entry) -> list[Finding]:
    """CL108：流量条目的四线 schema（协议 §2.3）与实体卡需求声明（§2.4）。

    只审 `type: flow` 的条目；字段词表是流量层自己的，不写进契约的 KNOWN_FIELDS——
    所以「哪些字段合法」是**按条目类型**决定的：flow 卡上放行 FLOW_FIELDS，
    别的卡上写 `line` / `amount` 仍然被 CL103 拦下；反过来 `demand`/`population`
    只在非 flow 卡上合法。双后端（legacy 与 core-cl）必须给出逐条相同的 Finding，
    由 classlint/tests/run_tests.py 的双跑守住。
    """
    if e.meta.get("type") != "flow":
        return _demand_findings(e)

    findings: list[Finding] = []

    def bad(msg: str) -> None:
        findings.append(Finding("CL108", "error", e.rel, msg))

    line = e.meta.get("line")
    if line is None:
        bad("流量条目必须声明 `line`（logistics/violence/information/people）")
    elif line not in FLOW_LINES:
        bad(f"`line` 必须是 logistics/violence/information/people 之一，收到 {line!r}")

    for leg, label in (("from", "起点"), ("to", "终点")):
        value = e.meta.get(leg)
        if value is None:
            bad(f"流量条目缺少必填字段 `{leg}`（{label} id）")
        elif not isinstance(value, str):
            bad(f"`{leg}` 必须是字符串 id")

    if isinstance(line, str) and line in FLOW_LINES:
        allowed = FLOW_COMMON_FIELDS | FLOW_LINE_FIELDS[line]
        for key in e.meta:
            if key in FLOW_FIELDS and key not in allowed:
                bad(f"line={line} 的流量不接受字段 `{key}`")
        for key in sorted(FLOW_LINE_FIELDS[line]):
            if key not in e.meta:
                bad(f"{line} 流量缺少必填字段 `{key}`")
            elif key == "amount":
                value = e.meta[key]
                if not _is_finite_number(value) or value <= 0:
                    bad("`amount` 必须是大于 0 的数字")
            elif key in ("supply_radius", "delay"):
                value = e.meta[key]
                if not _is_finite_number(value) or value < 0:
                    bad(f"`{key}` 必须是 ≥0 的数字")
            elif key in ("unit", "radius_unit", "what"):
                if not _nonempty_str(e.meta[key]):
                    bad(f"`{key}` 必须是非空字符串")

    trend = e.meta.get("trend")
    if trend is not None and trend not in FLOW_TRENDS:
        bad("`trend` 只能是 rising/flat/falling")
    if "note" in e.meta and not isinstance(e.meta["note"], str):
        bad("`note` 必须是字符串")
    return findings


def collect(root: Path) -> tuple[list[Entry], dict[str, Entry], list[Finding]]:
    """扫描 codex/ 下全部条目 + CL100–CL103 结构规则。
    重复 id：首个（按路径序）入索引，后续不入索引（报 CL102）。"""
    entries: list[Entry] = []
    codex = root / ENTRY_ROOT
    if codex.is_dir():
        for p in sorted(codex.rglob("*.md")):
            if not p.is_file():
                # rglob("*.md") 也会返回同名目录与悬空符号链接，跳过而非崩溃
                continue
            if SKIP_DIRS & set(p.relative_to(root).parts):
                continue
            entries.append(parse_entry(p, root))

    findings: list[Finding] = []
    index: dict[str, Entry] = {}
    for e in entries:
        if e.parse_error:
            findings.append(Finding("CL100", "error", e.rel, e.parse_error))
            continue
        for f in REQUIRED_FIELDS:
            if f not in e.meta:
                findings.append(Finding("CL101", "error", e.rel, f"缺少必填字段 `{f}`"))
        for k in e.meta:
            if k not in KNOWN_FIELDS and not str(k).startswith("x-"):
                # 流量层字段只在 `type: flow` 的条目上合法（§2.3）：写进实体卡仍是 CL103。
                if e.meta.get("type") == "flow" and k in FLOW_FIELDS:
                    continue
                # 需求侧字段只在非 flow 的条目上合法（§2.4）：写进流量卡仍是 CL103。
                if e.meta.get("type") != "flow" and k in FLOW_ENTITY_FIELDS:
                    continue
                # 时间线字段只在对应类型上合法（§2.6）：moment 写 begin、shift 写 at 仍是 CL103。
                if e.meta.get("type") in TIMELINE_TYPES and k in TIMELINE_FIELDS:
                    continue
                findings.append(Finding("CL103", "error", e.rel,
                                        f"未定义字段 `{k}`（扩展字段须 x- 前缀）"))
        # CL107：关系名拼写近失。存储层已经把这条边**按规范名建好**（所以 PE 族判得到
        # 它），但作者写下的那个词与判定用的名字不同，必须说出来——否则「我明明写的是
        # extractss，工具却判 extracts」是一句无法追溯的结论。
        for raw_name in e.raw_relation_names:
            near = shared.nearest_relation_name(raw_name)
            if near is not None:
                findings.append(Finding(
                    "CL107", "warning", e.rel,
                    f"关系名 `{raw_name}` 与规范名 `{near}` 只差一个字符，疑似拼写错误，"
                    f"已按 `{near}` 判定；确是新关系请改用其它名字或加 `x-` 前缀"))
        findings.extend(flow_schema_findings(e))
        findings.extend(timeline_schema_findings(e))
        if e.id is not None and not ID_RE.match(e.id):
            findings.append(Finding("CL102", "error", e.rel,
                                    f"id={e.id!r} 非法（仅允许小写字母/数字/连字符）"))
        elif e.id is not None:
            if e.id in index:
                findings.append(Finding("CL102", "error", e.rel,
                                        f"id `{e.id}` 重复：{index[e.id].rel} 与 {e.rel}"))
            else:
                index[e.id] = e
        findings.extend(e.edges[1])
    # CL106: 拆分前的写法（`depends_on` + `kind=legitimacy`）。存储层已经把它归一成
    # 关系名 derives_legitimacy_from 并按那条关系判定，这里只提示作者改写法——canonlint
    # 的 CA111 是同一件事。搬家如果完全静默，就等于留了一条只有工具知道的新关系名，
    # 而且本引擎的 PE002/PE003 会因此和作者以为的写法对不上（评审 blocker 3）。
    for e in entries:
        for err in e.relation_migrations:
            findings.append(Finding("CL106", "warning", e.rel, err.msg))
    return entries, index, findings


# ---- 世界模型（引擎遍历，规则只判断）------------------------------------------


class World:
    """引擎建好的世界模型：条目索引 + 全部关系边。规则通过它查询，不自己遍历文件。"""

    def __init__(self, entries: list[Entry], index: dict[str, Entry]):
        self.entries = entries
        self.index = index
        # id → 该 id 在索引里的那一条（撞 id 时按路径序首个赢，与 canonlint 的 CA105 同口径）。
        # 规则要用「来源的路径」时一律走 `rel_of`，别再自己去翻 `index[...].rel`——
        # 被遮蔽的条目不在 index 里，直接下标会 KeyError，而它在图里是有的。
        self.rel_of: dict[str, str] = {e.id: e.rel for e in entries if e.id is not None}
        self.edges: list[tuple[str, Edge, str]] = []  # (src_id, edge, 写下这条边的文件)
        # 遍历的是**全部条目**，不是 `index.values()`：两张卡撞同一个 id 时，被遮蔽的那一张
        # 不进索引（依路径序首个赢），但它写下的出边照旧要判——canonlint 侧早就这么做
        # （CA105 那一行写着「被遮蔽那一份自己的出边照旧检查」），classlint 只在索引上兜圈，
        # 于是同一个世界两个引擎的结论不同：无撞 id 报 2 条 CL105，有撞 id 只剩 1 条 CL102。
        for e in entries:
            if e.id is None:
                continue
            for edge in e.edges[0]:
                self.edges.append((e.id, edge, e.rel))
                # 「名分依据」与「正当化」是同一断言的两个方向：A derives_legitimacy_from B
                # 就是 B legitimizes A。这里把反向边物化出来，PE003（找自我正当化的闭环）
                # 因此不必关心作者把边写在哪一端——两个引擎对同一份数据必须同判。
                # 目标必须真实存在：悬空的名分来源不能凭空充当锚点（悬空已由 CA401/CL105 报）。
                if edge.rel == "derives_legitimacy_from" and edge.target in index:
                    self.edges.append(
                        (edge.target, Edge("legitimizes", e.id,
                                           {"note": edge.attrs.get("note", "")}), e.rel))

    def edges_of(self, rel: str) -> list[tuple[str, Edge, str]]:
        """按关系名取边。入参允许任意历史拼法（canon-ref / canon_refs / canon_refs），
        与存储层 `Entry.edges_of` 同一语义：查的是规范名。"""
        want = canonical_rel(rel)
        return [(s, e, rel_) for s, e, rel_ in self.edges if e.rel == want]

    def find_edge(self, src: str, rels: set[str], dst: str) -> Edge | None:
        for s, e, _rel in self.edges:
            if s == src and e.rel in rels and e.target == dst:
                return e
        return None


# ---- 规则注册机制（ESLint 插件模型：注册 → 配置开关 → 引擎喂模型 → emit）--------


def _cyclic_sccs(adj: dict[str, set[str]]) -> list[list[str]]:
    """有向图的环状强连通分量（含自环）。小图用互达性 + 并查集，世界观量级足够。
    adj 须含所有涉及节点（含只有入边的）。返回成员列表的列表，无固定顺序。"""
    def reachable(start: str) -> set[str]:
        seen, stack = set(), [start]
        while stack:
            for nxt in adj.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    parent = {n: n for n in adj}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    reach = {n: reachable(n) for n in adj}
    for u in adj:
        for v in adj[u]:
            if u in reach[v]:  # v 能回到 u → 同一 SCC
                parent[find(u)] = find(v)

    groups: dict[str, list[str]] = {}
    for n in adj:
        groups.setdefault(find(n), []).append(n)
    return [m for m in groups.values()
            if len(m) > 1 or any(n in adj[n] for n in m)]


@dataclass
class Rule:
    id: str
    level: str
    doc: str
    fn: object  # fn(world: World, emit: Callable[[str | None, str, str], None])


RULES: dict[str, Rule] = {}


def rule(rid: str, level: str, doc: str):
    """注册一条 PE 规则。fn(world, emit)；emit(level, entry, msg)，level=None 用默认级别。"""
    def deco(fn):
        RULES[rid] = Rule(rid, level, doc, fn)
        return fn
    return deco


@rule("PE001", "error", "抽取必须有基础（controls/coerces/owns）")
def pe001(world: World, emit) -> None:
    for src, e, src_rel in world.edges_of("extracts"):
        if e.target not in world.index:
            # 目标不存在时「对不存在的目标论证它没有基础」是空话，且 CL105 已经报过。
            # 同族规则（PE003/PE005/PE009）都自己守卫悬空目标，只 PE001 以前漏了这一道。
            continue
        if world.find_edge(src, {"controls", "coerces", "owns"}, e.target) is None:
            emit(None, src_rel,
                 f"extracts → `{e.target}` 无基础：对该目标没有任何 controls/coerces/owns 边")


@rule("PE002", "error", "不能镇压自己的供养者")
def pe002(world: World, emit) -> None:
    for src, e, src_rel in world.edges_of("coerces"):
        dep = world.find_edge(src, {"depends_on"}, e.target)
        if dep is None:
            continue
        if dep.attrs.get("critical") is True:
            emit("error", src_rel,
                 f"一边 coerces → `{e.target}`，一边对其 critical 依赖（断供即崩）"
                 "——镇压自己的供养者")
        else:
            emit("warning", src_rel,
                 f"一边 coerces → `{e.target}`，一边对其 depends_on（非 critical）"
                 "——镇压与供养重叠，请确认")


@rule("PE003", "error", "合法性不得无锚闭环")
def pe003(world: World, emit) -> None:
    """legitimizes 子图的环状 SCC：无分量外输入边 = 无锚闭环。有锚互锁合法（WGP v0.5 魔戒案例）。"""
    adj: dict[str, set[str]] = {}
    for src, e, src_rel in world.edges_of("legitimizes"):
        if e.target in world.index:  # 悬空目标已由 CL105 报告
            adj.setdefault(src, set()).add(e.target)
            adj.setdefault(e.target, set())

    for members in _cyclic_sccs(adj):
        ms = set(members)
        anchored = any(u not in ms for u in adj for v in adj[u] if v in ms)
        if anchored:
            continue
        rep = min(members)
        loop = " ↔ ".join(sorted(members)) if len(members) > 1 else f"{members[0]}（自环）"
        emit(None, world.rel_of[rep],
             f"legitimizes 闭环无外部锚点: {loop}——合法性不能凭空互证")


@rule("PE004", "error", "剩余必须收敛：extracts 子图无环（定性版）")
def pe004(world: World, emit) -> None:
    """定性版：环状 extracts SCC = 剩余在循环中互相凭空抽取、不落地于任何生产（黑洞）。
    定量判定（抽取量 vs 剩余量）待流量层数据就位后回填。"""
    adj: dict[str, set[str]] = {}
    for src, e, src_rel in world.edges_of("extracts"):
        if e.target in world.index:
            adj.setdefault(src, set()).add(e.target)
            adj.setdefault(e.target, set())

    for members in _cyclic_sccs(adj):
        rep = min(members)
        loop = " ↔ ".join(sorted(members)) if len(members) > 1 else f"{members[0]}（自环）"
        emit(None, world.rel_of[rep],
             f"extracts 存在环: {loop}——剩余在循环中不落地于生产（黑洞）")


@rule("PE005", "warning", "劳动者必须被覆盖：被抽取者的再生产必须可见（定性版）")
def pe005(world: World, emit) -> None:
    """定性版：若 A —extracts→ B 且 B 没有**物质关系**的来源侧边，则 B 的剩余/再生产
    在模型里不可见（隐形剥削嫌疑）。报在 B 侧——修法是标注 B 的来源侧边，或确认 B 为
    终端生产者。定量判定待流量层回填。

    **什么算「来源侧边」**（本次收紧）：`extracts`（我在抽取别人）、`exchanges_with`
    （我在交换，即别人也在给我）、或带**物质类别** kind 的 `depends_on`（resource/
    production/economy/fiscal/manpower）。以前只要有一条任意出边就算数，于是
    `depends_on: [weather]` 一行就能消音——一条自然条件既不是生产关系也不承担再生产，
    消音的门槛低到等于没有门槛（评审：PE005 与终端生产者语义无关）。收紧之后，消音
    必须是一次**物质关系的声明**：作者得说清 B 靠的是什么类别的东西活着。
    """
    def has_material_source(src: str) -> bool:
        for owner, e, _rel in world.edges:
            if owner != src:
                continue
            if e.rel in ("extracts", "exchanges_with"):
                return True
            if e.rel == "depends_on" and e.attrs.get("kind") in MATERIAL_KINDS:
                return True
        return False

    for src, e, src_rel in world.edges_of("extracts"):
        if e.target not in world.index:
            continue  # CL105 已报
        if not has_material_source(e.target):
            emit(None, world.index[e.target].rel,
                 f"被 `{src}` 抽取，但本条目没有任何**物质**来源侧边（不抽取谁、不交换、"
                 f"也不靠带类别的物质依赖活着）——剩余从哪来不可见（请标注本条的 "
                 f"extracts/exchanges_with/带 kind 的 depends_on，或确认为终端生产者）")


class ConfigError(Exception):
    pass
@rule("PE009", "warning", "债务必须收得回来：债权关系要有能兑现它的结构")
def pe009(world: World, emit) -> None:
    """A —owes→ B（A 欠 B）时，模型里必须至少有一条**收得回来**的通道：

    - B 对 A 有 `controls` / `coerces` / `extracts` / `legitimizes` 任一条：债主能指挥、
      能强制、能从债务人身上抽取偿付，或能撤回给债务人的正当性；
    - 或 A 对 B 有**承重**的 `depends_on`（`critical: true`，或 `kind` 在物质族内）：
      债务人靠债主活着（断供即崩），债主捏着续借的开关。裸 `depends_on: [B]` 不算——
      与 PE005 对同一条裸依赖的口径一致。

    都没有 = 这笔债在模型里无法兑现，只是一句记账。债务不是「写一个 owes 就成立」的
    关系：它要能收回来，收回来的途径必须写在模型里。反面提醒：`owes` 与 `depends_on`
    是两条不同的边（债务不等于供养），所以这里**不会**因为写了 owes 就假定欠债方依赖
    债主——依赖得另外写出来。

    报在债务人侧（欠债的那张卡）。
    """
    for src, e, src_rel in world.edges_of("owes"):
        if e.target not in world.index:  # 悬空目标已由 CL105 报告
            continue
        claim = world.find_edge(e.target, {"controls", "coerces", "extracts",
                                           "legitimizes"}, src)
        if claim is not None:
            continue
        dep = world.find_edge(src, {"depends_on"}, e.target)
        if dep is not None and (dep.attrs.get("critical") is True
                                or dep.attrs.get("kind") in MATERIAL_KINDS):
            # 只有**承重**的依赖才算收得回来的通道：断供即崩（critical）或明确挂在某类
            # 物质上（kind 属物质族）。裸 `depends_on: [债主]` 不算——PE005 早就对同一条
            # 裸依赖明确拒绝（自然条件不承担再生产），一条「我依赖他」的重叠不足以上升
            # 成「他能收得回这笔债」。
            continue
        emit(None, src_rel,
             f"欠 `{e.target}` 债务，但看不到任何收得回来的途径：`{e.target}` 不指挥、不强制、"
             f"不抽取、也不为这条提供正当性，这条自己也不依赖 `{e.target}`"
             "——债权关系要有能兑现它的结构，否则只是记账")





def _flow_entries(world: World, line: str) -> list[Entry]:
    """可判的流量条目：line 对得上、from/to 都是存在字符串、且本线字段形状合法。

    形状坏掉的流量由 CL108 报，这里不拿它做守恒计算——否则「amount 写成 bool」
    会变成 0 参与求和，报出一条误导性的断供。
    """
    out: list[Entry] = []
    for e in world.entries:
        if e.meta.get("type") != "flow" or e.meta.get("line") != line:
            continue
        frm, to = e.meta.get("from"), e.meta.get("to")
        if not isinstance(frm, str) or not isinstance(to, str):
            continue
        if frm not in world.index or to not in world.index:
            continue
        if any(f.rule == "CL108" for f in flow_schema_findings(e)):
            continue
        out.append(e)
    return out


def _demand_of(world: World, eid: str) -> dict:
    demand = world.index[eid].meta.get("demand")
    return demand if isinstance(demand, dict) else {}


@rule("PE010", "error", "物流守恒：流入必须满足需求（数据不足时报 warning，不静默）")
def pe010(world: World, emit) -> None:
    logistics = _flow_entries(world, "logistics")

    # 从需求侧看：有 demand 的实体，同单位流入必须够量。
    for e in world.entries:
        if e.id is None or e.meta.get("type") == "flow":
            continue
        demand = e.meta.get("demand")
        if not isinstance(demand, dict):
            continue
        for what, spec in demand.items():
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not (_is_finite_number(amount) and _nonempty_str(unit)):
                continue
            incoming = [f for f in logistics
                        if f.meta.get("to") == e.id and f.meta.get("what") == what]
            same = [f for f in incoming if f.meta.get("unit") == unit]
            if same:
                inflow = sum(f.meta["amount"] for f in same)
                if inflow < amount:
                    emit("error", e.rel,
                         f"物流守恒：`{e.id}` 对 `{what}` 的需求是 {amount:g} {unit}，"
                         f"同单位流入只有 {inflow:g} {unit}——断供")
            elif incoming:
                units = "、".join(sorted({str(f.meta.get("unit")) for f in incoming}))
                emit("warning", e.rel,
                     f"物流守恒：`{e.id}` 对 `{what}` 的需求单位是 `{unit}`，"
                     f"流入线单位是 {units}——单位不可比，无法判定")
            else:
                emit("error", e.rel,
                     f"物流守恒：`{e.id}` 声明了 `{what}` 需求 {amount:g} {unit}，"
                     f"但没有任何物流线流入——断供")

    # 从流量侧看：每条流入都要有对账对象——目标没声明该需求，就无法判断够不够。
    for f in logistics:
        to, what = f.meta.get("to"), f.meta.get("what")
        if what in _demand_of(world, to):
            continue
        emit("warning", f.rel,
             f"物流守恒：`{to}` 没有声明对 `{what}` 的需求，这条流入无法对账"
             f"（给 `{to}` 加 demand，或确认它不需要）")


@rule("PE011", "error", "补给律：暴力线的驻军地必须有物流线到达")
def pe011(world: World, emit) -> None:
    logistics = _flow_entries(world, "logistics")
    for v in _flow_entries(world, "violence"):
        to = v.meta.get("to")
        if any(l.meta.get("to") == to for l in logistics):
            continue
        emit(None, v.rel,
             f"补给律：暴力线驻守 `{to}`，但没有任何物流线送到 `{to}`——军队跨线无补给")


@rule("PE012", "warning", "人口律：流失必须有可对账的端点")
def pe012(world: World, emit) -> None:
    for p in _flow_entries(world, "people"):
        frm, to = p.meta.get("from"), p.meta.get("to")
        if frm == to:
            emit(None, p.rel, "人口律：起点与终点是同一实体——流失没有去向")
            continue

        def has_population(eid: str) -> bool:
            value = world.index[eid].meta.get("population")
            return _is_finite_number(value) and value > 0

        if not has_population(frm) and not has_population(to):
            emit(None, p.rel,
                 f"人口律：`{frm}` 与 `{to}` 都没有声明 population——流失规模无法对账"
                 f"（给至少一端加 population）")


@rule("PE006", "warning", "危机积累：剩余刚好够活 + 抽取在上升")
def pe006(world: World, emit) -> None:
    logistics = _flow_entries(world, "logistics")
    for e in world.entries:
        if e.id is None or e.meta.get("type") == "flow":
            continue
        demand = e.meta.get("demand")
        if not isinstance(demand, dict):
            continue
        # 「抽取在增加」只认 tax/tribute 这两类协议建议词的外流；
        # 其余自由词（grain 等）算贸易，不据此报危机积累。
        extraction = sorted((f for f in logistics
                             if f.meta.get("from") == e.id
                             and f.meta.get("what") in ("tax", "tribute")
                             and f.meta.get("trend") == "rising"),
                            key=lambda f: f.id or "")
        if not extraction:
            continue
        for what in sorted(demand):
            spec = demand[what]
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not (_is_finite_number(amount) and _nonempty_str(unit)):
                continue
            inflow = sum(f.meta["amount"] for f in logistics
                         if f.meta.get("to") == e.id and f.meta.get("what") == what
                         and f.meta.get("unit") == unit)
            if not (inflow >= amount and inflow < amount * 1.1):
                continue
            f = extraction[0]
            margin = (inflow - amount) / amount if amount else 0.0
            emit("warning", e.rel,
                 f"危机积累：`{e.id}` 的 `{what}` 需求 {amount:g} {unit} 只有同单位流入 "
                 f"{inflow:g} {unit}（余量 {margin:.0%}），而抽往 `{f.meta.get('to')}` 的 "
                 f"`{f.meta.get('what')}` 线还在 rising——剩余刚好够活，抽取再加就断")
            break


@rule("PE007", "warning", "结构性压力：人口在增长 + 占有关系未变")
def pe007(world: World, emit) -> None:
    growing = sorted({p.meta.get("to") for p in _flow_entries(world, "people")
                      if p.meta.get("trend") == "rising"
                      and p.meta.get("to") in world.index})
    for eid in growing:
        involved = any((s == eid or e.target == eid)
                       for s, e, _r in world.edges if e.rel == "owns")
        if not involved:
            continue
        emit("warning", world.index[eid].rel,
             f"结构性压力：`{eid}` 人口在增长（people 流入 trend=rising），"
             f"但占有关系未变——人多了，占有格局还是旧的")


@rule("PE008", "error", "镇压自己的基础：暴力镇压的对象同时是物流供养来源")
def pe008(world: World, emit) -> None:
    logistics = _flow_entries(world, "logistics")
    seen: set[tuple[str, str]] = set()
    for src, e, src_rel in world.edges_of("coerces"):
        if e.target not in world.index:
            continue
        key = (src, e.target)
        if key in seen:
            continue
        seen.add(key)
        if not any(f.meta.get("from") == e.target and f.meta.get("to") == src
                   for f in logistics):
            continue
        emit("error", src_rel,
             f"镇压自己的基础：`{src}` 镇压 `{e.target}`，但 `{e.target}` 的物流线"
             f"在供养 `{src}`——镇压自己的供养来源")


def _personal_edge(world: World, a: str, b: str, rel: str):
    """个人关系是语境边，方向不承诺：A↔B 任一方向有这条关系就算数。"""
    for src, edge, _r in world.edges:
        if edge.rel != rel:
            continue
        if (src == a and edge.target == b) or (src == b and edge.target == a):
            return edge
    return None


@rule("PE013", "warning", "亲情与镇压矛盾：被镇压的供养者与镇压者有亲缘")
def pe013(world: World, emit) -> None:
    for src, e, src_rel in world.edges_of("coerces"):
        if e.target not in world.index:
            continue
        if world.find_edge(src, {"depends_on"}, e.target) is None:
            continue
        kin = _personal_edge(world, src, e.target, "kin")
        if kin is None:
            continue
        label = (kin.attrs.get("what") or "").strip()
        note = f"`{label}`" if label else "亲缘"
        emit("warning", src_rel,
             f"亲情与镇压矛盾：`{src}` 镇压供养自己的 `{e.target}`（PE002 报的结构矛盾），"
             f"但双方有{note}关系——私人关系可能让镇压被容忍或延迟，审计不应按纯经济人读")


@rule("PE014", "warning", "庇护关系可能缓冲危机：抽取者与被抽取者有效忠关系")
def pe014(world: World, emit) -> None:
    logistics = _flow_entries(world, "logistics")
    for f in logistics:
        what, trend = f.meta.get("what"), f.meta.get("trend")
        if what not in ("tax", "tribute") or trend != "rising":
            continue
        frm, to = f.meta.get("from"), f.meta.get("to")
        if frm not in world.index or to not in world.index:
            continue
        # 只在 PE006 的触发面上报：被抽取方有需求且同单位余量 < 10%。
        demand = _demand_of(world, frm)
        crisis = None
        for dwhat in sorted(demand):
            spec = demand[dwhat]
            if not isinstance(spec, dict):
                continue
            amount, unit = spec.get("amount"), spec.get("unit")
            if not (_is_finite_number(amount) and _nonempty_str(unit)):
                continue
            inflow = sum(x.meta["amount"] for x in logistics
                         if x.meta.get("to") == frm and x.meta.get("what") == dwhat
                         and x.meta.get("unit") == unit)
            if inflow >= amount and inflow < amount * 1.1:
                crisis = (dwhat, amount, unit, inflow)
                break
        if crisis is None:
            continue
        allegiance = _personal_edge(world, frm, to, "allegiance")
        if allegiance is None:
            continue
        dwhat, amount, unit, inflow = crisis
        label = (allegiance.attrs.get("what") or "").strip()
        note = f"`{label}`" if label else "效忠"
        margin = (inflow - amount) / amount if amount else 0.0
        emit("warning", f.rel,
             f"庇护关系可能缓冲危机：`{to}` 从 `{frm}` 抽取 `{what}`（线在 rising），"
             f"而 `{frm}` 的 `{dwhat}` 只剩 {margin:.0%} 余量，但双方有{note}关系"
             f"——危机可能被庇护网络吸收，不应按纯市场读")


def load_entity_aliases(root: Path, index: dict[str, Entry]) -> dict[str, str]:
    path = root / "codex" / "entities.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path} 解析失败: {exc}")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 顶层必须是映射")
    entities = data.get("entities", {})
    if entities is None:
        entities = {}
    if not isinstance(entities, dict):
        raise ConfigError(f"{path} 的 entities 必须是映射")
    aliases: dict[str, str] = {}
    for stable_id, record in entities.items():
        if not isinstance(stable_id, str) or not ID_RE.match(stable_id):
            raise ConfigError(f"{path} 的稳定 id 非法: {stable_id!r}")
        if stable_id not in index:
            raise ConfigError(f"{path} 的稳定 id `{stable_id}` 没有对应条目卡")
        if not isinstance(record, dict):
            raise ConfigError(f"{path} 的 `{stable_id}` 记录必须是映射")
        raw = record.get("aliases", [])
        if not isinstance(raw, list):
            raise ConfigError(f"{path} 的 `{stable_id}.aliases` 必须是列表")
        for alias in raw:
            if not isinstance(alias, str) or not alias.strip():
                raise ConfigError(f"{path} 的 `{stable_id}.aliases` 含空或非字符串别名: {alias!r}")
            if alias in aliases:
                raise ConfigError(f"{path} 的别名 `{alias}` 重复注册")
            aliases[alias] = stable_id
    return aliases


def body_mentions(body: str, aliases: dict[str, str]) -> list[dict]:
    if not aliases or not body:
        return []

    def ascii_word(char: str) -> bool:
        return char.isascii() and (char.isalnum() or char == "_")

    def boundary(char: str) -> bool:
        return ascii_word(char) or char == "-"

    ordered_aliases = sorted(aliases, key=lambda value: (-len(value), value))
    counts: dict[tuple[str, str], int] = {}
    first: dict[tuple[str, str], int] = {}
    position = 0
    while position < len(body):
        for alias in ordered_aliases:
            if not body.startswith(alias, position):
                continue
            end = position + len(alias)
            if ascii_word(alias[0]) and position > 0 and boundary(body[position - 1]):
                continue
            if ascii_word(alias[-1]) and end < len(body) and boundary(body[end]):
                continue
            key = (aliases[alias], alias)
            counts[key] = counts.get(key, 0) + 1
            first.setdefault(key, position)
            position = end
            break
        else:
            position += 1
    ordered = sorted(counts, key=lambda key: (first[key], key[0], key[1]))
    return [{"entity": entity, "alias": alias, "count": counts[(entity, alias)]}
            for entity, alias in ordered]


def load_config(root: Path, rule_ids=None) -> dict:
    """读 classlint.yaml。rules: {PE00x: off} 可关 PE 规则；CL 结构规则不可关。"""
    cfg_path = root / "classlint.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"classlint.yaml 解析失败: {e}")
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ConfigError("classlint.yaml 必须是键值映射")
    rules_cfg = cfg.get("rules") or {}
    if not isinstance(rules_cfg, dict):
        raise ConfigError("classlint.yaml 的 rules 必须是映射，如 {PE003: off}")
    allowed_rules = RULES if rule_ids is None else rule_ids
    disabled = set()
    for rid, v in rules_cfg.items():
        if rid not in allowed_rules:
            raise ConfigError(f"rules 中未知规则编号 `{rid}`"
                              f"（可关的只有 PE 规则：{sorted(allowed_rules)}）")
        if v != "off" and v is not False:  # YAML 1.1：未加引号的 off 会被解析成 False
            raise ConfigError(f"rules.{rid}={v!r} 非法（只支持 off）")
        disabled.add(rid)
    return {"disabled": disabled}


def _run_checks_registry(root: Path):
    from judges.cl.pack import apply_core_cl
    from judges.cl.structure import scan
    from judges.pe.pack import apply_pe
    from judges.registry import RegistryError, select_packs

    try:
        registry = select_packs("classlint", ["core-cl", "pe"])
    except RegistryError as exc:
        raise ConfigError(str(exc)) from exc
    core_cl, pe = registry.selected
    cfg = load_config(root, {rule.id for rule in pe.rules})
    entries, index = scan(root, parse_entry, ENTRY_ROOT, SKIP_DIRS)
    world = World(entries, index)
    findings: list[Finding] = []

    def emit(rule, level, entry, message):
        findings.append(Finding(rule, level, entry, message))

    apply_core_cl(core_cl, entries, index, world, KNOWN_FIELDS, emit)
    apply_pe(pe, world, cfg["disabled"], emit)
    return entries, index, findings, cfg["disabled"]


def run_checks(root: Path) -> tuple[list[Entry], dict[str, Entry], list[Finding], set[str]]:
    """引擎主流程：解析 → 结构规则 → 建模型 → 引用存在性 → 跑启用的 PE 规则。
    返回 (全部条目, id 索引, 发现, 被关闭的规则)；缺省走 Registry，可显式回退 legacy。"""
    from judges.registry import RegistryError, load_backend

    try:
        backend = load_backend()
    except RegistryError as exc:
        raise ConfigError(str(exc)) from exc
    if backend == "registry":
        return _run_checks_registry(root)

    cfg = load_config(root)
    entries, index, findings = collect(root)
    world = World(entries, index)

    # CL105: 关系目标存在性
    for src, e, src_rel in world.edges:
        if e.target not in index:
            findings.append(Finding("CL105", "error", src_rel,
                                    f"{e.rel} 目标 `{e.target}` 不存在"))
    # CL105（时间线层，协议 v0.6）：source 与 affects 也是跨条目引用，悬空同样要报。
    for e in entries:
        if e.meta.get("type") not in TIMELINE_TYPES:
            continue
        source = e.meta.get("source")
        if isinstance(source, str) and source not in index:
            findings.append(Finding("CL105", "error", e.rel,
                                    f"时间线来源 `{source}` 不存在"))
        affects = e.meta.get("affects")
        if isinstance(affects, list):
            for target in affects:
                if isinstance(target, str) and target not in index:
                    findings.append(Finding("CL105", "error", e.rel,
                                            f"时间线受影响实体 `{target}` 不存在"))

    # CL105（流量层，协议 v0.2）：流量条目的 from/to 也是跨条目引用，悬空同样要报。
    for e in entries:
        if e.meta.get("type") != "flow":
            continue
        for leg, label in (("from", "流量起点"), ("to", "流量终点")):
            target = e.meta.get(leg)
            if isinstance(target, str) and target not in index:
                findings.append(Finding("CL105", "error", e.rel,
                                        f"{label} `{target}` 不存在"))

    for rid in sorted(RULES):
        if rid in cfg["disabled"]:
            continue
        r = RULES[rid]

        def emit(level, entry, msg, _r=r):
            world_findings.append(Finding(_r.id, level or _r.level, entry, msg))

        world_findings: list[Finding] = []
        r.fn(world, emit)
        findings.extend(world_findings)

    return entries, index, findings, cfg["disabled"]


def impact_report(index: dict[str, Entry], subjects: list[str]) -> list[dict]:
    """影响报告：subject 的 depends_on 反向传递闭包（改 A 炸 B 的待复核队列）。
    报告级，永不进退出码。"""
    dependents: dict[str, list[str]] = {}
    for e in index.values():
        for edge in e.edges[0]:
            if edge.rel == "depends_on" and edge.target in index:
                dependents.setdefault(edge.target, []).append(e.id)

    reports = []
    for subj in subjects:
        # `seen` 预置主体：环（ra ↔ rb，或自环）会把主体带回下游，而"改 A 会炸 A"
        # 是环的结论（CA502/CL50x 报），不是影响报告的结论。canonlint 的 CA504 早就是
        # 这么做的（PROTOCOL.md「不含主体自身」），classlint 以前没跟上。
        seen, order = {subj}, []
        queue = [subj]
        while queue:
            cur = queue.pop(0)
            for dep in dependents.get(cur, []):
                if dep not in seen:
                    seen.add(dep)
                    order.append(dep)
                    queue.append(dep)
        reports.append({"subject": subj, "downstream": order})
    return reports


# ---- 命令 --------------------------------------------------------------------


def cmd_graph(root: Path, fmt: str) -> int:
    """关系图生成：节点 = 条目，边 = 七种关系。输出 DOT（Graphviz）或 JSON。"""
    if not (root / "classlint.yaml").is_file():
        print(f"error: {root} 不是 classlint 世界仓库（缺 classlint.yaml）",
              file=sys.stderr)
        return 2
    try:
        _, index, _, _ = run_checks(root)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if fmt == "json":
        print(json.dumps({
            "nodes": [{"id": e.id, "title": e.meta.get("title"),
                       "type": e.meta.get("type")} for e in index.values()],
            "edges": [{"src": s, "rel": edge.rel, "dst": edge.target,
                       "attrs": edge.attrs}
                      for s, edge in
                      [(e.id, ed) for e in index.values() for ed in e.edges[0]]
                      if edge.target in index],
        }, ensure_ascii=False, indent=2, default=str))
    else:
        lines = ["digraph world {", "  rankdir=BT;"]
        for e in index.values():
            title = str(e.meta.get("title", e.id)).replace('"', "'")
            lines.append(f'  "{e.id}" [label="{title}"];')
        for e in index.values():
            for edge in e.edges[0]:
                if edge.target in index:
                    lines.append(f'  "{e.id}" -> "{edge.target}" [label="{edge.rel}"];')
        lines.append("}")
        print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# 视图层（Sprint 9）：关系图 + 时间线，自包含 HTML（不外链）
# ---------------------------------------------------------------------------

VIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>__TITLE__ · classlint 视图</title>
<style>
  body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: #222; background: #fafafa; }
  header { padding: 14px 20px 6px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #666; font-size: 12px; }
  .tabs { display: flex; gap: 6px; padding: 8px 20px 0; }
  .tab { border: 1px solid #ccc; background: #fff; padding: 6px 14px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 13px; }
  .tab.active { background: #fff; border-bottom-color: #fff; font-weight: 600; }
  .panel { background: #fff; border: 1px solid #ccc; margin: 0 20px 20px; border-radius: 0 6px 6px 6px; }
  svg { display: block; width: 100%; height: auto; }
  .legend { display: flex; flex-wrap: wrap; gap: 12px; padding: 8px 14px; font-size: 12px; color: #555; border-top: 1px solid #eee; }
  .legend span.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub">classlint v__VERSION__ · 关系图与时间线（自包含视图；数据来自 codex/ 条目）</div>
</header>
<div class="tabs">
  <button class="tab active" data-page="page-graph">关系图</button>
  <button class="tab" data-page="page-timeline">时间线</button>
</div>
<div class="panel"><div id="page-graph"><svg id="graph" viewBox="0 0 860 620"></svg><div class="legend" id="legend"></div></div></div>
<div class="panel" hidden><div id="page-timeline"><svg id="timeline" viewBox="0 0 860 380"></svg></div></div>
<script id="view-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('view-data').textContent);
const NS = 'http://www.w3.org/2000/svg';
function h(tag, attrs, text) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (text != null) n.textContent = text;
  return n;
}
function typeColor(t) {
  const palette = ['#6c8ebf','#82b366','#d79b00','#9673a6','#b85450','#3c8dbc','#7f8c8d','#c0392b'];
  let s = 0; for (const c of (t || 'entry')) s = (s * 31 + c.charCodeAt(0)) | 0;
  return palette[Math.abs(s) % palette.length];
}
function trunc(s, n) { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }

function drawGraph() {
  const svg = document.getElementById('graph');
  svg.innerHTML = '';
  const nodes = DATA.nodes.slice().sort((a,b) => String(a.type||'').localeCompare(String(b.type||'')) || a.id.localeCompare(b.id));
  if (!nodes.length) { svg.appendChild(h('text', {x:430,y:310,'text-anchor':'middle',fill:'#888'}, '暂无条目')); return; }
  const cx = 430, cy = 305, R = nodes.length > 1 ? Math.min(250, 110 + 9 * nodes.length) : 0;
  const pos = {};
  nodes.forEach((node, i) => {
    const a = -Math.PI / 2 + 2 * Math.PI * i / nodes.length;
    pos[node.id] = {x: cx + R * Math.cos(a), y: cy + R * Math.sin(a)};
  });
  const edgeLayer = h('g', {stroke:'#999','stroke-width':1.2});
  DATA.edges.forEach(e => {
    const a = pos[e.src], b = pos[e.dst];
    if (!a || !b) return;
    edgeLayer.appendChild(h('line', {x1:a.x, y1:a.y, x2:b.x, y2:b.y, opacity:0.55}));
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    if (DATA.edges.length <= 90) {
      const label = h('text', {x:mx, y:my - 3, 'text-anchor':'middle', 'font-size':9, fill:'#777'}, trunc(e.rel, 18));
      label.appendChild(h('title', {}, e.rel));
      edgeLayer.appendChild(label);
    }
  });
  svg.appendChild(edgeLayer);
  nodes.forEach(node => {
    const p = pos[node.id];
    const g = h('g', {});
    g.appendChild(h('circle', {cx:p.x, cy:p.y, r:9, fill:typeColor(node.type), stroke:'#fff', 'stroke-width':1.5}));
    const t = h('text', {x:p.x, y:p.y + 22, 'text-anchor':'middle', 'font-size':11, fill:'#333'}, trunc(node.title || node.id, 20));
    t.appendChild(h('title', {}, (node.title || node.id) + '\\n' + node.id + (node.type ? ' · ' + node.type : '')));
    g.appendChild(t);
    svg.appendChild(g);
  });
  const legend = document.getElementById('legend');
  legend.innerHTML = '';
  const types = [...new Set(nodes.map(n => n.type || 'entry'))].sort();
  types.forEach(t => {
    const span = document.createElement('span');
    const dot = document.createElement('span');
    dot.className = 'dot'; dot.style.background = typeColor(t);
    span.appendChild(dot); span.appendChild(document.createTextNode(t + '（' + nodes.filter(n => (n.type || 'entry') === t).length + '）'));
    legend.appendChild(span);
  });
}

function drawTimeline() {
  const svg = document.getElementById('timeline');
  svg.innerHTML = '';
  const times = [];
  DATA.moments.forEach(m => { if (typeof m.at === 'number') times.push(m.at); });
  DATA.shifts.forEach(s => { if (typeof s.begin === 'number') times.push(s.begin); if (typeof s.end === 'number') times.push(s.end); });
  if (!times.length) { svg.appendChild(h('text', {x:430,y:190,'text-anchor':'middle',fill:'#888'}, '暂无时间线条目（moment / shift）')); return; }
  const lo = Math.min.apply(null, times), hi = Math.max.apply(null, times);
  const span = (hi - lo) || 1;
  const x = t => 70 + (t - lo) / span * 720;
  const axisY = 185;
  svg.appendChild(h('line', {x1:60, y1:axisY, x2:800, y2:axisY, stroke:'#999'}));
  [lo, hi].forEach((t, i) => {
    svg.appendChild(h('text', {x:x(t), y:axisY + 16, 'text-anchor':'middle', 'font-size':10, fill:'#888'}, String(+t.toFixed(2))));
    svg.appendChild(h('line', {x1:x(t), y1:axisY - 4, x2:x(t), y2:axisY + 4, stroke:'#999'}));
  });
  DATA.moments.forEach(m => {
    if (typeof m.at !== 'number') return;
    svg.appendChild(h('circle', {cx:x(m.at), cy:axisY, r:5, fill:'#b85450', stroke:'#fff', 'stroke-width':1}));
    const label = h('text', {x:x(m.at), y:axisY - 12, 'text-anchor':'middle', 'font-size':10, fill:'#b85450'}, trunc(m.text || m.id, 22));
    label.appendChild(h('title', {}, (m.text || m.id) + (m.source ? '\\n来源：' + m.source : '')));
    svg.appendChild(label);
  });
  const laneY = 300;
  DATA.shifts.forEach((s, i) => {
    if (typeof s.begin !== 'number' || typeof s.end !== 'number') return;
    const y = laneY + (i % 3) * 30;
    const w = Math.max(2, x(s.end) - x(s.begin));
    const rect = h('rect', {x:x(s.begin), y:y - 10, width:w, height:20, rx:4, fill:'#dbeafe', stroke:'#6c8ebf'});
    rect.appendChild(h('title', {}, (s.change || s.id) + '\\n' + (s.before || '') + ' → ' + (s.after || '')));
    svg.appendChild(rect);
    svg.appendChild(h('text', {x:x(s.begin) + 4, y:y + 4, 'font-size':10, fill:'#2c5282'}, trunc(s.change || s.id, 24)));
  });
  if (DATA.shifts.length) {
    svg.appendChild(h('text', {x:60, y:laneY - 22, 'font-size':11, fill:'#555'}, '结构变迁（shift）'));
  }
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.panel').forEach((p, i) => {
      const sections = ['page-graph', 'page-timeline'];
      p.hidden = sections[i] !== btn.dataset.page;
    });
  });
});
drawGraph();
drawTimeline();
</script>
</body>
</html>
"""


def _view_data(root: Path) -> dict:
    _, index, _, _ = run_checks(root)
    nodes = [{"id": e.id, "title": e.meta.get("title") or e.id,
              "type": e.meta.get("type")} for e in index.values()]
    edges = [{"src": e.id, "rel": edge.rel, "dst": edge.target,
              "attrs": edge.attrs}
             for e in index.values() for edge in e.edges[0]
             if edge.target in index]
    moments, shifts = [], []
    for e in index.values():
        t = e.meta.get("type")
        if t == "moment" and _is_finite_number(e.meta.get("at")):
            moments.append({"id": e.id, "at": e.meta["at"],
                            "text": e.meta.get("text"),
                            "affects": e.meta.get("affects"),
                            "source": e.meta.get("source")})
        elif t == "shift" and _is_finite_number(e.meta.get("begin")) and _is_finite_number(e.meta.get("end")):
            shifts.append({"id": e.id, "begin": e.meta["begin"],
                           "end": e.meta["end"],
                           "change": e.meta.get("change"),
                           "before": e.meta.get("before"),
                           "after": e.meta.get("after"),
                           "source": e.meta.get("source")})
    moments.sort(key=lambda m: (m["at"], m["id"]))
    shifts.sort(key=lambda s: (s["begin"], s["id"]))
    return {"nodes": nodes, "edges": edges, "moments": moments, "shifts": shifts}


def cmd_view(root: Path, out: Path | None = None) -> int:
    """生成关系图 + 时间线的自包含 HTML（无外链、无 CDN，可直接双击打开）。"""
    if not (root / "classlint.yaml").is_file():
        print(f"error: {root} 不是 classlint 世界仓库（缺 classlint.yaml）",
              file=sys.stderr)
        return 2
    try:
        data = _view_data(root)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    target = out if out is not None else root / "view.html"
    blob = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = (VIEW_TEMPLATE.replace("__TITLE__", str(data.get("world") or root.name))
            .replace("__VERSION__", VERSION).replace("__DATA__", blob))
    target.write_text(html, encoding="utf-8")
    print(f"视图已生成: {target}")
    return 0


def cmd_fork(root: Path, name: str) -> int:
    """反事实推演：把世界当前状态开成一条 Git 分支（世界内时间线的分叉点由作者在条目里记录）。"""
    if not (root / "classlint.yaml").is_file():
        print(f"error: {root} 不是 classlint 世界仓库（缺 classlint.yaml）",
              file=sys.stderr)
        return 2
    if not (root / ".git").is_dir():
        print(f"error: {root} 不是 Git 仓库——反事实推演依赖 Git 分支",
              file=sys.stderr)
        return 2
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"],
                       cwd=root, capture_output=True)
    if r.returncode != 0:
        print("error: 世界仓库还没有任何提交（HEAD 为空）——先 git add . && git commit，再开反事实分支",
              file=sys.stderr)
        return 2
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                        f"refs/heads/{name}"], cwd=root, capture_output=True)
    if r.returncode == 0:
        print(f"error: 分支 {name} 已存在", file=sys.stderr)
        return 1
    r = subprocess.run(["git", "branch", name], cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"error: git branch 失败：{r.stderr.strip()}", file=sys.stderr)
        return 2
    print(f"已从当前世界开出反事实分支：{name}")
    print("下一步：在该分支里改设定；时间线里用一条 shift 记下分歧点。")
    print(f"看分歧：git diff main..{name}；看世界外历史：git log --oneline")
    return 0


def cmd_init(root: Path) -> int:
    """初始化世界仓库：目录结构 + classlint.yaml + entities.yaml + git。"""
    root.mkdir(parents=True, exist_ok=True)
    cfg = root / "classlint.yaml"
    if cfg.exists():
        print(f"error: {root} 已是 classlint 世界仓库（classlint.yaml 已存在）",
              file=sys.stderr)
        return 1
    for d in WORLD_DIRS:
        sub = root / d
        sub.mkdir(parents=True, exist_ok=True)
        if not any(sub.iterdir()):
            (sub / ".gitkeep").touch()
    cfg.write_text(CONFIG_SKELETON.format(name=root.name, version=VERSION),
                   encoding="utf-8")
    (root / "codex" / "entities.yaml").write_text(ENTITIES_SKELETON, encoding="utf-8")
    if not (root / ".git").is_dir():
        r = subprocess.run(["git", "init"], cwd=root, capture_output=True)
        if r.returncode == 0:
            print("git 仓库已初始化")
        else:
            print("提示：git init 失败，请手动执行", file=sys.stderr)
    print(f"世界仓库已初始化: {root}")
    return 0


def cmd_check(root: Path, as_json: bool, impact_ids: list[str],
              accept_disabled_rules: bool = False) -> int:
    """审计：输出全部发现（--impact 报告不参与退出码）。

    关掉规则（`classlint.yaml` 的 `rules: {PE00x: off}`）会让「通过」这句话变弱：世界
    通过了，但通过的是一台少了几条规则的机器。以前这只看摘要行里的一句附注，退出码
    与全规则通过完全相同——于是自动化（CI、pre-commit）无法区分二者，一条规则被关掉
    就永久静默。现在返回 **3**（通过，但有规则被关闭），只有显式 `--accept-disabled-rules`
    才回到 0。约定与 canonlint 的「跳过必须显式授权」一致（tests/test_serve.py）。
    """
    if not (root / "classlint.yaml").is_file():
        print(f"error: {root} 不是 classlint 世界仓库（缺 classlint.yaml）",
              file=sys.stderr)
        return 2
    # 指错目录必须当用法错误处理：`codex/` 不在时 collect 收 0 条，会给出
    # 「0 个条目 | 0 错误」的全绿报告——那是「整批条目看起来在被审，实际一张都没审」。
    # 与 canonlint 的「不像一个世界仓库……（指错目录了？）」对齐成同一个退出码 2。
    if not (root / ENTRY_ROOT).is_dir():
        print(f"error: {root} 不像一个 classlint 世界仓库：没有 {ENTRY_ROOT}/ 目录"
              f"（指错目录了？classlint 只审 {ENTRY_ROOT}/ 下的卡片）", file=sys.stderr)
        return 2
    try:
        entries, index, findings, disabled = run_checks(root)
        aliases = load_entity_aliases(root, index)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    reports = impact_report(index, impact_ids) if impact_ids else []
    order = {"error": 0, "warning": 1}
    findings.sort(key=lambda f: (order.get(f.level, 2), f.rule, f.entry))
    errors = [f for f in findings if f.level == "error"]

    if as_json:
        print(json.dumps({
            "classlint_version": VERSION,
            "entries": [
                {"id": e.id, "path": e.rel, "meta": dict(e.meta),
                 "body_chars": len(e.body.strip()),
                 "mentions": body_mentions(e.body, aliases)}
                for e in entries if not e.parse_error
            ],
            "findings": [{"rule": f.rule, "level": f.level, "entry": f.entry,
                          "message": f.message} for f in findings],
            "reports": reports,
            "rules_disabled": sorted(disabled),
            "judgement_complete": not disabled,
        }, ensure_ascii=False, indent=2, default=str))
    else:
        for f in findings:
            print(f)
        for r in reports:
            print(f"[IMPACT] report  {r['subject']}: 下游待复核 → {r['downstream'] or '(无下游)'}")
        print(f"\n{len(entries)} 个条目 | {len(index)} 个有效 id | "
              f"{len(errors)} 错误 | {len(findings) - len(errors)} 警告"
              + (f" | 已关闭规则: {sorted(disabled)}" if disabled else ""))
        if disabled and not accept_disabled_rules:
            print(f"判定不完整：{sorted(disabled)} 被 rules: off 关闭，本次「通过」只覆盖"
                  f"仍开着的规则。确认这是有意的，请加 --accept-disabled-rules")
    if errors:
        return 1
    if disabled and not accept_disabled_rules:
        return 3
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=f"classlint — 马克思主义政治经济学审计工具 v{VERSION}")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p_init = sp.add_parser("init", help="初始化世界仓库")
    p_init.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_check = sp.add_parser("check", help="审计世界仓库")
    p_check.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_check.add_argument("--json", action="store_true", help="机器可读输出")
    p_check.add_argument("--impact", nargs="*", default=[], metavar="ID",
                         help="影响报告：指定条目的 depends_on 下游闭包（不进退出码）")
    p_check.add_argument("--accept-disabled-rules", action="store_true",
                         help="接受 rules: off 关掉的规则：关着规则也返回 0（默认返回 3）")
    p_graph = sp.add_parser("graph", help="关系图生成（DOT 或 JSON）")
    p_graph.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_graph.add_argument("--format", choices=["dot", "json"], default="dot")
    p_view = sp.add_parser("view", help="生成关系图与时间线视图（自包含 HTML）")
    p_view.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_view.add_argument("--out", type=Path, default=None,
                        help="输出路径（默认 <root>/view.html）")
    p_fork = sp.add_parser("fork", help="开一条反事实分支（Git branch）")
    p_fork.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_fork.add_argument("name", help="新分支名")
    args = ap.parse_args()

    root = args.root.resolve()
    if args.cmd == "init":
        return cmd_init(root)
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2
    if args.cmd == "graph":
        return cmd_graph(root, args.format)
    if args.cmd == "view":
        return cmd_view(root, args.out)
    if args.cmd == "fork":
        return cmd_fork(root, args.name)
    return cmd_check(root, args.json, args.impact, args.accept_disabled_rules)


if __name__ == "__main__":
    sys.exit(main())
