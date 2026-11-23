#!/usr/bin/env python3
"""classlint — 马克思主义政治经济学审计工具，协议 v0.6（生产关系层 + 流量层 + 个人关系层语境 + 时间线层）

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
Git + Markdown 是唯一事实来源：条目 = codex/ 下一个带 YAML frontmatter 的 Markdown 文件。
规则编号即协议：CL/PE 规则由 judges/ 的 core-cl 与 pe Pack 实现；本文件是引擎驱动
（扫描入口、World 模型、CLI、graph/view/fork）。

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

from store.contract import ContractError  # noqa: E402
try:
    from store import model as shared_model  # noqa: E402
    from store import policy as shared_policy  # noqa: E402
    from store import parse as shared  # noqa: E402
except ContractError as exc:
    print(f"error: {exc}", file=sys.stderr)
    sys.exit(2)

VERSION = "0.10"

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

# 流量层/时间线层/需求侧的字段词表与 CL108/CL109 的形状判定在 judges/cl/structure.py
# （core-cl Pack 的实现）。本文件不再复制——同一套词表两处真值是历史事故的来源。
from judges.cl.structure import REQUIRED_FIELDS  # noqa: E402  # 契约对账面（tests/test_schema.py）

def _is_finite_number(value) -> bool:
    """bool 是 int 的子类，不能当数字收下（同 canonlint 的 CA601）。"""
    return (isinstance(value, int | float) and not isinstance(value, bool)
            and value == value and value not in (float("inf"), float("-inf")))


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

    # 判定口径在 store/policy.py 显式声明（#14）：本引擎的口径 = CLASSLINT_POLICY。
    # 协议 §2.2 把 `kind`/`critical` 降为可选（八层链与 kind 分族是 WGP 治理层的建模工具，
    # 审计只关心边的存在性与方向）——所以注解开关是关的，近失换名建边保持开。
    depends_on_requires_annotations = shared_policy.CLASSLINT_POLICY.depends_on_requires_annotations
    rename_near_miss_edges = shared_policy.CLASSLINT_POLICY.rename_near_miss_edges

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


class ConfigError(Exception):
    pass
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


def load_config(root: Path, rule_ids) -> dict:
    """读 classlint.yaml。rules: {PE00x: off} 可关 PE 规则；CL 结构规则不可关。

    可关规则集合由调用方给（当前选择集里 pe Pack 登记的编号）——本函数不认识
    任何具体规则。CL 规则不在集合里，写 CL 编号自然报「未知规则编号」。
    """
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
    allowed_rules = rule_ids
    disabled = set()
    for rid, v in rules_cfg.items():
        if rid not in allowed_rules:
            raise ConfigError(f"rules 中未知规则编号 `{rid}`"
                              f"（可关的只有 PE 规则：{sorted(allowed_rules)}）")
        if v != "off" and v is not False:  # YAML 1.1：未加引号的 off 会被解析成 False
            raise ConfigError(f"rules.{rid}={v!r} 非法（只支持 off）")
        disabled.add(rid)
    return {"disabled": disabled}


def run_checks(root: Path) -> tuple[list[Entry], dict[str, Entry], list[Finding], set[str]]:
    """引擎主流程：扫描 → CL 结构规则 → 建模型 → PE 规则（judges/ 的 core-cl 与 pe Pack）。
    返回 (全部条目, id 索引, 发现, 被关闭的规则)。"""
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
    title = (str(data.get("world") or root.name).replace("&", "&amp;")
             .replace("<", "&lt;").replace(">", "&gt;"))
    html = (VIEW_TEMPLATE.replace("__TITLE__", title)
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
    r = subprocess.run(["git", "branch", "--", name], cwd=root,
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


def contract_notice() -> str | None:
    """兼容模式（契约缺失 + 显式 WGP_COMPAT_VOCAB）时给用户看的醒目提示。"""
    status = shared.contract_status()
    if not status["degraded"]:
        return None
    return ("⚠ 兼容模式：世界契约 world.schema.json 未读到，读卡词表已退回内置词表"
            f"（source={status['source']}，version={status['version']}，"
            f"fingerprint={status['fingerprint']}）。本次判定不是完整契约审计。")


def main() -> int:
    notice = contract_notice()
    if notice:
        print(notice, file=sys.stderr)
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
