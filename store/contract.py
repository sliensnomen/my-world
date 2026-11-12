"""世界契约的加载与体检：**契约是关系词表的唯一真值**。

本模块只回答一个问题：`world.schema.json` 读得到、读得懂吗？

以前这个问题的答案被静默吞掉：读文件失败、JSON 解析失败、键缺失，三种情况都返回空表，
调用点各自退回内置词表，于是工具还能跑出一份「正常」审计，只是用的已经不是现行契约。
这正是 #12 要钉死的缝。

现在的规矩：

* 契约在、且结构合格 → 正常模式；
* 契约**不在** → 默认失败（非零退出），并告诉用户怎么修；
* 契约在、但损坏 / 缺必需键 / 类型不对 → 失败，指出文件与具体位置；
* 只拷了 `store/`（或 `classlint/`）的独立运行 → 必须显式设置 `WGP_COMPAT_VOCAB=1`
  才进入兼容模式；兼容模式用内置词表，并在 CLI / HTTP / 导出里带可见标记。

本模块不认识任何一条关系的**含义**——它只负责把契约读成结构化词表，
再交给 `store/parse.py` 做拼法归一。规则层的判断不在这里。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

SCHEMA_NAME = "world.schema.json"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / SCHEMA_NAME

# 显式兼容模式的开关：只在「契约文件确实不在」时才允许退化。
# 契约在但损坏时**不**接受这个开关——损坏是错误，不是运行环境。
COMPAT_ENV = "WGP_COMPAT_VOCAB"

# 契约缺席（单独拷走 store/ 或 classlint/）时的退化表：本工具读得懂的具名字段名。
# 有了它，「契约读不到」不会让引擎把已知关系名当成未定义字段。
FALLBACK_RELATION_NAMES = ("canon_refs", "conflicts_with", "depends_on", "exchanges_with",
                           "owns", "controls", "extracts", "coerces", "legitimizes",
                           "derives_legitimacy_from", "owes")


class ContractError(RuntimeError):
    """契约缺失或不合格。调用方应把它变成一次明确的非零退出，而不是 traceback。"""


@dataclass(frozen=True)
class Contract:
    """一份读好、验过的契约视图。

    `source == "builtin"` 表示兼容模式（只可能是显式开启的）；此时 `path/version/
    fingerprint` 都是 None，词表为空、调用点退回 `FALLBACK_RELATION_NAMES`。
    """
    source: str                      # "contract" | "builtin"
    degraded: bool
    path: Path | None
    version: str | None
    fingerprint: str | None          # sha256 前 16 位；兼容模式没有
    names: dict[str, tuple[str, ...]]
    deprecations: tuple[tuple[str, str, str], ...]
    strict_vocabulary: dict[str, tuple[str, ...]]
    reason: str = ""                 # 兼容模式的原因（给人看）


def compat_requested() -> bool:
    """兼容模式是否被**显式**开启。没有这个环境变量就绝不退化。"""
    return os.environ.get(COMPAT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _fail_missing(path: Path) -> ContractError:
    return ContractError(
        f"契约缺失：{path} 不存在。\n"
        "契约是关系词表的唯一真值；缺少它时工具不会静默退回内置词表。\n"
        f"若这是独立拷贝（只拷了 store/ 或 classlint/），请显式设置环境变量 "
        f"{COMPAT_ENV}=1 进入兼容模式"
        f"（词表退回内置 {len(FALLBACK_RELATION_NAMES)} 个名字，CLI / HTTP / 导出会带可见标记）。")


def _expect(cond: bool, message: str) -> None:
    if not cond:
        raise ContractError(f"契约结构不合格：{message}")


def _validate_names(raw) -> dict[str, tuple[str, ...]]:
    _expect(isinstance(raw, dict), "x-relation-vocabulary.names 必须是对象")
    _expect(bool(raw), "x-relation-vocabulary.names 不能为空")
    names: dict[str, tuple[str, ...]] = {}
    for name, spec in raw.items():
        _expect(isinstance(name, str) and name, "x-relation-vocabulary.names 的键必须是非空字符串")
        _expect(isinstance(spec, dict), f"x-relation-vocabulary.names.{name} 必须是对象")
        accept = spec.get("accept")
        _expect(isinstance(accept, list) and bool(accept),
                f"x-relation-vocabulary.names.{name}.accept 必须是非空列表")
        _expect(all(isinstance(v, str) and v for v in accept),
                f"x-relation-vocabulary.names.{name}.accept 的每一项必须是非空字符串")
        names[name] = tuple(accept)
    return names


def _validate_deprecations(raw) -> tuple[tuple[str, str, str], ...]:
    _expect(isinstance(raw, list), "x-relation-vocabulary.deprecations 必须是列表")
    out = []
    for i, item in enumerate(raw):
        _expect(isinstance(item, dict), f"x-relation-vocabulary.deprecations[{i}] 必须是对象")
        for key in ("relation", "kind", "becomes"):
            _expect(isinstance(item.get(key), str) and item[key],
                    f"x-relation-vocabulary.deprecations[{i}].{key} 必须是非空字符串")
        out.append((item["relation"], item["kind"], item["becomes"]))
    return tuple(out)


def _validate_strict_vocabulary(raw) -> dict[str, tuple[str, ...]]:
    """`x-strict-vocabulary` 的词表值是字符串列表；`*-exception` 键是说明文字，允许字符串。

    例外键（如 `depends_on.kind-exception`）不参与判定，只给读契约的人解释「为什么
    x- 开头的实验值合法」。以前把整个对象一律当列表会让一份合格契约读不进来。
    """
    _expect(isinstance(raw, dict), "x-strict-vocabulary 必须是对象")
    vocab: dict[str, tuple[str, ...]] = {}
    for key, values in raw.items():
        _expect(isinstance(key, str) and key, "x-strict-vocabulary 的键必须是非空字符串")
        if isinstance(values, str):
            _expect(key.endswith("-exception"),
                    f"x-strict-vocabulary.{key} 是字符串，但它不是 *-exception 说明键")
            continue
        _expect(isinstance(values, list), f"x-strict-vocabulary.{key} 必须是列表或说明字符串")
        _expect(all(isinstance(v, str) and v for v in values),
                f"x-strict-vocabulary.{key} 的每一项必须是非空字符串")
        vocab[key] = tuple(values)
    return vocab


def load_contract(path: Path | None = None) -> Contract:
    """读并体检契约。失败一律抛 `ContractError`，诊断里带文件路径与具体位置。"""
    where = path or SCHEMA_PATH
    if not where.exists():
        if compat_requested():
            return Contract(
                source="builtin", degraded=True, path=None, version=None, fingerprint=None,
                names={}, deprecations=(), strict_vocabulary={},
                reason=f"显式兼容模式（{COMPAT_ENV}=1），契约文件 {where.name} 不存在")
        raise _fail_missing(where)

    try:
        raw_bytes = where.read_bytes()
    except OSError as exc:
        raise ContractError(
            f"契约无法读取：{where}（{exc}）——契约是唯一真值，拒绝静默降级。") from exc

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ContractError(
            f"契约 JSON 损坏：{where}（{exc}）——契约是唯一真值，拒绝静默降级。") from exc

    _expect(isinstance(data, dict), f"{where.name} 顶层必须是对象")
    version = data.get("x-contract-version")
    _expect(isinstance(version, str) and version, "缺少 x-contract-version（契约版本号）")

    vocab = data.get("x-relation-vocabulary")
    _expect(isinstance(vocab, dict), "缺少 x-relation-vocabulary")
    names = _validate_names(vocab.get("names"))
    deprecations = _validate_deprecations(vocab.get("deprecations", []))
    strict = _validate_strict_vocabulary(data.get("x-strict-vocabulary", {}))

    return Contract(
        source="contract", degraded=False, path=where, version=version,
        fingerprint=hashlib.sha256(raw_bytes).hexdigest()[:16],
        names=names, deprecations=deprecations, strict_vocabulary=strict)


_CACHED: Contract | None = None


def get_contract() -> Contract:
    """进程内只读一次。失败时把异常抛给第一次调用者（import 即调用）。"""
    global _CACHED
    if _CACHED is None:
        _CACHED = load_contract()
    return _CACHED


def contract_status() -> dict:
    """给标记用的只读快照：来源、版本、指纹、是否降级。"""
    c = get_contract()
    return {
        "source": c.source,
        "degraded": c.degraded,
        "path": str(c.path) if c.path else None,
        "version": c.version,
        "fingerprint": c.fingerprint,
        "reason": c.reason,
    }
