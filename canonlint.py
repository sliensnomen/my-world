#!/usr/bin/env python3
"""canonlint — 世界观治理协议（WGP）参考实现，协议版本 0.4

规则编号即协议：本文件实现 PROTOCOL.md §6.3 全部确定性规则（CA504 见 --impact）。
用法:
  canonlint.py <仓库根> [--strict] [--dup-threshold 0.85] [--json] [--impact ID...]
退出码: 0=通过(或仅警告) 1=存在错误(--strict 下警告也算) 2=用法/环境错误
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path

import yaml

PROTOCOL_VERSION = "1.0"

# ---- 协议常量（改动 = 协议变更，须升版本号）------------------------------

REQUIRED_FIELDS = [
    "id", "title", "type", "author", "date", "status", "load_bearing",
    "canon_refs", "conflicts_with", "ai_assisted",
]
KNOWN_FIELDS = set(REQUIRED_FIELDS) | {"layer", "depends_on", "superseded_by"}

VALID_TYPES = {"location", "faction", "character", "event", "item"}
VALID_STATUS = {"draft", "trial", "canon", "archived"}
VALID_STANCE = {"official", "heretic", "unknown"}
LAYERS = ["geo", "resource", "production", "economy", "fiscal", "military",
          "political", "ideology"]
LAYER_INDEX = {name: i for i, name in enumerate(LAYERS)}

KIND_INITIAL_SET = {"resource", "production", "economy", "fiscal",
                    "manpower", "legitimacy"}
# kind 分族（§5.4）：物质族受 CA501/CA502 约束；legitimacy 与 x- 实验值属规范族，豁免
MATERIAL_KINDS = {"resource", "production", "economy", "fiscal", "manpower"}
CA503_LAYERS = {"economy", "fiscal", "military", "political"}  # ideology 豁免
CA505_TRIGGER_LAYERS = {"military", "political"}

ID_RE = re.compile(r"^[a-z0-9-]+$")
WORLD_REF_RE = re.compile(r"^[a-z0-9-]+:")  # world:id 形式，本版不支持

# 附录 A · 承重墙关键词清单
LOAD_BEARING_KEYWORDS = ["经济", "货币", "税收", "贸易", "铸币", "政治",
                         "政权", "法律", "继承", "选帝", "军队", "征兵", "战争赔款"]

MIN_BODY_CHARS = 200        # CA104
MIN_DUP_CHARS = 100         # CA201 最短参与长度

ENTRY_DIRS = ("entries", "canon", "sandbox", "archive")  # 条目扫描目录
SKIP_DIRS = {"templates", "scripts", ".git"}

# ---- 数据模型 ------------------------------------------------------------


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
    rule: str
    msg: str


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


@dataclass
class Finding:
    rule: str
    level: str  # error | warning | info
    entry: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.level:7s} {self.entry}: {self.message}"


# ---- 解析 ----------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def parse_entry(path: Path, root: Path) -> Entry:
    rel = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8")
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


# ---- 规则 ----------------------------------------------------------------


def check_structure(e: Entry, findings: list[Finding]) -> None:
    """CA1xx 结构规则。"""
    rel = e.rel
    if e.parse_error:
        findings.append(Finding("CA100", "error", rel, e.parse_error))
        return
    for f in REQUIRED_FIELDS:
        if f not in e.meta:
            findings.append(Finding("CA101", "error", rel, f"缺少必填字段 `{f}`"))
    # 条件必填：archived 必须有 superseded_by 字段（可为 null，但字段要在）
    if e.meta.get("status") == "archived" and "superseded_by" not in e.meta:
        findings.append(Finding("CA101", "error", rel,
                                "archived 条目缺少 `superseded_by`（无承接者时填 null）"))
    if "type" in e.meta and e.meta["type"] not in VALID_TYPES:
        findings.append(Finding("CA102", "error", rel,
                                f"type={e.meta['type']!r} 非法，须为 {sorted(VALID_TYPES)}"))
    if "status" in e.meta and e.meta["status"] not in VALID_STATUS:
        findings.append(Finding("CA102", "error", rel,
                                f"status={e.meta['status']!r} 非法，须为 {sorted(VALID_STATUS)}"))
    if "layer" in e.meta and e.meta["layer"] not in LAYER_INDEX:
        findings.append(Finding("CA102", "error", rel,
                                f"layer={e.meta['layer']!r} 非法，须为 {LAYERS}"))
    if "date" in e.meta and not isinstance(e.meta["date"], date):
        findings.append(Finding("CA103", "error", rel,
                                f"date={e.meta['date']!r} 不是合法日期（须为 YYYY-MM-DD）"))
    if "id" in e.meta:
        if not isinstance(e.meta["id"], str) or not ID_RE.match(e.meta["id"]):
            findings.append(Finding("CA105", "error", rel,
                                    f"id={e.meta['id']!r} 非法（仅允许小写字母/数字/连字符）"))
    for k in e.meta:
        if k not in KNOWN_FIELDS and not str(k).startswith("x-"):
            findings.append(Finding("CA106", "error", rel,
                                    f"未定义字段 `{k}`（扩展字段须 x- 前缀）"))
    # CA109: bool 字段类型
    for bf in ("load_bearing", "ai_assisted"):
        if bf in e.meta and not isinstance(e.meta[bf], bool):
            findings.append(Finding("CA109", "error", rel,
                                    f"{bf}={e.meta[bf]!r} 必须是 bool（true/false）"))
    # CA107/CA108: depends_on schema 与 kind；CA109: conflicts/canon_refs 类型
    for err in e.deps[1]:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    for dep in e.deps[0]:
        if dep.kind in KIND_INITIAL_SET:
            continue
        if dep.kind.startswith("x-"):
            findings.append(Finding("CA108", "info", rel,
                                    f"kind={dep.kind!r} 为实验值，已计入案例收集"))
        else:
            findings.append(Finding("CA108", "error", rel,
                                    f"kind={dep.kind!r} 不在初始集且未带 x- 前缀"))
    for err in e.conflicts[1]:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    for ref in e.conflicts[0]:
        if ref.stance is not None and ref.stance not in VALID_STANCE:
            findings.append(Finding("CA102", "error", rel,
                                    f"stance={ref.stance!r} 非法，须为 {sorted(VALID_STANCE)}"))
    for err in e.canon_ref_ids[1]:
        findings.append(Finding(err.rule, "error", rel, err.msg))


def check_content(e: Entry, findings: list[Finding]) -> None:
    """CA104 篇幅、CA301 关键词触发、CA302 承重墙义务。"""
    if e.parse_error:
        return
    rel = e.rel
    if e.status in ("trial", "canon") and len(e.clean_body) < MIN_BODY_CHARS:
        findings.append(Finding("CA104", "warning", rel,
                                f"正文 {len(e.clean_body)} 字，{e.status} 档建议 ≥{MIN_BODY_CHARS} 字"))
    if e.meta.get("load_bearing") is True:
        missing = [f for f in ("layer", "depends_on") if f not in e.meta]
        if missing:
            findings.append(Finding("CA302", "error", rel,
                                    f"load_bearing: true 但缺 {missing}"))
    else:
        hay = str(e.meta.get("title", "")) + e.clean_body
        hits = [kw for kw in LOAD_BEARING_KEYWORDS if kw in hay]
        if hits:
            findings.append(Finding("CA301", "warning", rel,
                                    f"命中承重墙关键词 {hits}，但未声明 load_bearing——请考虑声明"))


def check_refs(index: dict[str, Entry], findings: list[Finding]) -> None:
    """CA4xx 引用与状态机。无传递违规原则：只判直接边。"""
    for e in index.values():
        if e.parse_error:
            continue
        rel = e.rel

        def check_target(ref_id: str, via: str) -> Entry | None:
            if WORLD_REF_RE.match(ref_id):
                findings.append(Finding("CA401", "error", rel,
                                        f"{via} 引用 {ref_id!r} 为 world:id 形式，本版协议不支持"))
                return None
            target = index.get(ref_id)
            if target is None:
                findings.append(Finding("CA401", "error", rel,
                                        f"{via} 引用指向不存在的 id `{ref_id}`"))
            return target

        for ref_id in e.canon_ref_ids[0]:
            target = check_target(ref_id, "canon_refs")
            if target is None or target.status == "canon":
                continue
            if target.status == "archived" and "superseded_by" not in target.meta:
                continue  # 由 CA405 在 archived 条目侧报告，避免双报
            if target.status == "archived":
                findings.append(Finding("CA402", "error", rel,
                                        f"canon_refs 目标 `{ref_id}` 已 archived，"
                                        f"请迁移至其 superseded_by 承接条目 `{target.meta.get('superseded_by')}`"))
            else:
                findings.append(Finding("CA402", "error", rel,
                                        f"canon_refs 目标 `{ref_id}` 状态为 {target.status}，须为 canon"))
        for dep in e.deps[0]:
            target = check_target(dep.id, "depends_on")
            if target is not None and e.status == "canon" and target.status != "canon":
                findings.append(Finding("CA404", "error", rel,
                                        f"canon 条目的 depends_on 目标 `{dep.id}` 状态为 {target.status}，须为 canon"))
        for ref in e.conflicts[0]:
            check_target(ref.id, "conflicts_with")

        # superseded_by 的目标存在性（CA401）
        sb = e.meta.get("superseded_by")
        if sb is not None:
            if not isinstance(sb, str):
                findings.append(Finding("CA109", "error", rel,
                                        f"superseded_by={sb!r} 必须是 id 字符串或 null"))
            else:
                check_target(sb, "superseded_by")

    # CA405: archived 被引用且未填 superseded_by（报在目标侧，定位到处置责任人）
    for e in index.values():
        if e.parse_error or e.status != "archived":
            continue
        referenced = any(
            ref_id == e.id
            for o in index.values() if not o.parse_error
            for ref_id in o.canon_ref_ids[0]
        )
        if referenced and "superseded_by" not in e.meta:
            findings.append(Finding("CA405", "error", e.rel,
                                    "archived 条目仍被 canon_refs 引用且未填 superseded_by（降级处置不完整）"))

    # CA403: 无回指且本方简式才报（对方是否有 stance 与本关系无关，见 §4.2 第 3 条）
    for e in index.values():
        if e.parse_error:
            continue
        for ref in e.conflicts[0]:
            target = index.get(ref.id)
            if target is None or target.parse_error:
                continue
            if any(r.id == e.id for r in target.conflicts[0]):
                continue  # 有回指即对称，不究形式
            if ref.stance is not None:
                continue  # 本方对象式 = 有意不对称
            findings.append(Finding("CA403", "warning", e.rel,
                                    f"与 `{ref.id}` 的矛盾标注不对称（对方未回指）"))


def check_chain(index: dict[str, Entry], findings: list[Finding]) -> None:
    """CA5xx 政治经济学链条。物质族边受 CA501/CA502 约束，规范族豁免。"""
    graph: dict[str, list[str]] = {}  # 仅物质族边（CA502 用）
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        deps = e.deps[0]
        graph[e.id] = [d.id for d in deps
                       if d.id in index and d.kind in MATERIAL_KINDS]

        if e.meta.get("load_bearing") is not True:
            continue
        layer = e.meta.get("layer")
        if layer not in LAYER_INDEX:
            continue  # CA102/CA302 已报
        for d in deps:
            if d.kind not in MATERIAL_KINDS:
                continue  # 规范族边豁免方向检查（§5.5）
            target = index.get(d.id)
            if target is None:
                continue  # CA401 已报
            tl = target.meta.get("layer")
            if tl in LAYER_INDEX and LAYER_INDEX[tl] > LAYER_INDEX[layer]:
                findings.append(Finding("CA501", "error", e.rel,
                                        f"depends_on 目标 `{d.id}` 层级 {tl}（序号 {LAYER_INDEX[tl]}）"
                                        f"高于本条目 {layer}（序号 {LAYER_INDEX[layer]}）"))
        # CA503: economy/fiscal/military/political 层须有物质族 critical 依赖；ideology 豁免
        if layer in CA503_LAYERS and not any(
                d.critical and d.kind in MATERIAL_KINDS for d in deps):
            findings.append(Finding("CA503", "warning", e.rel,
                                    f"{layer} 层承重墙条目无任何物质族 critical 依赖（空中楼阁提示）"))

    # CA505: 仓库级——有 military/political 承重墙但全库无任何 layer=fiscal 条目
    layers_present = {e.meta.get("layer") for e in index.values() if not e.parse_error}
    lb_layers = {e.meta.get("layer") for e in index.values()
                 if not e.parse_error and e.meta.get("load_bearing") is True}
    if lb_layers & CA505_TRIGGER_LAYERS and "fiscal" not in layers_present:
        findings.append(Finding("CA505", "warning", "(仓库级)",
                                "存在 military/political 层承重墙条目，但全库无 layer=fiscal 条目"
                                "——财政维度可能缺失（刚铎型盲区）"))

    # CA502: 环检测（仅物质族子图；三色 DFS，迭代实现防深递归）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in graph}

    for start in graph:
        if color[start] != WHITE:
            continue
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        color[start] = GRAY
        while stack:
            node, path = stack[-1]
            advanced = False
            for nxt in graph.get(node, []):
                if color.get(nxt) == GRAY:
                    cycle = path[path.index(nxt):] + [nxt]
                    findings.append(Finding("CA502", "error", index[node].rel,
                                            f"depends_on 存在环（物质族）: {' → '.join(cycle)}"))
                elif color.get(nxt) == WHITE:
                    color[nxt] = GRAY
                    stack.append((nxt, path + [nxt]))
                    advanced = True
                    break
            if not advanced:
                stack.pop()
                color[node] = BLACK


def check_duplicates(index: dict[str, Entry], threshold: float,
                     findings: list[Finding]) -> None:
    """CA201: 正文相似度（§6.6 预处理，双方 ≥100 字符才参与）。"""
    items = [(e.rel, e.clean_body) for e in index.values() if not e.parse_error]
    items = [(rel, t) for rel, t in items if len(t) >= MIN_DUP_CHARS]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            ratio = difflib.SequenceMatcher(None, items[i][1], items[j][1]).ratio()
            if ratio >= threshold:
                findings.append(Finding(
                    "CA201", "warning", f"{items[i][0]} ↔ {items[j][0]}",
                    f"正文相似度 {ratio:.0%} ≥ {threshold:.0%}，疑似重复"))


def impact_report(index: dict[str, Entry], subjects: list[str]) -> list[dict]:
    """CA504: 输出 subject 的 depends_on 反向传递闭包，按链条序号降序。"""
    dependents: dict[str, list[str]] = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for d in e.deps[0]:
            dependents.setdefault(d.id, []).append(e.id)

    reports = []
    for subj in subjects:
        seen, order = set(), []
        queue: deque[str] = deque([subj])
        while queue:
            cur = queue.popleft()
            for dep in dependents.get(cur, []):
                if dep not in seen:
                    seen.add(dep)
                    order.append(dep)
                    queue.append(dep)

        def layer_key(eid: str) -> int:
            e = index.get(eid)
            l = e.meta.get("layer") if e else None
            return LAYER_INDEX.get(l, -1)

        order.sort(key=layer_key, reverse=True)
        reports.append({"rule": "CA504", "subject": subj, "downstream": order})
    return reports


# ---- 主流程 --------------------------------------------------------------


def collect(root: Path) -> tuple[list[Entry], dict[str, Entry], list[Finding]]:
    """扫描条目目录。返回 (全部条目, id索引, 索引期发现)。
    重复 id：首个（按路径序）入索引，后续的不入索引但仍参与结构检查。"""
    dirs = [root / d for d in ENTRY_DIRS if (root / d).is_dir()]
    if not dirs:
        dirs = [root]
    all_entries: list[Entry] = []
    for d in dirs:
        for p in sorted(d.rglob("*.md")):
            if SKIP_DIRS & set(p.relative_to(root).parts):
                continue
            all_entries.append(parse_entry(p, root))

    index: dict[str, Entry] = {}
    findings: list[Finding] = []
    for e in all_entries:
        if e.parse_error or not e.id:
            continue
        if e.id in index:
            findings.append(Finding("CA105", "error", e.rel,
                                    f"id `{e.id}` 重复：{index[e.id].rel} 与 {e.rel}"
                                    "（后者不入索引，其引用不被检查）"))
        else:
            index[e.id] = e
    return all_entries, index, findings


def run(root: Path, dup_threshold: float, impact_ids: list[str]):
    all_entries, index, findings = collect(root)

    for e in all_entries:
        check_structure(e, findings)
        check_content(e, findings)
    check_refs(index, findings)
    check_chain(index, findings)
    check_duplicates(index, dup_threshold, findings)

    reports = impact_report(index, impact_ids) if impact_ids else []
    return all_entries, index, findings, reports


def main() -> int:
    ap = argparse.ArgumentParser(description=f"canonlint — WGP 协议参考实现 v{PROTOCOL_VERSION}")
    ap.add_argument("root", type=Path, help="世界仓库根目录")
    ap.add_argument("--strict", action="store_true", help="警告也算失败（pre-commit 用）")
    ap.add_argument("--dup-threshold", type=float, default=0.85)
    ap.add_argument("--json", action="store_true", help="机器可读输出（§6.5 schema）")
    ap.add_argument("--impact", nargs="*", default=[], metavar="ID",
                    help="CA504：输出指定条目的下游影响闭包")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2

    all_entries, index, findings, reports = run(root, args.dup_threshold, args.impact)

    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order.get(f.level, 3), f.rule, f.entry))
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    n_entries = sum(1 for e in all_entries if not e.parse_error)

    if args.json:
        print(json.dumps({
            "protocol_version": PROTOCOL_VERSION,
            "entries": n_entries,
            "findings": [{"rule": f.rule, "level": f.level, "entry": f.entry,
                          "message": f.message} for f in findings],
            "reports": reports,
        }, ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f)
        for r in reports:
            print(f"[CA504] report  {r['subject']}: 下游待复核 → {r['downstream'] or '(无下游)'}")
        print(f"\n{n_entries} 个条目 | {len(errors)} 错误 | {len(warnings)} 警告")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
