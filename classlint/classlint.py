#!/usr/bin/env python3
"""classlint — 马克思主义政治经济学审计工具，协议 v0.1（生产关系层）

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
Git + Markdown 是唯一事实来源：条目 = codex/ 下一个带 YAML frontmatter 的 Markdown 文件。
规则编号即协议：本文件实现 PROTOCOL.md 全部规则（CL1xx 结构 + PE001–PE005 + PE009）。

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

VERSION = "0.1"

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
KNOWN_FIELDS = ({"id", "title", "type", "relations"}
                | set(ALL_RELATION_NAMES) | set(CONTRACT_ATTESTED))
REQUIRED_FIELDS = ["id", "title", "type"]

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
# 条目正文可用别名指代实体，审计时统一解析到这里的稳定 ID（别名解析待实现）。
# 格式：
# entities:
#   gray-harbor:           # 稳定 ID（= 条目 frontmatter 的 id）
#     aliases: [灰港, 灰港城]
entities: {{}}
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
        return list(self.relations), errs


def parse_entry(path: Path, root: Path) -> Entry:
    # 读文件这一步在 store/parse.py（与 canonlint 共用一份）；这里只装进本引擎的 Entry。
    return shared.read_frontmatter(path, root).as_entry(Entry)


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





def load_config(root: Path) -> dict:
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
    disabled = set()
    for rid, v in rules_cfg.items():
        if rid not in RULES:
            raise ConfigError(f"rules 中未知规则编号 `{rid}`"
                              f"（可关的只有 PE 规则：{sorted(RULES)}）")
        if v != "off" and v is not False:  # YAML 1.1：未加引号的 off 会被解析成 False
            raise ConfigError(f"rules.{rid}={v!r} 非法（只支持 off）")
        disabled.add(rid)
    return {"disabled": disabled}


def run_checks(root: Path) -> tuple[list[Entry], dict[str, Entry], list[Finding], set[str]]:
    """引擎主流程：解析 → 结构规则 → 建模型 → 引用存在性 → 跑启用的 PE 规则。
    返回 (全部条目, id 索引, 发现, 被关闭的规则)。"""
    cfg = load_config(root)
    entries, index, findings = collect(root)
    world = World(entries, index)

    # CL105: 关系目标存在性
    for src, e, src_rel in world.edges:
        if e.target not in index:
            findings.append(Finding("CL105", "error", src_rel,
                                    f"{e.rel} 目标 `{e.target}` 不存在"))

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
                 "body_chars": len(e.body.strip())}
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
    args = ap.parse_args()

    root = args.root.resolve()
    if args.cmd == "init":
        return cmd_init(root)
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2
    if args.cmd == "graph":
        return cmd_graph(root, args.format)
    return cmd_check(root, args.json, args.impact, args.accept_disabled_rules)


if __name__ == "__main__":
    sys.exit(main())
