#!/usr/bin/env python3
"""canonlint — 世界观治理协议（WGP）参考实现。

协议版本见下方 PROTOCOL_VERSION 常量（也是 JSON 输出里的 protocol_version），
本 docstring 不重复数字，避免两处各写一份而对不上。

规则编号即协议：本文件实现 PROTOCOL.md §6.3 全部确定性规则（CA504 见 --impact）。
本文件只放**判定**（什么组合算错）；世界文件的读写契约在 store/（见 store/README.md）。
用法:
  canonlint.py <仓库根> [--strict] [--dup-threshold 0.85] [--json] [--pack econ] [--impact ID...]
  canonlint.py init|new|link|export ...   （人类工作流子命令，见 --help）
退出码: 0=通过(或仅警告) 1=存在错误(--strict 下警告也算) 2=用法/环境错误
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

try:
    # 存储层与扩展包都要用它；这里先做「依赖就绪」检查，真正的使用在 store/model.py
    import yaml  # noqa: F401
except ImportError:  # 环境错误，不是逻辑分支
    print("error: 缺少依赖 pyyaml（pip install pyyaml）", file=sys.stderr)
    sys.exit(2)

import store  # 存储层：模型 / 解析 / 布局 / 写入
from store import Entry, ID_RE  # noqa: F401  （ID_RE 供 CA105 使用）
import ledger  # 事件流水：解析与派生状态（判定原料；判语在本文件的 CA7xx）
from judges.model import Pack
from judges.registry import PackImportError, RegistryError, load_backend, select_packs

PROTOCOL_VERSION = "1.9"   # 1.9：modify 转正；同一 id 内变化，不动窗口与派生状态
CONTRACT_VERSION = "0.7"   # 与 world.schema.json 的 x-contract-version 一致（tests/test_docs.py 钉住）

# ---- 协议常量（改动 = 协议变更，须升版本号）------------------------------

REQUIRED_FIELDS = [
    "id", "title", "type", "author", "date", "status", "load_bearing",
    "canon_refs", "conflicts_with", "ai_assisted",
]
# 顶层字段表归存储层（store/model.py 的 FIELD_TABLE）；这里取它的快照当 CA106 的默认词表，
# 扩展包再用 --pack 往 extra_known 里加自己的字段。
KNOWN_FIELDS = store.FIELD_TABLE

VALID_TYPES = {"location", "faction", "character", "event", "item"}
# 实验类型（1.1）：x-<命名空间>-<名称>，与 kind 的 x- 泄压阀同一套（§5.4）——
# 能存、不判错，CA102 记 info；确定普适了再进 VALID_TYPES（那一步才是收紧词表）。
X_TYPE_RE = re.compile(r"^x-[a-z0-9]+-[a-z0-9-]+$")
VALID_STATUS = {"draft", "trial", "canon", "archived"}
VALID_STANCE = {"official", "heretic", "unknown"}
LAYERS = ["geo", "resource", "production", "economy", "fiscal", "military",
          "political", "ideology"]
LAYER_INDEX = {name: i for i, name in enumerate(LAYERS)}

# `depends_on` 的 kind 词表：这五类就是「哪一类物资」（契约 x-strict-vocabulary.depends_on.kind）。
# 「算不算承重」不再由 kind 决定——那是关系名的事：物质承重是 `depends_on`，
# 名分依据是 `derives_legitimacy_from`（拆分前写作 depends_on + kind: legitimacy）。
KIND_INITIAL_SET = {"resource", "production", "economy", "fiscal", "manpower"}
CA503_LAYERS = {"economy", "fiscal", "military", "political"}  # ideology 豁免
CA505_TRIGGER_LAYERS = {"military", "political"}

WORLD_REF_RE = re.compile(r"^[a-z0-9-]+:")  # world:id 形式，本版不支持（ID_RE 见 store/model.py）

# 附录 A · 承重墙关键词清单
LOAD_BEARING_KEYWORDS = ["经济", "货币", "税收", "贸易", "铸币", "政治",
                         "政权", "法律", "继承", "选帝", "军队", "征兵", "战争赔款"]

MIN_BODY_CHARS = 200        # CA104
MIN_DUP_CHARS = 100         # CA201 最短参与长度

# 扫描目录（ENTRY_DIRS/SKIP_DIRS）与类型目录（TYPE_DIRS）归存储层：store/layout.py

# ---- 数据模型（条目/边/解析错误在 store/model.py，这里只留报告项）--------

@dataclass
class Finding:
    rule: str
    level: str  # error | warning | info
    entry: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.level:7s} {self.entry}: {self.message}"


# 解析（FRONTMATTER_RE / parse_entry）在 store/model.py


# ---- 规则 ----------------------------------------------------------------

def is_valid_date(value) -> bool:
    """`date` 字段的两种合法形态：YAML 原生日期对象，或契约要求的 ISO 字符串。

    契约把 `date` 写成字符串（`^[0-9]{4}-[0-9]{2}-[0-9]{2}$`），而 YAML 会把没加引号的
    `date: 2026-10-15` 直接解成 `datetime.date`。两种都是作者会合理写出来的东西，规则
    就该两种都收下；JSON 入口来的（没有日期类型）必然是字符串。
    """
    if isinstance(value, (date, datetime)):  # YAML 原生日期/时间对象
        return True
    if isinstance(value, str):
        # 契约的 pattern 是 `^\d{4}-\d{2}-\d{2}$`，而 `date.fromisoformat` 从 3.11 起
        # 还收 ISO 基本格式（`20261015`）与周历格式（`2026-W42-6`）——两种都过了 CA103，
        # 而文案写的是「须为 YYYY-MM-DD」。先把形状钉死，再验日期本身是否真实（2 月 30 日）。
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True
    return False


def _valid_successor(e: Entry, index: dict[str, Entry]) -> str | None:
    """`superseded_by` 指向的那个条目 id；值坏掉/指向自己/指向不存在都返回 None。

    以前只判「不是 None」，于是一个 `superseded_by: 42`、或指向自己、或指向不存在的
    承接者，都能让 CA405「降级处置不完整」静默消音，同时 CA402 还会让作者「迁移至
    `42`」——一处坏值，两处误导。
    """
    sb = e.meta.get("superseded_by")
    if not isinstance(sb, str) or not sb or sb == e.id:
        return None
    return sb if sb in index else None


def _has_successor(e: Entry, index: dict[str, Entry]) -> bool:
    """archived 条目是否真有承接者。

    `superseded_by` 字段缺 或 显式为 null，都表示**没有**承接者——契约把 null
    定义为「无承接者」的合法写法（§4.1 / CA101 文案），所以降级级联的两条规则
    （CA402 报在引用方、CA405 报在目标方）必须把 null 与字段缺当成同一件事，
    否则填一个 null 就能把 CA405 关掉（评审 F4）。
    """
    return _valid_successor(e, index) is not None


def check_structure(e: Entry, findings: list[Finding],
                    known_fields: frozenset | set = KNOWN_FIELDS) -> None:
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
    if "type" in e.meta and (not isinstance(e.meta["type"], str)
                             or e.meta["type"] not in VALID_TYPES):
        if isinstance(e.meta["type"], str) and X_TYPE_RE.match(e.meta["type"]):
            findings.append(Finding("CA102", "info", rel,
                                    f"type={e.meta['type']!r} 为实验类型（x- 前缀），已计入案例收集"))
        else:
            findings.append(Finding("CA102", "error", rel,
                                    f"type={e.meta['type']!r} 非法，须为 {sorted(VALID_TYPES)}"
                                    f"（实验类型须形如 `x-<命名空间>-<名称>`，如 `x-mine-weather`）"))
    if "status" in e.meta and (not isinstance(e.meta["status"], str)
                               or e.meta["status"] not in VALID_STATUS):
        findings.append(Finding("CA102", "error", rel,
                                f"status={e.meta['status']!r} 非法，须为 {sorted(VALID_STATUS)}"))
    if "layer" in e.meta and (not isinstance(e.meta["layer"], str)
                              or e.meta["layer"] not in LAYER_INDEX):
        findings.append(Finding("CA102", "error", rel,
                                f"layer={e.meta['layer']!r} 非法，须为 {LAYERS}"))
    if "date" in e.meta and not is_valid_date(e.meta["date"]):
        findings.append(Finding("CA103", "error", rel,
                                f"date={e.meta['date']!r} 不是合法日期（须为 YYYY-MM-DD）"))
    if "id" in e.meta:
        if not isinstance(e.meta["id"], str) or not ID_RE.match(e.meta["id"]):
            findings.append(Finding("CA105", "error", rel,
                                    f"id={e.meta['id']!r} 非法（仅允许小写字母/数字/连字符）"))
    for k in e.meta:
        if k in known_fields or str(k).startswith("x-"):
            continue
        # 契约 `x-relation-vocabulary.value.accept` 登记的历史拼法必须认下：
        # `canon-ref:` / `depends-on:` 是契约声明合法的写法，判成「未定义字段」是硬错误。
        # 认下的范围严格等于登记表（`canonical_relation_name`），编辑距离 ≤1 的机械变体
        # （`canon_ref` 单数之类）仍然报错——字段名拼错该被抓住。
        if isinstance(k, str) and store.canonical_relation_name(k) in known_fields:
            continue
        findings.append(Finding("CA106", "error", rel,
                                f"未定义字段 `{k}`（扩展字段须 x- 前缀）"))
    # CA112: YAML 重复键。PyYAML 对重复键是 last-wins 且一声不响，写在前面的那一条
    # 等于没写；`depends_on` 写两遍会让一条边在解析结果里彻底消失，而所有规则都看不到。
    for k in e.duplicate_keys:
        findings.append(Finding("CA112", "error", rel,
                                f"字段 `{k}` 在 frontmatter 里出现了不止一次：YAML 只保留最后一个，"
                                f"写在前面的那条等于没写"))
    # CA109: bool 字段类型
    for bf in ("load_bearing", "ai_assisted"):
        if bf in e.meta and not isinstance(e.meta[bf], bool):
            findings.append(Finding("CA109", "error", rel,
                                    f"{bf}={e.meta[bf]!r} 必须是 bool（true/false）"))
    # CA107/CA108: depends_on schema 与 kind；CA109: conflicts/canon_refs 类型
    for err in e.deps[1]:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    # 边的判定一律读**统一视图**：旧具名字段与规范形 `relations` 一视同仁
    for dep in e.edges_of("depends_on"):
        kind = dep.attrs.get("kind")
        if kind is None or kind in KIND_INITIAL_SET:
            continue  # 规范形不强制 kind；旧写法的缺 kind 已由上面的 schema 错误报掉
        if isinstance(kind, str) and kind.startswith("x-"):
            findings.append(Finding("CA108", "info", rel,
                                    f"kind={kind!r} 为实验值，已计入案例收集"))
        else:
            findings.append(Finding("CA108", "error", rel,
                                    f"kind={kind!r} 不在初始集且未带 x- 前缀"))
    for err in e.conflicts[1]:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    for ref in e.edges_of("conflicts_with"):
        stance = ref.attrs.get("stance")
        if stance is not None and (not isinstance(stance, str)
                                   or stance not in VALID_STANCE):
            findings.append(Finding("CA102", "error", rel,
                                    f"stance={stance!r} 非法，须为 {sorted(VALID_STANCE)}"))
    for err in e.canon_ref_ids[1]:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    # 六个后接线的具名字段（owns/controls/extracts/coerces/legitimizes/owes）：
    # 形状问题必须报出来，否则「接线」等于把它们从 CA106 硬错误降级成静默
    for err in e.named_relation_errors:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    # 规范形 relations：这里只报**形状**；关系名是否成立由判定器决定（PR#3）
    for err in e.relation_errors:
        findings.append(Finding(err.rule, "error", rel, err.msg))
    # CA110: 关系名拼写近失守卫（契约 x-relation-vocabulary.spelling-guard）。
    # 自由档允许自定义关系名（PROTOCOL §254 fail-open），所以这里只对「与已知规范名
    # 编辑距离 ≤1」的名字发 warning——正是这条缝让 depends-on 这种拼写同时漏判又误判。
    for raw_name in e.raw_relation_names:
        near = store.nearest_relation_name(raw_name)
        if near is not None:
            findings.append(Finding("CA110", "warning", rel,
                                    f"关系名 `{raw_name}` 与规范名 `{near}` 只差一个字符，"
                                    f"疑似拼写错误，已按 `{near}` 判定；"
                                    f"确是新关系请改用其它名字或加 `x-` 前缀"))
    # CA111: 拆分前的写法（depends_on + kind=legitimacy）。存储层已经把它归一成关系名
    # derives_legitimacy_from 并按那条关系判定，这里只提示作者把写法改过来——废弃如果
    # 完全静默，就等于留了一条只有工具知道的新关系名。
    for err in e.relation_migrations:
        findings.append(Finding(err.rule, "warning", rel, err.msg))


def check_content(e: Entry, findings: list[Finding]) -> None:
    """CA104 篇幅、CA301 关键词触发、CA302 承重墙义务。"""
    if e.parse_error:
        return
    rel = e.rel
    if e.status in ("trial", "canon") and len(e.clean_body) < MIN_BODY_CHARS:
        findings.append(Finding("CA104", "warning", rel,
                                f"正文 {len(e.clean_body)} 字，{e.status} 档建议 ≥{MIN_BODY_CHARS} 字"))
    if e.meta.get("load_bearing") is True:
        missing = []
        if "layer" not in e.meta:
            missing.append("layer")
        # 「声明」而不是「有边」：两种写法的同一句话必须判成同一个结果（§5.3）。
        if not e.declares_dependencies and not e.edges_of("depends_on"):
            missing.append("depends_on")
        if missing:
            findings.append(Finding("CA302", "error", rel,
                                    f"load_bearing: true 但缺 {missing}"))
    else:
        # CA301 只对**已定档**的条目发（trial/canon）：draft 还没到做决定的时候，而
        # `--strict` 会让任何 warning 变成失败——以前一条把「政治/经济」写在正文里的
        # 草稿在 --strict 下无法提交，审计器等于替作者做了决定（评审 F8，与 CA104
        # 只对 trial/canon 报篇幅是同一个口径）。
        hay = str(e.meta.get("title", "")) + e.clean_body
        hits = [kw for kw in LOAD_BEARING_KEYWORDS if kw in hay]
        if hits and e.status in ("trial", "canon"):
            findings.append(Finding("CA301", "warning", rel,
                                    f"命中承重墙关键词 {hits}，但未声明 load_bearing——请考虑声明"))


def check_events(e: Entry, findings: list[Finding]) -> None:
    """CA7xx 的单条目部分 + 事件字段形状（CA109）与 event_kind 词表（CA102）。

    「给了 event_kind 才算完整事件」（D2）；when 与 event_kind 只给一个
    是半截事件（CA706）。x- 实验 event_kind 与 type/kind 同一套泄压阀：
    记 info、不判腿、不进派生，但 CA701 时序照算（时序不看 kind）。
    """
    if e.parse_error:
        return
    rel = e.rel
    if not ledger.is_event_card(e):
        # 事件字段是流水的一部分，流水只收 `type: event` 的卡。以前只看有没有
        # event_kind：一张 location 卡带上事件字段就被当成完整事件参与派生状态，
        # 却永远不在 entries/events/ 里。类型是作者声明的，判定器不替它改。
        if "event_kind" in e.meta or any(leg in e.meta for leg in ledger.LEG_FIELDS):
            findings.append(Finding(
                "CA109", "error", rel,
                f"事件字段只能出现在 `type: event` 的卡上（本卡 type={e.meta.get('type')!r}）；"
                f"要记账请建 event 卡，史料卡上不要放 event_kind/腿"))
        return
    v = ledger.event_view(e)
    for msg in v.shape_errors:
        findings.append(Finding("CA109", "error", rel, msg))
    has_when = "when" in e.meta
    has_kind = "event_kind" in e.meta
    if has_kind:
        if not isinstance(v.kind, str):
            findings.append(Finding("CA102", "error", rel,
                                    f"event_kind={v.kind!r} 必须是字符串"))
        elif v.kind not in ledger.EVENT_KINDS:
            if ledger.is_experimental_kind(v.kind):
                findings.append(Finding("CA102", "info", rel,
                                        f"event_kind={v.kind!r} 为实验值（x- 前缀），已计入案例收集"))
            else:
                findings.append(Finding(
                    "CA102", "error", rel,
                    f"event_kind={v.kind!r} 非法，须为 {sorted(ledger.EVENT_KINDS)}"
                    f"（实验值须形如 `x-<命名空间>-<名称>`）"))
    if has_when != has_kind:
        findings.append(Finding("CA706", "warning", rel,
                                "半截事件：`when` 与 `event_kind` 只给了一个"
                                "（两个都给才进流水判定，都不给就是普通史料卡）"))
    if not ledger.is_complete_event(v):
        return
    for leg in ledger.REQUIRED_LEGS[v.kind]:
        if leg not in v.declared:
            findings.append(Finding(
                "CA702", "error", rel,
                f"{v.kind} 事件缺腿 `{leg}`（必填：{list(ledger.REQUIRED_LEGS[v.kind])}）——账不平"))
        elif leg in v.legs and not v.legs[leg] and leg not in v.bad_legs:
            findings.append(Finding("CA702", "error", rel,
                                    f"{v.kind} 事件的 `{leg}` 是空列表——账不平"))
        # 腿声明过但形状写坏（含「是列表但元素全坏」）：CA109 已报，这里不双报


# 已经有专属引用检查的关系（各自带状态语义：canon_refs 的 CA402/CA405、depends_on 的
# CA404 等）。剩下的关系没有专属规则，但**目标存在性**是结构问题，不属于哪一层的理论：
# 从前这六种字段一条都不查，于是 `owns: [幽灵]` 在 canonlint 里完全隐形。
# 只取**规范名**：`RELATION_TYPE_NAMES` 的键包含每一种可接受拼法，按它遍历会把同一条
# 边按 canon-ref / canon-refs / canonrefs 报三遍。
# 有专属引用检查的关系（各自带状态语义，见下）。
_RELATIONS_WITH_OWN_REFERENCE_RULES = frozenset({
    "canon_refs", "conflicts_with", "depends_on", "exchanges_with",
    "derives_legitimacy_from"})


def check_refs(entries: list[Entry], index: dict[str, Entry],
               findings: list[Finding]) -> None:
    """CA4xx 引用与状态机。无传递违规原则：只判直接边。

    逐条检查的是**全部**条目，不只是进了索引的那些：id 重复时被遮蔽的那一份
    过去完全不查引用（CA105 的文案还把这当成既定事实写出来了），于是「世界上
    摆着一条指向不存在条目的边」可以一直没人报——它只是没进索引，不是没写错。
    索引只用来查目标是否存在，被遮蔽的条目自己的出边一样要判。
    """
    for e in entries:
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

        for ref_id in [r.target for r in e.edges_of("canon_refs")]:
            target = check_target(ref_id, "canon_refs")
            if target is None or target.status == "canon":
                continue
            if target.status == "archived" and not _has_successor(target, index):
                continue  # 没有承接者，由 CA405 在 archived 条目侧报告，避免双报
            if target.status == "archived":
                findings.append(Finding("CA402", "error", rel,
                                        f"canon_refs 目标 `{ref_id}` 已 archived，"
                                        f"请迁移至其承接条目 `{_valid_successor(target, index)}`"))
            else:
                findings.append(Finding("CA402", "error", rel,
                                        f"canon_refs 目标 `{ref_id}` 状态为 {target.status}，须为 canon"))
        for dep in e.edges_of("depends_on"):
            target = check_target(dep.target, "depends_on")
            if target is not None and e.status == "canon" and target.status != "canon":
                findings.append(Finding("CA404", "error", rel,
                                        f"canon 条目的 depends_on 目标 `{dep.target}` 状态为 {target.status}，须为 canon"))
        for ref in e.edges_of("conflicts_with"):
            check_target(ref.target, "conflicts_with")
        # 交换只是流通关系，目标存在性要查（悬空引用是坏的），但**不**查状态：
        # 交换对象降级不必处置，交换本身也不构成承重（见契约 x-relation-vocabulary）。
        for ref in e.edges_of("exchanges_with"):
            check_target(ref.target, "exchanges_with")
        # 名分依据只查存在性，且**不**查状态：依据来源是草稿/降级不构成违规，
        # 「名分断了」与「物资断了」不是一回事（CA402/CA404 都针对生存依赖）。
        for ref in e.edges_of("derives_legitimacy_from"):
            check_target(ref.target, "derives_legitimacy_from")

        # 其余关系，**包括作者自定义的关系名**（owns / controls / extracts / coerces /
        # legitimizes / owes，以及 `relations: [{type: mentor-of}]` 这种自由档）：
        # 语义住在 classlint 那一层，但「引用指向不存在的 id」是结构问题，不该因为规则
        # 归属而看不见。以前只列了六个具名字段，于是 `type: mentor-of` 指向幽灵时
        # classlint 报 CL105、canonlint 一声不响——同一份数据两个引擎两种结论，而且这处
        # 差异没在任何地方登记过。
        for edge in e.relations:
            if edge.type in _RELATIONS_WITH_OWN_REFERENCE_RULES:
                continue
            check_target(edge.target, edge.type)

        # superseded_by 的目标存在性（CA401）
        sb = e.meta.get("superseded_by")
        if sb is not None:
            if not isinstance(sb, str):
                findings.append(Finding("CA109", "error", rel,
                                        f"superseded_by={sb!r} 必须是 id 字符串或 null"))
            elif sb == e.id:
                findings.append(Finding("CA109", "error", rel,
                                        "superseded_by 不能指向自己（承接者须是另一条目）"))
            else:
                check_target(sb, "superseded_by")

        # 事件腿（by/to/object/from，协议 1.2/1.4）的悬空引用与关系边同罪：
        # 「指向不存在的 id 是结构问题」不因字段归属而改变（v1.1 修订第 16 条的同一原则）
        for leg in ledger.LEG_FIELDS:
            for ref_id in ledger.event_view(e).legs.get(leg, []):
                check_target(ref_id, leg)

        # custody_of / member_of 断言（协议 1.4/1.6）：形状（CA109）与存在性（CA401）。
        # 它们是断言不是事件腿，所以不进 ledger.LEG_FIELDS，但检查口径与腿相同
        for assertion in ("custody_of", "member_of"):
            raw_assertion = e.meta.get(assertion)
            if raw_assertion is None:
                continue
            if not isinstance(raw_assertion, list):
                findings.append(Finding("CA109", "error", rel,
                                        f"{assertion} 必须是 id 列表"))
                continue
            for i, item in enumerate(raw_assertion):
                if not isinstance(item, str):
                    findings.append(Finding(
                        "CA109", "error", rel,
                        f"{assertion}[{i}] 必须是 id 字符串，得到 {item!r}"))
                else:
                    check_target(item, assertion)

    # CA405: archived、被 canon_refs 引用、且**没有承接者**（字段缺 或 显式 null）
    # 报在目标侧，定位到处置责任人。`superseded_by: null` 是 CA101 允许的写法，
    # 意思是「没有承接者」——那正是降级不完整的情形，不能因为填了 null 就放行。
    for e in index.values():
        if e.parse_error or e.status != "archived":
            continue
        referenced = any(
            ref_id == e.id
            for o in index.values() if not o.parse_error
            for ref_id in (r.target for r in o.edges_of("canon_refs"))
        )
        if referenced and not _has_successor(e, index):
            sb = e.meta.get("superseded_by")
            if "superseded_by" not in e.meta:
                why = "未填 `superseded_by`"
            elif sb is None:
                why = "声称没有承接者（`superseded_by: null`）"
            elif not isinstance(sb, str) or not sb:
                why = f"`superseded_by={sb!r}` 不是合法的承接者"
            elif sb == e.id:
                why = "`superseded_by` 指向自己（承接者不能是本条目）"
            else:
                why = f"`superseded_by` 指向不存在的条目 `{sb}`"
            why += "（没有可迁移的承接条目）"
            findings.append(Finding("CA405", "error", e.rel,
                                    f"archived 条目仍被 canon_refs 引用，但{why}——降级处置不完整"))

    # CA403: 无回指且本方简式才报（对方是否有 stance 与本关系无关，见 §4.2 第 3 条）
    for e in index.values():
        if e.parse_error:
            continue
        for ref in e.edges_of("conflicts_with"):
            target = index.get(ref.target)
            if target is None or target.parse_error:
                continue
            if any(r.target == e.id for r in target.edges_of("conflicts_with")):
                continue  # 有回指即对称，不究形式
            if ref.attrs.get("stance") is not None:
                continue  # 本方对象式 = 有意不对称
            findings.append(Finding("CA403", "warning", e.rel,
                                    f"与 `{ref.target}` 的矛盾标注不对称（对方未回指）"))


def check_chain(index: dict[str, Entry], findings: list[Finding]) -> None:
    """CA5xx 政治经济学链条。判据只看**关系名**与 kind 是不是已知物资类别。

    拆分之后 `depends_on` 就是物质承重，所以「算不算承重」不再挂在 kind 副标签上：
    `kind` 只回答「依赖的是哪一类物资」。x- 实验值仍豁免（契约把它定义成泄压阀，
    能存、只记 info、不进链条判定）。
    """
    graph: dict[str, list[str]] = {}  # 仅物质族边（CA502 用）
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        deps = e.edges_of("depends_on")
        graph[e.id] = [d.target for d in deps
                       if d.target in index and d.attrs.get("kind") in KIND_INITIAL_SET]

        if e.meta.get("load_bearing") is not True:
            continue
        layer = e.meta.get("layer")
        if layer not in LAYER_INDEX:
            continue  # CA102/CA302 已报
        for d in deps:
            if d.attrs.get("kind") not in KIND_INITIAL_SET:
                continue  # 未知/实验类别不参与方向检查（§5.5）
            target = index.get(d.target)
            if target is None:
                continue  # CA401 已报
            tl = target.meta.get("layer")
            if tl in LAYER_INDEX and LAYER_INDEX[tl] > LAYER_INDEX[layer]:
                findings.append(Finding("CA501", "error", e.rel,
                                        f"depends_on 目标 `{d.target}` 层级 {tl}（序号 {LAYER_INDEX[tl]}）"
                                        f"高于本条目 {layer}（序号 {LAYER_INDEX[layer]}）"))
        # CA503: economy/fiscal/military/political 层须有物质族 critical 依赖；ideology 豁免
        if layer in CA503_LAYERS and not any(
                d.attrs.get("critical") and d.attrs.get("kind") in KIND_INITIAL_SET
                for d in deps):
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

    # CA502: 环检测（仅物质族子图；三色 DFS 迭代实现；同一环只报一次）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in graph}
    reported_cycles: set[frozenset] = set()

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
                    key = frozenset(cycle)
                    if key not in reported_cycles:
                        reported_cycles.add(key)
                        findings.append(Finding("CA502", "error", index[node].rel,
                                                f"depends_on 存在环（物质族）: {' → '.join(cycle)}"))
                elif color.get(nxt) == WHITE:
                    color[nxt] = GRAY
                    stack.append((nxt, path + [nxt]))  # path 逐层复制，深图 O(n²) 空间，世界观量级可接受
                    advanced = True
                    break
            if not advanced:
                stack.pop()
                color[node] = BLACK


def check_ledger(index: dict[str, Entry], findings: list[Finding]) -> None:
    """CA7xx 的跨条目部分：时序与账平。缺 when_sort 一律 fail-open（D2）。

    CA703/CA704 的持有者口径见 ledger.derive_state：owns 断言是无时间的
    「有持有者」证据（D3），transfer/grant 推出新的最终持有者；断言与最终
    持有者打架是 CA704（error），客体从无来源是 CA703（warning）。
    """
    events = ledger.ordered_events(index)

    def is_event(v: ledger.EventView) -> bool:
        return ledger.is_complete_event(v) or ledger.is_experimental_kind(v.kind)

    # CA701: 事件 A depends_on 事件 B，两边都有 when_sort 时要求 B ≤ A
    for e in index.values():
        if not ledger.is_event_card(e):
            continue
        va = ledger.event_view(e)
        if va.when_sort is None or not is_event(va):
            continue
        for d in e.edges_of("depends_on"):
            b = index.get(d.target)
            if b is None or not ledger.is_event_card(b):
                continue  # 悬空由 CA401 报
            vb = ledger.event_view(b)
            if vb.when_sort is None or not is_event(vb):
                continue
            if vb.when_sort > va.when_sort:
                findings.append(Finding(
                    "CA701", "warning", e.rel,
                    f"时序倒流：本事件 when_sort={va.when_sort:g}，"
                    f"depends_on 的事件 `{b.id}` when_sort={vb.when_sort:g}（要求 ≤ 本事件）"))

    # CA703: transfer/grant 的客体在它之前没有任何持有者
    # （owns 断言是无时间的「有持有者」证据；更早的 transfer/grant 也算）
    held: set[str] = set()
    for e in index.values():
        if not e.parse_error:
            held.update(r.target for r in e.edges_of("owns"))
    for e, v in events:
        if v.kind in ("transfer", "grant"):
            for obj in v.legs.get("object", []):
                if obj not in held:
                    findings.append(Finding(
                        "CA703", "warning", e.rel,
                        f"无源之财：{v.kind} 的客体 `{obj}` 在它之前没有任何持有者"
                        f"（既无 owns 断言，也无更早的 transfer/grant 指向它）"))
            held.update(v.legs.get("object", []))

    # CA704: 手写 owns 断言与流水推出的最终持有者打架
    # （只对有流水的客体比对；无流水的客体，断言即全部历史。
    #  多值受方 = 归属未定序：最终那笔的 to 列表里任一受方的断言都放行，
    #  更早一笔的受方已被转手，不放行）
    states = ledger.derive_state(index)
    # 每个客体的「最终一刻」：when_sort 最大的那批 transfer/grant。同刻多笔的先后
    # 没有定义（ordered_events 的 id 序只用于输出稳定），所以不许拿 id 序挑一个赢家：
    # 受方集合不同 = 归属未定序，报 warning；相同才继续对账。
    final_acts: dict[str, tuple[float, list[tuple[Entry, list[str]]]]] = {}
    for e, v in events:
        if v.kind not in ("transfer", "grant"):
            continue
        if not v.legs.get("to"):
            continue
        for obj in v.legs.get("object", []):
            per_obj = final_acts.setdefault(obj, (v.when_sort, []))
            if v.when_sort > per_obj[0]:
                final_acts[obj] = (v.when_sort, [(e, v.legs["to"])])
            elif v.when_sort == per_obj[0]:
                per_obj[1].append((e, v.legs["to"]))
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for r in e.edges_of("owns"):
            if r.target not in final_acts:
                continue
            when, acts = final_acts[r.target]
            recipient_sets = {frozenset(to) for _ev, to in acts}
            if len(recipient_sets) > 1:
                peers = "、".join(sorted(ev.id or ev.rel for ev, _to in acts))
                findings.append(Finding(
                    "CA704", "warning", e.rel,
                    f"归属未定序：`{r.target}` 在 when_sort={when:g} 同时有 "
                    f"{len(acts)} 笔转让（{peers}），受方集合不同——先按 id 序挑一个"
                    f"只是展示，断言无法对账；请拆开 when_sort 或让受方一致"))
                continue
            recipients = set().union(*recipient_sets)
            st = states.get(r.target)
            if (st is not None and st.holder is not None and st.holder != e.id
                    and e.id not in recipients):
                findings.append(Finding(
                    "CA704", "error", e.rel,
                    f"结论与流水打架：卡上断言 owns `{r.target}`，但流水推出的"
                    f"最终持有者是 `{st.holder}`（来自 `{st.holder_source}`）"))

    # CA705: 事件的 by 里有人在更早的事件里已 death（同刻不算，严格 <）
    deaths: dict[str, float] = {}
    for e, v in events:
        if v.kind == "death":
            for obj in v.legs.get("object", []):
                deaths[obj] = min(deaths.get(obj, v.when_sort), v.when_sort)
    for e, v in events:
        # 以前这里跳过所有 death 事件：一笔「死人主持的死亡」永远不报。
        # 协议没有这条豁免——death 的 by 里若有人严格更早死亡，同样是 CA705。
        for actor in v.legs.get("by", []):
            if actor in deaths and deaths[actor] < v.when_sort:
                findings.append(Finding(
                    "CA705", "warning", e.rel,
                    f"死人做活事：`{actor}` 在 when_sort={deaths[actor]:g} 的事件里"
                    f"已 death，却在更晚的本事件（when_sort={v.when_sort:g}）的 by 里"))

    # CA707: 同一客体被多张卡断言 owns——断言互搏。derive_state 按 id 序取第一个
    # 只是「报告需要一个答案」，不是裁决；互搏本身要报出来（与有无流水无关）。
    claims: dict[str, list[Entry]] = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for r in e.edges_of("owns"):
            claims.setdefault(r.target, []).append(e)
    for obj in sorted(claims):
        holders = claims[obj]
        if len(holders) < 2:
            continue
        first = min(h.id for h in holders)  # derive_state 按 id 序取的那个
        for h in sorted(holders, key=lambda x: x.rel):
            if h.id == first:
                continue
            findings.append(Finding(
                "CA707", "warning", h.rel,
                f"owns 断言互搏：`{obj}` 同时被 `{first}` 与本卡断言持有"
                f"（派生状态按 id 序取 `{first}`；请统一到一张卡上断言，或用流水表达流转）"))

    # CA708: 客体的事件必须落在它自己的存在窗口里（create/birth 开窗，
    # death/destroy 关窗，transform 关旧窗开新窗；端点事件自身即边界，跳过）。
    # modify 是普通客体事件，只受窗口约束，不改变窗口。
    # 缺 when_sort 的边界不产生窗口、缺 when_sort 的事件不进流水——两头都 fail-open。
    windows = ledger.existence_windows(index)
    for e, v in events:
        if v.kind in ("birth", "create", "death", "destroy", "transform"):
            continue  # 端点事件自身豁免
        for obj in v.legs.get("object", []):
            start, end = windows.get(obj, (None, None))
            if start is not None and v.when_sort < start:
                findings.append(Finding(
                    "CA708", "warning", e.rel,
                    f"不存在的东西在动弹：`{obj}` 在 when_sort={start:g} 才被造出来/出生/转化出来，"
                    f"本事件却在 when_sort={v.when_sort:g} 就拿它当客体"))
            elif end is not None and v.when_sort > end:
                findings.append(Finding(
                    "CA708", "warning", e.rel,
                    f"不存在的东西在动弹：`{obj}` 在 when_sort={end:g} 已死亡/被毁/被转化，"
                    f"本事件却在更晚的 when_sort={v.when_sort:g} 拿它当客体"))

    # CA709: 手写 custody_of 断言与 custody 流水推出的最终保管人打架
    # （CA704 的保管版；多值受方同口径：最终那笔 to 列表里任一受方放行）
    custody_final: dict[str, tuple[float, list[tuple[Entry, list[str]]]]] = {}
    for e, v in events:
        if v.kind != "custody" or not v.legs.get("to"):
            continue
        for obj in v.legs.get("object", []):
            per_obj = custody_final.setdefault(obj, (v.when_sort, []))
            if v.when_sort > per_obj[0]:
                custody_final[obj] = (v.when_sort, [(e, v.legs["to"])])
            elif v.when_sort == per_obj[0]:
                per_obj[1].append((e, v.legs["to"]))
    # CA710 的原料也一并收集：custody_of 断言按客体归拢
    custody_claims: dict[str, list[Entry]] = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for obj in ledger.custody_assertions(e):
            custody_claims.setdefault(obj, []).append(e)
            if obj not in custody_final:
                continue
            when, acts = custody_final[obj]
            recipient_sets = {frozenset(to) for _ev, to in acts}
            if len(recipient_sets) > 1:
                peers = "、".join(sorted(ev.id or ev.rel for ev, _to in acts))
                findings.append(Finding(
                    "CA709", "warning", e.rel,
                    f"归属未定序：`{obj}` 在 when_sort={when:g} 同时有 "
                    f"{len(acts)} 笔 custody（{peers}），保管人集合不同——"
                    f"断言无法对账；请拆开 when_sort 或让保管人一致"))
                continue
            recipients = set().union(*recipient_sets)
            st = states.get(obj)
            if (st is not None and st.custodian is not None
                    and st.custodian != e.id and e.id not in recipients):
                findings.append(Finding(
                    "CA709", "error", e.rel,
                    f"结论与流水打架：卡上断言 custody_of `{obj}`，但流水推出的"
                    f"最终保管人是 `{st.custodian}`（custody 不改变持有者，只改保管）"))

    # CA710: custody_of 断言互搏（CA707 的保管版）
    for obj in sorted(custody_claims):
        keepers = custody_claims[obj]
        if len(keepers) < 2:
            continue
        first = min(k.id for k in keepers)
        for k in sorted(keepers, key=lambda x: x.rel):
            if k.id == first:
                continue
            findings.append(Finding(
                "CA710", "warning", k.rel,
                f"custody_of 断言互搏：`{obj}` 同时被 `{first}` 与本卡断言保管"
                f"（派生状态按 id 序取 `{first}`；请统一到一张卡上断言，或用 custody 流水表达移交）"))

    # CA712: member_of 断言与流水打架——断言在，但该人对那个组织的最后一个
    # 流水动作是 leave。组织没有流水时断言即全部历史，不判（D3 同款豁免）。
    # member_of 多值合法：一个人在多个组织不算互搏，所以只有对账没有互搏规则。
    # 同刻 join 与 leave 并存时没有「最后一个动作」：以前按 id 序挑一个，改个文件名
    # 就能让结论翻转。这里 fail-open（不报），与 CA705 的「同刻不算」同一口径。
    membership_acts: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for _e, v in events:
        if v.kind not in ("join", "leave"):
            continue
        orgs = v.legs.get("to" if v.kind == "join" else "from", [])
        for person in v.legs.get("by", []):
            for org in orgs:
                membership_acts.setdefault((person, org), []).append(
                    (v.when_sort, v.kind))
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for org in ledger.member_of_assertions(e):
            acts = membership_acts.get((e.id, org))
            if not acts:
                continue
            last_when = max(when for when, _kind in acts)
            last_kinds = {kind for when, kind in acts if when == last_when}
            if len(last_kinds) > 1:
                continue  # 同刻 join/leave 并存：未定序，fail-open
            if "leave" in last_kinds:
                findings.append(Finding(
                    "CA712", "error", e.rel,
                    f"结论与流水打架：卡上断言 member_of `{org}`，但流水里本条目"
                    f"对该组织的最后一个动作是 leave——要么补一笔 join，要么把断言撤了"))

    # CA711: 轨迹断裂——move 的 from 对不上链上的当前位置。
    # 只走存在窗口内的 move（窗外归 CA708，姊妹规则不双报）。
    # 「未定」对称哲学：上一笔 to 多值 → 位置未知 → 跳过校验，直到单值 to 重新锚定；
    # from 多值 = 没定，当前位置在列表里就放行；缺 from / 缺 when_sort 不查。
    UNDETERMINED = object()  # 位置「未定」：与 None（还没出现过）区分——未定跳过校验
    position: dict[str, tuple[object, float]] = {}  # 位置 + 它出自哪个 when_sort
    for e, v in events:
        if v.kind != "move":
            continue
        for obj in v.legs.get("object", []):
            start, end = windows.get(obj, (None, None))
            in_window = not ((start is not None and v.when_sort < start)
                             or (end is not None and v.when_sort > end))
            to = v.legs.get("to", [])
            frm = v.legs.get("from", [])
            cur = position.get(obj)
            if (in_window and frm and cur is not None
                    and cur[0] is not UNDETERMINED
                    and cur[1] < v.when_sort  # 同刻的 move 彼此不构成「上一笔」
                    and cur[0] not in frm):
                findings.append(Finding(
                    "CA711", "warning", e.rel,
                    f"轨迹断裂：`{obj}` 上一笔账落在 `{cur[0]}`（when_sort={cur[1]:g}），"
                    f"本笔却声称从 `{frm[0]}` 出发（不写 from 就不查；同刻 move 不排序）"))
            # 同刻多笔 move 只在结论一致时保留位置；不一致 = 位置未定。
            if to:
                loc = to[0] if len(to) == 1 else UNDETERMINED
                if cur is not None and cur[1] == v.when_sort:
                    if cur[0] is UNDETERMINED or loc is UNDETERMINED or cur[0] != loc:
                        loc = UNDETERMINED
                position[obj] = (loc, v.when_sort)
            # to 缺失/为空：CA702 已报，位置不动


def _supersede_pairs(index: dict[str, Entry]) -> set[frozenset[str]]:
    """`superseded_by` 声明的降级承接对（无序）。

    承接条目按定义要**接着**旧条目的内容写，正文天然高度相似——那正是降级处置的样子，
    不是重复。评审 F9：这条豁免以前不存在，于是每一对正常的 archived→承接者都会在
    `--strict` 下把世界判红。
    """
    pairs = set()
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        sb = e.meta.get("superseded_by")
        if isinstance(sb, str) and sb and sb != e.id:
            pairs.add(frozenset((e.id, sb)))
    return pairs


def check_duplicates(index: dict[str, Entry], threshold: float,
                     findings: list[Finding]) -> None:
    """CA201: 正文相似度（§6.6 预处理，双方 ≥100 字符才参与）。

    降级承接对（`superseded_by` 声明的两方）豁免：相似是**要求的**，不是疑似重复。
    """
    exempt = _supersede_pairs(index)
    items = [(e.id, e.rel, e.clean_body) for e in index.values() if not e.parse_error]
    items = [it for it in items if len(it[2]) >= MIN_DUP_CHARS]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            id_i, rel_i, text_i = items[i]
            id_j, rel_j, text_j = items[j]
            if id_i and id_j and frozenset((id_i, id_j)) in exempt:
                continue
            ratio = difflib.SequenceMatcher(None, text_i, text_j).ratio()
            if ratio >= threshold:
                findings.append(Finding(
                    "CA201", "warning", f"{rel_i} ↔ {rel_j}",
                    f"正文相似度 {ratio:.0%} ≥ {threshold:.0%}，疑似重复"))


def impact_report(index: dict[str, Entry], subjects: list[str]) -> list[dict]:
    """CA504: 输出 subject 的 depends_on 反向传递闭包，按链条序号降序。"""
    dependents: dict[str, list[str]] = {}
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        for d in e.edges_of("depends_on"):
            dependents.setdefault(d.target, []).append(e.id)

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
        # 主体不上榜：`--impact x` 问的是「谁依赖 x」，x 自己不是自己的下游。
        # 只有 x 落在环里时闭包才会把它带回来，而环由 CA502 单独报（评审 F6）。
        order = [x for x in order if x != subj]

        def layer_key(eid: str) -> int:
            e = index.get(eid)
            l = e.meta.get("layer") if e else None
            return LAYER_INDEX.get(l, -1)

        order.sort(key=layer_key, reverse=True)
        reports.append({"rule": "CA504", "subject": subj, "downstream": order})
    return reports


def ledger_report(root: Path, packs=()) -> int:
    """`canonlint ledger <世界>`：打印派生状态与没算平的地方。

    与 --impact 同一条纪律：report 级输出，永不进退出码、永不写盘。
    「没算平的」复用所选后端的判据（CA703/CA704/CA705），
    报告与门禁不许各说一套。
    """
    all_entries, index, _issues = store.collect(root)
    events = ledger.ordered_events(index)
    states = ledger.derive_state(index)
    findings: list[Finding] = []
    core_ca = next((p for p in packs
                    if isinstance(p, Pack) and p.name == "core-ca"), None)
    if core_ca is not None:
        from judges.ca.pack import apply_core_ca_ledger

        apply_core_ca_ledger(
            core_ca, index,
            lambda rule, level, rel, msg: findings.append(Finding(rule, level, rel, msg)))
    else:
        check_ledger(index, findings)
    n_entries = sum(1 for e in all_entries if not e.parse_error)
    print(f"{n_entries} 个条目 | {len(events)} 笔完整事件（有 when_sort 才进流水）")
    print("\n== 派生状态（期初断言 + 流水）==")
    if not states:
        print("(没有可派生的客体：没有 owns 断言，也没有完整事件)")
    for obj in sorted(states):
        st = states[obj]
        src = f"（来自 `{st.holder_source}`）" if st.holder_source else ""
        print(f"{obj}: 持有者 {st.holder or '（无）'}{src}"
              f" | 保管 {st.custodian or '-'} | 位置 {st.location or '-'}")
    unbalanced = [f for f in findings if f.rule in ("CA703", "CA704", "CA705")]
    print("\n== 没算平的 ==")
    if not unbalanced:
        print("(账平)")
    for f in unbalanced:
        print(f"[{f.rule}] {f.entry}: {f.message}")
    membership = ledger.derive_membership(index)
    print("\n== 组织归属（join/leave 流水）==")
    if not membership:
        print("(没有 join/leave 流水)")
    for person in sorted(membership):
        acts = membership[person]
        joined = sorted(o for o, a in acts.items() if a == "join")
        left = sorted(o for o, a in acts.items() if a == "leave")
        line = f"{person}: " + ("在 " + "、".join(joined) if joined else "无在册组织")
        if left:
            line += "（已离开 " + "、".join(left) + "）"
        print(line)
    return 0


# ---- 导出（前端 / 其他出口用的数据集）------------------------------------

EXPORT_EXCERPT_CHARS = 200  # 与 CA104 的 MIN_BODY_CHARS 同一个量级：够看开头，不当正文用
LEVEL_ORDER = {"error": 0, "warning": 1, "info": 2}


def _entry_export(e: Entry) -> dict:
    """一个条目的导出形态：选定字段 + 统一视图的边。前端不该自己解析 Markdown。

    事件流水字段（协议 1.2 起）与断言字段（1.4/1.6）原样透出——前端要渲染
    「谁拿着什么」，B6 的触发条件已经达成。
    """
    meta = e.meta
    d = meta.get("date")
    return {
        "id": e.id,
        "path": e.rel,
        "title": meta.get("title"),
        "type": meta.get("type"),
        "status": meta.get("status"),
        "layer": meta.get("layer"),
        "author": meta.get("author"),
        "date": d.isoformat() if isinstance(d, date) else d,
        "load_bearing": meta.get("load_bearing"),
        "ai_assisted": meta.get("ai_assisted"),
        "superseded_by": meta.get("superseded_by"),
        "when": meta.get("when"),
        "when_sort": meta.get("when_sort"),
        "event_kind": meta.get("event_kind"),
        "by": meta.get("by"),
        "to": meta.get("to"),
        "object": meta.get("object"),
        "from": meta.get("from"),
        "result": meta.get("result"),
        "owns": [r.target for r in e.edges_of("owns")] or None,
        "custody_of": meta.get("custody_of"),
        "member_of": meta.get("member_of"),
        "parse_error": e.parse_error,
        "body_chars": len((e.body or "").strip()),
        "body_excerpt": (e.body or "").strip()[:EXPORT_EXCERPT_CHARS],
        "x_fields": {k: v for k, v in meta.items() if str(k).startswith("x-")},
        "relations": [{"source": e.id, "type": r.type, "target": r.target, **r.attrs}
                      for r in e.relations],
    }


def _counts(values) -> dict:
    """vocabularies 计数：只数字符串值。写坏的值（如 `type: [faction]`）不该拖垮导出——
    它自己已经由 CA102 报出来了，条目里也照原样留着。"""
    out: dict = {}
    for v in values:
        if not isinstance(v, str):
            continue
        out[v] = out.get(v, 0) + 1
    return {k: out[k] for k in sorted(out)}


def _json_safe(value):
    r"""把文件名里解不出来的字节变成可输出的文本。

    文件名不是 UTF-8 时，Python 用 surrogateescape 存（`\udcff`），这种字符**编码不成
    UTF-8**：`json.dumps(..., ensure_ascii=False).encode("utf-8")` 直接抛
    UnicodeEncodeError，接口回 0 字节、CLI export 打 traceback。它还是世界里的一个文件，
    不能凭空消失——所以把它还原成原始字节再转义（`\udcff` → `\xff`），路径从此可打印、
    可 grep，并且一眼能看出「这名字本身有问题」。
    """
    if isinstance(value, str):
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    if isinstance(value, dict):
        return {_json_safe(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def build_export(all_entries: list[Entry], findings: list[Finding],
                 reports: list[dict], root: Path,
                 index: dict[str, Entry] | None = None) -> dict:
    """把已算好的审计结果整理成自描述数据集。确定性：无时间戳、无绝对路径。"""
    entries = sorted((_entry_export(e) for e in all_entries), key=lambda d: d["path"])
    known = {e.id for e in all_entries if e.id}
    relations = [edge for d in entries for edge in d["relations"]]
    dangling = []
    for edge in relations:
        if edge["target"] in known:
            continue
        dangling.append({
            "source": edge["source"], "type": edge["type"], "target": edge["target"],
            "reason": "world-ref" if WORLD_REF_RE.match(edge["target"]) else "missing-id",
        })
    assets = []
    assets_dir = root / "assets"
    if assets_dir.is_dir():
        for p in sorted(assets_dir.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                assets.append({"path": str(p.relative_to(root)), "bytes": p.stat().st_size})
    parsed = [d for d in entries if not d["parse_error"]]
    dep_kinds = [a.get("kind") for d in parsed for a in d["relations"]
                 if a["type"] == "depends_on" and a.get("kind") is not None]
    stances = [a.get("stance") for d in parsed for a in d["relations"]
               if a.get("stance") is not None]
    levels = _counts(f.level for f in findings)
    # 派生状态透出（B6）：期初断言 + 流水 → 谁拿着什么、谁在哪个组织
    states_raw = ledger.derive_state(index) if index is not None else {}
    membership_raw = ledger.derive_membership(index) if index is not None else {}
    return _json_safe({
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "counts": {
            "entries": len(entries),
            "unparsed": len(entries) - len(parsed),
            "relations": len(relations),
            "dangling": len(dangling),
            "assets": len(assets),
            "findings": len(findings),
            "errors": levels.get("error", 0),
            "warnings": levels.get("warning", 0),
            "infos": levels.get("info", 0),
        },
        "vocabularies": {
            "types": _counts(d["type"] for d in parsed if d["type"] is not None),
            "statuses": _counts(d["status"] for d in parsed if d["status"] is not None),
            "layers": _counts(d["layer"] for d in parsed if d["layer"] is not None),
            "kinds": _counts(dep_kinds),
            "stances": _counts(stances),
            "relation_types": _counts(a["type"] for d in parsed for a in d["relations"]),
            "fields": _counts(k for e in all_entries if not e.parse_error for k in e.meta),
        },
        "ledger": {
            "states": {obj: {"holder": st.holder, "holder_source": st.holder_source,
                             "custodian": st.custodian, "location": st.location}
                       for obj, st in sorted(states_raw.items())},
            "membership": {p: dict(sorted(acts.items()))
                           for p, acts in sorted(membership_raw.items())},
        },
        "entries": entries,
        "relations": relations,
        "dangling": dangling,
        "assets": assets,
        "findings": [{"rule": f.rule, "level": f.level, "entry": f.entry,
                      "message": f.message} for f in findings],
        "reports": reports,
    })


def export_world(root: Path, packs=(), impact=(), extra_known=frozenset(),
                 dup_threshold: float = 0.85) -> dict:
    """世界目录 → 导出数据集。CLI 的 `export` 与 serve.py 共用这一条路径。

    导出不是判定：这里绝不改退出码，也不吞掉 findings——它们原样进数据集。
    """
    all_entries, index, findings, reports = run(root, dup_threshold, list(impact),
                                                extra_known=extra_known, packs=packs)
    findings.sort(key=lambda f: (LEVEL_ORDER.get(f.level, 3), f.rule, f.entry))
    return build_export(all_entries, findings, reports, root, index=index)


def _load_packs(names: list[str]):
    """按统一后端选择加载判定包，返回 (Pack 或旧模块列表, 扩展字段集)。"""
    if load_backend() == "registry":
        try:
            registry = select_packs("canonlint", ["core-ca", *names])
        except PackImportError as e:
            if (e.engine, e.name) == ("canonlint", "econ"):
                return None, None
            raise
        return list(registry.selected), registry.ca106_fields

    packs: list = []
    extra_known: frozenset[str] = frozenset()
    for name in names:
        if name != "econ":
            continue
        try:
            import econ
        except ImportError:
            return None, None
        extra_known |= econ.KNOWN_FIELDS  # 扩展包字段注入，先于 CA106 检查
        packs.append(econ)
    return packs, extra_known


def _apply_registry_pack(pack: Pack, index: dict, findings: list[Finding]) -> None:
    for e in index.values():
        if e.parse_error:
            continue
        for rule in sorted(pack.rules, key=lambda r: r.order):
            if rule.scope != "entry" or rule.entry_domain != "index_parseable":
                raise RegistryError(f"canonlint 当前不能调度规则 {rule.id}")

            def add(level, msg, rule=rule, rel=e.rel):
                level = rule.default_level if level is None else level
                if level not in rule.levels:
                    raise RegistryError(f"规则 {rule.id} 发出未登记级别: {level!r}")
                findings.append(Finding(rule.id, level, rel, msg))

            rule.check(e.meta, e.rel, add)


def _apply_packs(packs, index: dict, findings: list[Finding]) -> None:
    for pack in packs:
        if isinstance(pack, Pack):
            _apply_registry_pack(pack, index, findings)
            continue
        for e in index.values():
            if not e.parse_error:
                pack.check_entry(
                    e.meta, e.rel,
                    lambda rule, level, msg, rel=e.rel:
                        findings.append(Finding(rule, level, rel, msg)))


def _apply_core_ca(pack: Pack, all_entries, index, issues,
                   known_fields, findings: list[Finding], dup_threshold: float) -> None:
    from judges.ca.pack import apply_core_ca

    apply_core_ca(
        pack, all_entries, index, issues, known_fields,
        lambda rule, level, rel, msg: findings.append(Finding(rule, level, rel, msg)),
        dup_threshold=dup_threshold)


def _apply_core_ca_reports(pack: Pack, index: dict, impact_ids: list[str]):
    from judges.ca.pack import apply_core_ca_reports

    return apply_core_ca_reports(pack, index, impact_ids)


# ---- 主流程 --------------------------------------------------------------


def run(root: Path, dup_threshold: float, impact_ids: list[str],
        extra_known: frozenset[str] = frozenset(), packs=()):
    """完整判定：结构 → 内容 → 引用 → 链 → 事件 → 流水 → 重复 → 扩展包。

    `packs` 必须与读路径（export_world / CLI）同口径：以前只有 CLI 和导出应用
    扩展包，serve 的写后审计不应用——同一个世界「读时合法、写时非法」。
    """
    all_entries, index, issues = store.collect(root)
    known = KNOWN_FIELDS | extra_known
    core_ca = next((p for p in packs
                    if isinstance(p, Pack) and p.name == "core-ca"), None)
    findings: list[Finding] = []

    if core_ca is not None:
        _apply_core_ca(core_ca, all_entries, index, issues, known, findings, dup_threshold)
    else:
        # 存储层报的形状问题（今天只有 id 重复 CA114）升级成报告项
        findings.extend(Finding(i.rule, "error", i.rel, i.message) for i in issues)
        for e in all_entries:
            check_structure(e, findings, known)
            check_content(e, findings)
        check_refs(all_entries, index, findings)
        check_chain(index, findings)
        for e in all_entries:
            check_events(e, findings)
        check_ledger(index, findings)
        check_duplicates(index, dup_threshold, findings)
    extension_packs = [p for p in packs
                       if not (isinstance(p, Pack) and p.name == "core-ca")]
    _apply_packs(extension_packs, index, findings)

    if not impact_ids:
        reports = []
    elif core_ca is not None:
        reports = _apply_core_ca_reports(core_ca, index, impact_ids)
    else:
        reports = impact_report(index, impact_ids)
    return all_entries, index, findings, reports


def _event_fields_from_args(a) -> dict | None:
    """把 new/event 子命令的事件与断言标志收成 fields 字典（None 表示没带任何字段）。

    argparse 的 `--from` 住在 dest=from_，这里换回字段名；`--when-sort` 同理。
    """
    if not hasattr(a, "when"):
        return None
    fields: dict = {}
    for attr, name in (("when", "when"), ("when_sort", "when_sort"),
                       ("event_kind", "event_kind"), ("from_", "from"),
                       ("by", "by"), ("to", "to"), ("object", "object"),
                       ("result", "result"), ("owns", "owns"),
                       ("custody_of", "custody_of"), ("member_of", "member_of")):
        value = getattr(a, attr, None)
        if value is not None:
            fields[name] = value
    return fields or None


def _event_kind(value: str) -> str:
    """argparse 的 event_kind 校验：词表值或 x- 实验值（CA102 的实验泄压阀）。

    以前 `choices=EVENT_KINDS` 把实验值挡在官方入口外：协议允许记 x- 并降 info，
    但 CLI/HTTP 都说「非法」，作者只能手写卡。
    """
    if value in ledger.EVENT_KINDS or ledger.is_experimental_kind(value):
        return value
    raise argparse.ArgumentTypeError(
        f"event_kind={value!r} 非法，须为 {sorted(ledger.EVENT_KINDS)} "
        f"或 x- 开头的实验值")


def main() -> int:
    # 人类工作流子命令：init / new / link / export / ledger / event；其余按审计（check）处理
    if len(sys.argv) > 1 and sys.argv[1] in ("init", "new", "link", "export", "ledger", "event"):
        cmd = sys.argv[1]
        sp = argparse.ArgumentParser(prog=f"canonlint {cmd}")
        sp.add_argument("--root", type=Path, default=Path("."),
                        help="世界仓库根目录（默认当前目录）")
        if cmd == "init":
            sp.add_argument("root_pos", type=Path, nargs="?", default=None,
                            help="世界仓库目录（位置参数，等价 --root）")
        if cmd == "new":
            sp.add_argument("type", nargs="?", choices=sorted(VALID_TYPES))
            sp.add_argument("title", nargs="?")
            sp.add_argument("--id")
            sp.add_argument("--author")
            sp.add_argument("--load-bearing", action="store_true")
            sp.add_argument("--layer", choices=LAYERS)
        if cmd == "event":
            # 一行记账：canonlint event transfer --by a --to b --object c
            sp.add_argument("kind", type=_event_kind)
            sp.add_argument("title", nargs="?")
            sp.add_argument("--id")
            sp.add_argument("--author")
        if cmd in ("new", "event"):
            # 事件流水与断言字段（白名单 = store 的 EVENT_FIELDS；store 端再挡一道）
            sp.add_argument("--when")
            sp.add_argument("--when-sort", type=float)
            sp.add_argument("--event-kind", type=_event_kind)
            sp.add_argument("--from", dest="from_", nargs="+")
            for leg in ("by", "to", "object", "result", "owns",
                        "custody-of", "member-of"):
                sp.add_argument(f"--{leg}", nargs="+")
        if cmd == "link":
            sp.add_argument("src")
            sp.add_argument("dst")
            sp.add_argument("--kind", required=True)
            sp.add_argument("--critical", action="store_true")
        if cmd == "export":
            sp.add_argument("root_pos", type=Path, nargs="?", default=None,
                            help="世界仓库目录（位置参数，等价 --root）")
            sp.add_argument("--out", type=Path, default=None,
                            help="写到文件（默认打到 stdout）")
            sp.add_argument("--impact", nargs="*", default=[], metavar="ID",
                            help="附带指定条目的下游影响闭包（CA504）")
            sp.add_argument("--pack", action="append", default=[], choices=["econ"],
                            help="启用协议扩展包（econ = WGP-econ 数值系统，CA6xx）")
        if cmd == "ledger":
            sp.add_argument("root_pos", type=Path, nargs="?", default=None,
                            help="世界仓库目录（位置参数，等价 --root）")
        a = sp.parse_args(sys.argv[2:])
        if cmd == "init":
            # exe 从这里传进去：store 里算不出「用户敲的 canonlint 在哪」
            exe = shutil.which("canonlint") or str(Path(__file__).resolve())
            return store.cmd_init(a.root_pos or a.root, exe=exe)
        if cmd == "new":
            # 层级词表是理论，归判定器；存储层只收下它
            fields = _event_fields_from_args(a)
            return store.cmd_new(a.root, a.type, a.title, a.id,
                                 author=a.author, load_bearing=a.load_bearing,
                                 layer=a.layer, layer_choices=LAYERS, fields=fields)
        if cmd == "event":
            fields = _event_fields_from_args(a) or {}
            fields["event_kind"] = a.kind
            title = a.title or f"{a.kind} 事件"
            return store.cmd_new(a.root, "event", title, a.id,
                                 author=a.author, layer_choices=LAYERS,
                                 fields=fields)
        if cmd == "link":
            return store.cmd_link(a.root, a.src, a.dst, a.kind, a.critical,
                                  kind_choices=KIND_INITIAL_SET)
        if cmd == "export":
            root = (a.root_pos or a.root).resolve()
            if not root.is_dir():
                print(f"error: {root} 不是目录", file=sys.stderr)
                return 2
            try:
                packs, extra_known = _load_packs(a.pack)
            except RegistryError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            if packs is None:
                print("error: 扩展包 econ 不可用（econ.py 应与 canonlint.py 同目录）",
                      file=sys.stderr)
                return 2
            data = export_world(root, packs, a.impact, extra_known)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            if a.out:
                a.out.parent.mkdir(parents=True, exist_ok=True)
                a.out.write_text(text + "\n", encoding="utf-8")
                print(f"导出 {data['counts']['entries']} 个条目 / "
                      f"{data['counts']['relations']} 条边 → {a.out}")
            else:
                print(text)
            return 0  # 导出不是判定：要门禁请用 canonlint <root> --strict
        if cmd == "ledger":
            root = (a.root_pos or a.root).resolve()
            if not root.is_dir():
                print(f"error: {root} 不是目录", file=sys.stderr)
                return 2
            try:
                packs, _extra_known = _load_packs([])
                return ledger_report(root, packs)
            except RegistryError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2

    ap = argparse.ArgumentParser(
        description=f"canonlint — WGP 协议参考实现 v{PROTOCOL_VERSION}",
        epilog=(
            "人类工作流子命令（不走审计路径）：\n"
            "  canonlint init [目录]                          新建世界仓库\n"
            "                                                 （entries/ + 模板 + pre-commit 钩子）\n"
            "  canonlint new <type> <标题> [--id ID]          新建一个草稿条目\n"
            "  canonlint link <源id> <目标id> --kind K        添加一条依赖边\n"
            "  canonlint export [目录] [--out 文件]           导出数据集（前端/其他出口用，不判定）\n"
            "  canonlint ledger [目录]                          事件流水：派生状态与没算平的（只读报告）\n"
            "  canonlint event <kind> --by X --to Y ...         一行记一笔流水（事件卡，等价 new event）\n"
            "  canonlint <仓库根> --strict                    审计（error 与 warning 都拦）\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="世界仓库根目录")
    ap.add_argument("--strict", action="store_true", help="警告也算失败（pre-commit 用）")
    ap.add_argument("--dup-threshold", type=float, default=0.85)
    ap.add_argument("--json", action="store_true", help="机器可读输出（§6.5 schema）")
    ap.add_argument("--impact", nargs="*", default=[], metavar="ID",
                    help="CA504：输出指定条目的下游影响闭包")
    ap.add_argument("--pack", action="append", default=[], choices=["econ"],
                    help="启用协议扩展包（econ = WGP-econ 数值系统，CA6xx）")
    args = ap.parse_args()

    # 相似度阈值必须落在 (0, 1]：>1 会让 CA201 永远不触发（静默关掉一条规则），
    # ≤0 会让任意两条都算重复。越界是用法错误（退出码 2），不是「安静地换个行为」。
    if not 0.0 < args.dup_threshold <= 1.0:
        print(f"error: --dup-threshold 必须在 (0, 1] 内，收到 {args.dup_threshold}",
              file=sys.stderr)
        return 2

    try:
        packs, extra_known = _load_packs(args.pack)
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if packs is None:
        print("error: 扩展包 econ 不可用（econ.py 应与 canonlint.py 同目录）",
              file=sys.stderr)
        return 2

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2
    if not store.looks_like_world(root):
        print(f"error: {root} 不像一个世界仓库：没有 entries/，目录里也没有一篇"
              "带 frontmatter 的条目卡（指错目录了？）", file=sys.stderr)
        return 2

    all_entries, index, findings, reports = run(root, args.dup_threshold, args.impact,
                                                extra_known=extra_known, packs=packs)

    findings.sort(key=lambda f: (LEVEL_ORDER.get(f.level, 3), f.rule, f.entry))
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
