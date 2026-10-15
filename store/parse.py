"""共享解析核心：**文件里写了什么 → 内存里是什么**。

canonlint（CA 规则）与 classlint（CL/PE 规则）读的是同一批卡，所以读卡的代码只应该有
一份。这个模块就是那一份：id 语法、frontmatter 切分、关系名词表（契约
`world.schema.json` 是唯一真值）、规范名归一化、拼写近失守卫，以及一条边长什么样。

它不认识理论，也不认识任何一个引擎的局部习惯——条目目录（`entries/` 还是 `codex/`）、
必填字段、错误码前缀、关系形状政策，全部留在各引擎自己的 profile 里。共用本模块是为了
守住 CONTRIBUTING §7 的「同一份数据必须得到同一份判定」：同一张卡不该因为两个引擎各抄了
一份读法，在一边是一张卡、在另一边变成另一张。

历史：本模块的内容原先分抄在 `store/model.py` 与 `classlint/classlint.py` 两份里，
同一段「读契约词表」的逻辑存在两个实现（拼法归一化的缝里曾经漏报过引用）。现已合并。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# ---- id 语法与文件形状 ------------------------------------------------------

ID_RE = re.compile(r"^[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

# ---- 关系名归一化（契约是唯一真值）------------------------------------------
# 本层不认识任何关系名的**含义**；它只负责「同一个关系的所有历史拼法 → 一个规范名」。
# 真值表在契约 world.schema.json 的 x-relation-vocabulary；本模块读它，不自己再写一份。

SCHEMA_NAME = "world.schema.json"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / SCHEMA_NAME

# 规范形边允许的键（契约 $defs/relation；`x-` 前缀的键永远是允许的）
CANONICAL_RELATION_ITEMS = ("type", "target", "kind", "critical", "stance", "note", "what")

# 契约缺席（单独拷走 store/ 或 classlint/）时的退化表：本工具读得懂的具名字段名。
# 有了它，「契约读不到」不会让引擎把已知关系名当成未定义字段。
FALLBACK_RELATION_NAMES = ("canon_refs", "conflicts_with", "depends_on", "exchanges_with",
                           "owns", "controls", "extracts", "coerces", "legitimizes",
                           "derives_legitimacy_from", "owes")


def _read_schema() -> dict:
    """读契约 JSON；读不到就返回空表（各调用点各自退化，不在这里静默吞掉一切）。"""
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def contract_relation_names() -> dict[str, tuple[str, ...]]:
    """读契约的关系名词表：{规范名: (契约声明的全部可接受拼法…)}。"""
    try:
        return {name: tuple(spec["accept"])
                for name, spec in _read_schema()["x-relation-vocabulary"]["names"].items()}
    except (KeyError, TypeError):
        return {}


def contract_deprecations() -> tuple[tuple[str, str, str], ...]:
    """读契约的「旧写法 → 新关系名」搬家表：((旧关系名, 旧注解值, 新关系名), …)。

    「`depends_on` + 某个 `kind` 值其实已经是一个独立关系名」这类历史写法由契约声明，
    本层只执行搬运：存储层不认识理论词，也不替判定器决定该怎么判——两个引擎看到同一条
    边就够了。
    """
    try:
        items = _read_schema()["x-relation-vocabulary"]["deprecations"]
        return tuple((str(i["relation"]), str(i["kind"]), str(i["becomes"])) for i in items)
    except (KeyError, TypeError):
        return ()


def contract_strict_vocabulary(key: str) -> tuple[str, ...]:
    """读契约 `x-strict-vocabulary` 里的一个词表（如 `depends_on.kind`）。

    契约是唯一真值；读不到就返回空元组，由调用点决定怎么退化（各引擎的退化表不同，
    因为那是各引擎自己的政策，不是契约的一部分）。
    """
    try:
        return tuple(str(v) for v in _read_schema()["x-strict-vocabulary"][key])
    except (KeyError, TypeError):
        return ()


def shape_variants(word: str) -> set[str]:
    """一个关系名的历史形状：原样、连字符、下划线、去掉分隔符。"""
    return {word, word.replace("-", "_"), word.replace("_", "-"),
            word.replace("-", "").replace("_", "")}


RELATION_VOCABULARY: dict[str, tuple[str, ...]] = contract_relation_names()
ALL_RELATION_NAMES: tuple[str, ...] = tuple(RELATION_VOCABULARY) or FALLBACK_RELATION_NAMES
# 契约认证过的每一种拼法（不只是规范名）——「这个字段名算不算已知关系」用它判。
CONTRACT_ATTESTED: frozenset[str] = frozenset(
    v for accepts in RELATION_VOCABULARY.values() for v in accepts)

# 任意拼法 → 规范名。契约变体优先，机械变体兜底。
RELATION_TYPE_NAMES: dict[str, str] = {}
for _name in ALL_RELATION_NAMES:
    for _variant in (RELATION_VOCABULARY.get(_name) or ()) or shape_variants(_name):
        RELATION_TYPE_NAMES[_variant] = _name
    for _variant in shape_variants(_name):
        RELATION_TYPE_NAMES.setdefault(_variant, _name)


def canonical_relation_name(name: str) -> str:
    """把任意历史拼法归一到规范名；未知名原样返回（自由档允许自定义关系名）。

    契约 x-relation-vocabulary.spelling-guard 规定：与已知名编辑距离 ≤1 的 type 值
    由判定层记 warning（canonlint 的 CA110），不是在这里报错——本层只归一化，不下判语。
    """
    return RELATION_TYPE_NAMES.get(name, name)


def edit_distance(a: str, b: str) -> int:
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
    if name in ALL_RELATION_NAMES:
        return None  # 本身就是规范名
    if RELATION_TYPE_NAMES.get(name) is not None:
        return None  # 是已知历史拼法，已经归一化，不必提示
    for canonical in ALL_RELATION_NAMES:
        if edit_distance(name, canonical) <= 1:
            return canonical
    return None


# ---- 一条边长什么样 ---------------------------------------------------------


@dataclass
class Relation:
    """一条边：关系名 + 目标 + 注解。同名别名 `Edge`（classlint 侧的叫法）。

    规范形只要求 `type` 与 `target`；注解（`kind`/`critical`/`stance`/`note`/`what`）
    可以缺席——**「还没想好」是合法状态，不是错误**。判定器按「缺数据不报错」处理。
    """
    type: str
    target: str
    attrs: dict

    @property
    def rel(self) -> str:
        """classlint 侧的历史叫法（`Edge.rel`）。同一个东西，不给第二份真值。"""
        return self.type

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


# ---- 文件 → frontmatter -----------------------------------------------------


@dataclass
class RawEntry:
    """一个条目的**文件层**结果：路径、相对路径、frontmatter、正文、解析错误。

    两个引擎的 `Entry` 都从这里长出来（各自的 Entry 继承它，再挂自己的规则视图）。
    读文件这一步只做一次、只有一份实现：`缺少 frontmatter` 这类判断不该有两个版本。
    """
    path: Path
    rel: str
    meta: dict
    body: str
    parse_error: str | None = None

    @property
    def id(self) -> str | None:
        v = self.meta.get("id")
        return v if isinstance(v, str) else None

    def as_entry(self, cls):
        """按目标引擎的 Entry 类重建（字段名一致，故可直接搬运）。"""
        return cls(self.path, self.rel, self.meta, self.body, self.parse_error)


def read_frontmatter(path: Path, root: Path) -> RawEntry:
    """读一个条目文件。失败也是一个结果（`parse_error`），不是异常。"""
    rel = str(path.relative_to(root))
    try:
        # utf-8-sig：容忍 BOM，避免把带 BOM 的文件误判为「缺少 frontmatter」
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as e:
        # 无法读取也是「文件无法解析」，按引擎的解析错误码报，而不是让 traceback 逃逸
        return RawEntry(path, rel, {}, "", parse_error=f"文件无法读取: {e}")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return RawEntry(path, rel, {}, text,
                        parse_error="缺少 frontmatter（文件须以 --- 包裹的 YAML 头开始）")
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return RawEntry(path, rel, {}, "",
                        parse_error=f"frontmatter YAML 解析失败: {e}")
    if not isinstance(meta, dict):
        return RawEntry(path, rel, {}, "", parse_error="frontmatter 必须是键值映射")
    return RawEntry(path, rel, meta, text[m.end():])
