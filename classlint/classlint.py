#!/usr/bin/env python3
"""classlint — 马克思主义政治经济学审计工具，协议 v0.1（生产关系层）

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
Git + Markdown 是唯一事实来源：条目 = codex/ 下一个带 YAML frontmatter 的 Markdown 文件。
规则编号即协议：本文件实现 PROTOCOL.md 全部规则（CL1xx 结构 + PE001–PE003）。

用法:
  classlint.py init [目录]        初始化世界仓库（目录结构 + classlint.yaml + git）
  classlint.py check [目录]       审计（--json 机器可读输出）
退出码: 0=无 error 1=存在 error 2=用法/环境/配置错误
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

VERSION = "0.1"

# ---- 协议常量（改动 = 协议变更，须升版本号）----------------------------------

# 实体 ID 规范：小写字母/数字/连字符，全库唯一，一旦发布永不更改、永不复用
ID_RE = re.compile(r"^[a-z0-9-]+$")

# 七种生产关系（协议 §2，固定语法）：relation → 允许的 optional 属性键
RELATIONS: dict[str, set[str]] = {
    "owns": {"note"},
    "controls": {"note"},
    "extracts": {"what", "note"},
    "coerces": {"note"},
    "legitimizes": {"note"},
    "owes": {"what", "note"},
    "depends_on": {"critical", "kind", "note"},
}
ATTR_TYPES = {"what": str, "note": str, "kind": str, "critical": bool}
KNOWN_FIELDS = {"id", "title", "type"} | set(RELATIONS)
REQUIRED_FIELDS = ["id", "title", "type"]

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

# ---- 数据模型与解析（解析器自 canonlint 抽取）---------------------------------

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


@dataclass
class Edge:
    """一条关系边：src 条目 —rel→ target。rel ∈ RELATIONS。"""
    rel: str
    target: str
    attrs: dict


@dataclass
class Finding:
    rule: str
    level: str  # error | warning
    entry: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.level:7s} {self.entry}: {self.message}"


@dataclass
class Entry:
    """一个条目 = 一个带 YAML frontmatter 的 Markdown 文件。"""
    path: Path
    rel: str
    meta: dict
    body: str
    parse_error: str | None = None

    @property
    def id(self) -> str | None:
        v = self.meta.get("id")
        return v if isinstance(v, str) else None

    @cached_property
    def edges(self) -> tuple[list[Edge], list[Finding]]:
        """解析七种关系字段（协议 §2.1：简式 id 字符串或对象式），结果缓存。"""
        out: list[Edge] = []
        errs: list[Finding] = []
        for rel, allowed_attrs in RELATIONS.items():
            raw = self.meta.get(rel)
            if raw is None:
                continue
            if not isinstance(raw, list):
                errs.append(Finding("CL104", "error", self.rel,
                                    f"{rel} 必须是列表"))
                continue
            for i, item in enumerate(raw):
                where = f"{rel}[{i}]"
                if isinstance(item, str):
                    out.append(Edge(rel, item, {}))
                    continue
                if not isinstance(item, dict):
                    errs.append(Finding("CL104", "error", self.rel,
                                        f"{where} 必须是 id 字符串或对象"))
                    continue
                tid = item.get("id")
                if not isinstance(tid, str):
                    errs.append(Finding("CL104", "error", self.rel,
                                        f"{where} 缺 id 或 id 不是字符串"))
                    continue
                bad = False
                for k, v in item.items():
                    if k == "id" or str(k).startswith("x-"):
                        continue
                    if k not in allowed_attrs:
                        errs.append(Finding("CL104", "error", self.rel,
                                            f"{where} 含 {rel} 未定义的属性 `{k}`"))
                        bad = True
                    elif not isinstance(v, ATTR_TYPES[k]):
                        errs.append(Finding("CL104", "error", self.rel,
                                            f"{where}.{k}={v!r} 类型错误"
                                            f"（须为 {ATTR_TYPES[k].__name__}）"))
                        bad = True
                if not bad:
                    out.append(Edge(rel, tid,
                                    {k: v for k, v in item.items() if k != "id"}))
        return out, errs


def parse_entry(path: Path, root: Path) -> Entry:
    rel = str(path.relative_to(root))
    try:
        # utf-8-sig：容忍 BOM，避免把带 BOM 的文件误判为「缺少 frontmatter」
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as e:
        # 无法读取也是「文件无法解析」，按 CL100 报，而不是让 traceback 逃逸
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
    return entries, index, findings


# ---- 世界模型（引擎遍历，规则只判断）------------------------------------------


class World:
    """引擎建好的世界模型：条目索引 + 全部关系边。规则通过它查询，不自己遍历文件。"""

    def __init__(self, entries: list[Entry], index: dict[str, Entry]):
        self.entries = entries
        self.index = index
        self.edges: list[tuple[str, Edge]] = []  # (src_id, edge)
        for e in index.values():
            for edge in e.edges[0]:
                self.edges.append((e.id, edge))

    def edges_of(self, rel: str) -> list[tuple[str, Edge]]:
        return [(s, e) for s, e in self.edges if e.rel == rel]

    def find_edge(self, src: str, rels: set[str], dst: str) -> Edge | None:
        for s, e in self.edges:
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
    for src, e in world.edges_of("extracts"):
        if world.find_edge(src, {"controls", "coerces", "owns"}, e.target) is None:
            emit(None, world.index[src].rel,
                 f"extracts → `{e.target}` 无基础：对该目标没有任何 controls/coerces/owns 边")


@rule("PE002", "error", "不能镇压自己的供养者")
def pe002(world: World, emit) -> None:
    for src, e in world.edges_of("coerces"):
        dep = world.find_edge(src, {"depends_on"}, e.target)
        if dep is None:
            continue
        if dep.attrs.get("critical") is True:
            emit("error", world.index[src].rel,
                 f"一边 coerces → `{e.target}`，一边对其 critical 依赖（断供即崩）"
                 "——镇压自己的供养者")
        else:
            emit("warning", world.index[src].rel,
                 f"一边 coerces → `{e.target}`，一边对其 depends_on（非 critical）"
                 "——镇压与供养重叠，请确认")


@rule("PE003", "error", "合法性不得无锚闭环")
def pe003(world: World, emit) -> None:
    """legitimizes 子图的环状 SCC：无分量外输入边 = 无锚闭环。有锚互锁合法（WGP v0.5 魔戒案例）。"""
    adj: dict[str, set[str]] = {}
    for src, e in world.edges_of("legitimizes"):
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
        emit(None, world.index[rep].rel,
             f"legitimizes 闭环无外部锚点: {loop}——合法性不能凭空互证")


@rule("PE004", "error", "剩余必须收敛：extracts 子图无环（定性版）")
def pe004(world: World, emit) -> None:
    """定性版：环状 extracts SCC = 剩余在循环中互相凭空抽取、不落地于任何生产（黑洞）。
    定量判定（抽取量 vs 剩余量）待流量层数据就位后回填。"""
    adj: dict[str, set[str]] = {}
    for src, e in world.edges_of("extracts"):
        if e.target in world.index:
            adj.setdefault(src, set()).add(e.target)
            adj.setdefault(e.target, set())

    for members in _cyclic_sccs(adj):
        rep = min(members)
        loop = " ↔ ".join(sorted(members)) if len(members) > 1 else f"{members[0]}（自环）"
        emit(None, world.index[rep].rel,
             f"extracts 存在环: {loop}——剩余在循环中不落地于生产（黑洞）")


@rule("PE005", "warning", "劳动者必须被覆盖：被抽取者的再生产必须可见（定性版）")
def pe005(world: World, emit) -> None:
    """定性版：若 A —extracts→ B 且 B 无任何来源侧出边（不抽取谁、也不靠谁养），
    则 B 的剩余/再生产在模型里不可见（隐形剥削嫌疑）。报在 B 侧——修法是标注 B 的
    depends_on/extracts，或确认 B 为终端生产者。定量判定待流量层回填。"""
    has_source_edge = {src for src, e in world.edges
                       if e.rel in ("extracts", "depends_on")}
    for src, e in world.edges_of("extracts"):
        if e.target not in world.index:
            continue  # CL105 已报
        if e.target not in has_source_edge:
            emit(None, world.index[e.target].rel,
                 f"被 `{src}` 抽取，但本条目没有任何来源侧边——剩余从哪来不可见"
                 f"（请标注本条的 depends_on/extracts，或确认为终端生产者）")


class ConfigError(Exception):
    pass


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
    for src, e in world.edges:
        if e.target not in index:
            findings.append(Finding("CL105", "error", index[src].rel,
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
        seen, order = set(), []
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


def cmd_check(root: Path, as_json: bool, impact_ids: list[str]) -> int:
    """审计：输出全部发现（--impact 报告不参与退出码）。"""
    if not (root / "classlint.yaml").is_file():
        print(f"error: {root} 不是 classlint 世界仓库（缺 classlint.yaml）",
              file=sys.stderr)
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
        }, ensure_ascii=False, indent=2, default=str))
    else:
        for f in findings:
            print(f)
        for r in reports:
            print(f"[IMPACT] report  {r['subject']}: 下游待复核 → {r['downstream'] or '(无下游)'}")
        print(f"\n{len(entries)} 个条目 | {len(index)} 个有效 id | "
              f"{len(errors)} 错误 | {len(findings) - len(errors)} 警告"
              + (f" | 已关闭规则: {sorted(disabled)}" if disabled else ""))
    return 1 if errors else 0


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
    return cmd_check(root, args.json, args.impact)


if __name__ == "__main__":
    sys.exit(main())
