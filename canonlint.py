#!/usr/bin/env python3
"""canonlint — 世界观治理协议（WGP）参考实现。

协议版本见下方 PROTOCOL_VERSION 常量（也是 JSON 输出里的 protocol_version），
本 docstring 不重复数字，避免两处各写一份而对不上。

规则编号即协议：PROTOCOL.md §6.3 的确定性规则由 judges/ 的 core-ca Pack 实现
（CA504 见 --impact）；本文件是引擎驱动：CLI、导出、ledger 报告与写后审计。
世界文件的读写契约在 store/（见 store/README.md）。
用法:
  canonlint.py <仓库根> [--strict] [--dup-threshold 0.85] [--json] [--pack econ] [--impact ID...]
  canonlint.py init|new|link|export ...   （人类工作流子命令，见 --help）
退出码: 0=通过(或仅警告) 1=存在错误(--strict 下警告也算) 2=用法/环境错误
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
    # 存储层与扩展包都要用它；这里先做「依赖就绪」检查，真正的使用在 store/model.py
    import yaml  # noqa: F401
except ImportError:  # 环境错误，不是逻辑分支
    print("error: 缺少依赖 pyyaml（pip install pyyaml）", file=sys.stderr)
    sys.exit(2)

from store.contract import ContractError  # 契约缺失/损坏时用它做一次人话退出（#12）

try:
    import store  # 存储层：模型 / 解析 / 布局 / 写入
    from store import Entry  # noqa: F401  （导出与报告的类型标注）
except ContractError as exc:
    print(f"error: {exc}", file=sys.stderr)
    sys.exit(2)
import ledger  # 事件流水：解析与派生状态（判定原料；判语在 judges/ 的 CA7xx）
from judges.model import Pack
from judges.registry import PackImportError, RegistryError, select_packs
from judges.ca.vocab import (  # 协议词表唯一定义点；本文件全量转发（tests/test_store.py 钉住）
    CA503_LAYERS, CA505_TRIGGER_LAYERS, KIND_INITIAL_SET, KNOWN_FIELDS,
    LAYER_INDEX, LAYERS, LOAD_BEARING_KEYWORDS, MIN_BODY_CHARS, MIN_DUP_CHARS,
    MIN_EXACT_DUP_CHARS,
    REQUIRED_FIELDS, VALID_STANCE, VALID_STATUS, VALID_TYPES, WORLD_REF_RE,
    X_TYPE_RE, _RELATIONS_WITH_OWN_REFERENCE_RULES)

PROTOCOL_VERSION = "1.27"  # 1.10：同刻未定序与断言解耦；1.11：from 腿语义 + certainty 导出；1.12：CA713 转让起点断裂；1.13：CA705 覆盖 destroy、CA708 查四腿、CA201 豁免限 archived；1.14：未定序不再吞掉断言对账；1.15：CA703 交出者来源、CA501 锚点 layer、CA708 端点施动者、CA712 类型门禁（#38）；1.16：CA703 的 create/birth 豁免只限第一笔转手（#42），端点事件死后 by 不再双报（#44）；1.17：显式 null 关系字段报 CA109（#43）、CA111 认契约历史拼法（#45）、CA103 拒收 datetime（#46）；1.18：#40 F1/F2/F3——规范形注解键按关系名校验、非事件卡 when/when_sort 报 CA109、坏 YAML 不制造假悬空引用；1.19：#49 CA504 闭包从全部条目建图、#50 扫描判据统一（扁平散文不误报、条目子目录不跳过）；1.20：#38 端点类 CA714（重复/顺序端点事件）；1.21：#38 元数据/自指/CA505 泄压阀；1.22：#38 状态门禁 CA715（canon 引用非 canon）；1.23：#38 x- 实验类别成环也报 CA502；1.24：#38 CA301 补军事/财政同义词、CA704/709 文案改用客体 id；1.25：#38 新增 CA716（when 数字与 when_sort 反向）；1.26：#38 CA201 精确短重复不设长度豁免；1.27：#38 事件腿类型表 CA717（by/join/move/birth/destroy 等）
CONTRACT_VERSION = "0.8"   # 与 world.schema.json 的 x-contract-version 一致（tests/test_docs.py 钉住）

# ---- 协议词表与阈值：唯一定义点在 judges/ca/vocab.py，文件头 import 转发 --------------
# 词表名不许在本文件再绑定（tests/test_store.py 的「只有一份定义」锁）；
# 改动词表 = 协议变更，须升版本号并同步 PROTOCOL.md §6.3。

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



CERTAINTY_LABEL = {
    "known": "流水结论",
    "unknown": "仅断言兜底，无流水佐证",
    "ambiguous": "未定（同刻未定序或断言互搏）",
}


def ledger_report(root: Path, packs=()) -> int:
    """`canonlint ledger <世界>`：打印派生状态与账本族的告警。

    与 --impact 同一条纪律：report 级输出、永不进退出码、永不写盘。
    「账本族的告警」与审计/导出共用同一份 findings 与同一个 `cert_` 三态——
    报告与门禁不许各说一套（issue #48：三出口三套说法）。
    """
    all_entries, index, issues = store.collect(root)
    events = ledger.ordered_events(index)
    states = ledger.derive_state(index)
    findings: list[Finding] = []
    core_ca = next((p for p in packs
                    if isinstance(p, Pack) and p.name == "core-ca"), None)
    if core_ca is None:
        raise RegistryError("core-ca Pack 缺失：ledger 报告无法审计")
    # 报告与门禁同口径：跑完整核心审计，再挑账本族（CA7xx），
    # 这样 CA706/707/711/712/713 不会被「只跑流水子集」吞掉（issue #48）。
    from judges.ca.pack import apply_core_ca

    apply_core_ca(
        core_ca, all_entries, index, issues, KNOWN_FIELDS,
        lambda rule, level, rel, msg: findings.append(Finding(rule, level, rel, msg)),
        dup_threshold=0.85)
    n_entries = sum(1 for e in all_entries if not e.parse_error)
    print(f"{n_entries} 个条目 | {len(events)} 笔完整事件（有 when_sort 才进流水）")
    print("\n== 派生状态（结论断言 + 流水）==")
    if not states:
        print("(没有可派生的客体：没有 owns 断言，也没有完整事件)")
    def _mark(value: str | None, certainty: str) -> str:
        if value is None:
            return "-"
        label = CERTAINTY_LABEL.get(certainty, certainty)
        if certainty == "ambiguous":
            return f"未定（显示值 {value}，仅 id 序，不代表结论）"
        if certainty == "unknown":
            return f"{value}（猜的）【{label}】"
        return f"{value}【{label}】"

    for obj in sorted(states):
        st = states[obj]
        src = f"（来自 `{st.holder_source}`）" if st.holder_source else ""
        holder = _mark(st.holder, st.certainty)
        if st.holder and src and st.certainty != "ambiguous":
            holder = holder.replace("【", f"{src}【", 1)
        print(f"{obj}: 持有者 {holder}"
              f" | 保管 {_mark(st.custodian, st.certainty)}"
              f" | 位置 {_mark(st.location, st.certainty)}")
    ledger_findings = [f for f in findings if f.rule.startswith("CA7")]
    print("\n== 账本族告警（没算平的 + 参考口径）==")
    if not ledger_findings:
        print("(账平)")
    for f in ledger_findings:
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
    # 派生状态透出（B6）：结论断言 + 流水 → 谁拿着什么、谁在哪个组织
    states_raw = ledger.derive_state(index) if index is not None else {}
    membership_raw = ledger.derive_membership(index) if index is not None else {}
    result = _json_safe({
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
                             "custodian": st.custodian, "location": st.location,
                             "certainty": st.certainty}
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
    status = store.contract_status()
    if status["degraded"]:
        # 导出报告也必须能自证「这份数据不是按完整契约审出来的」（#12）。
        result["contract"] = {
            "source": status["source"],
            "degraded": True,
            "version": status["version"],
            "fingerprint": status["fingerprint"],
            "reason": status["reason"],
        }
    return result


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
    """加载判定包（core-ca + 显式扩展包），返回 (Pack 列表, 扩展字段集)。"""
    try:
        registry = select_packs("canonlint", ["core-ca", *names])
    except PackImportError as e:
        if (e.engine, e.name) == ("canonlint", "econ"):
            return None, None
        raise
    return list(registry.selected), registry.ca106_fields


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
        _apply_registry_pack(pack, index, findings)


def _apply_core_ca(pack: Pack, all_entries, index, issues,
                   known_fields, findings: list[Finding], dup_threshold: float) -> None:
    from judges.ca.pack import apply_core_ca

    apply_core_ca(
        pack, all_entries, index, issues, known_fields,
        lambda rule, level, rel, msg: findings.append(Finding(rule, level, rel, msg)),
        dup_threshold=dup_threshold)


def _apply_core_ca_reports(pack: Pack, index: dict, impact_ids: list[str],
                           entries: list | None = None):
    from judges.ca.pack import apply_core_ca_reports

    return apply_core_ca_reports(pack, index, impact_ids, entries=entries)


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
    if core_ca is None and not packs:
        # 空 packs 是「默认审计」的旧契约：调用方（export_world 默认值、嵌入方、
        # 测试）传空就等于要 core-ca。显式给了 packs 却漏掉 core-ca 才是调用方 bug。
        reg = select_packs("canonlint", ["core-ca"])
        core_ca = reg.selected[0]
        packs = list(reg.selected)
        known = KNOWN_FIELDS | reg.ca106_fields | extra_known
    if core_ca is None:
        raise RegistryError("core-ca Pack 缺失：canonlint 无法审计")
    findings: list[Finding] = []
    _apply_core_ca(core_ca, all_entries, index, issues, known, findings, dup_threshold)
    extension_packs = [p for p in packs
                       if not (isinstance(p, Pack) and p.name == "core-ca")]
    _apply_packs(extension_packs, index, findings)

    if not impact_ids:
        reports = []
    else:
        reports = _apply_core_ca_reports(core_ca, index, impact_ids, all_entries)
    return all_entries, index, findings, reports


def _post_write_problems(root: Path, path: Path, packs) -> list[str]:
    """写后审计：新卡本身（按相对路径）的 error 级发现。"""
    rel = path.relative_to(root).as_posix()
    try:
        _, _, findings, _ = run(root, 0.85, [], packs=packs)
    except Exception as e:  # 自检失败也必须拒绝落盘，不能静默
        return [f"写后自检失败：{e}"]
    return [f"{f.rule} {f.level} {f.entry}: {f.message}"
            for f in findings if f.level == "error" and f.entry == rel]


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


def contract_notice() -> str | None:
    """兼容模式（契约缺失 + 显式 WGP_COMPAT_VOCAB）时给用户看的醒目提示；正常模式 None。"""
    status = store.contract_status()
    if not status["degraded"]:
        return None
    return ("⚠ 兼容模式：世界契约 world.schema.json 未读到，关系词表已退回内置词表"
            f"（source={status['source']}，version={status['version']}，"
            f"fingerprint={status['fingerprint']}）。本次审计不是完整契约审计。")


def main() -> int:
    notice = contract_notice()
    if notice:
        print(notice, file=sys.stderr)
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
            packs, _ = _load_packs([])
            return store.cmd_new(
                a.root, a.type, a.title, a.id,
                author=a.author, load_bearing=a.load_bearing,
                layer=a.layer, layer_choices=LAYERS, fields=fields,
                verify=lambda path: _post_write_problems(a.root, path, packs))
        if cmd == "event":
            fields = _event_fields_from_args(a) or {}
            fields["event_kind"] = a.kind
            title = a.title or f"{a.kind} 事件"
            packs, _ = _load_packs([])
            return store.cmd_new(
                a.root, "event", title, a.id,
                author=a.author, layer_choices=LAYERS,
                fields=fields,
                verify=lambda path: _post_write_problems(a.root, path, packs))
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
