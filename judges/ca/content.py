"""canonlint 的 CA 内容规则。"""
from __future__ import annotations

from store import Entry
from store.model import (
    DEPENDENCY_DECLARING_RELATIONS,
    MIGRATED_RELATIONS,
    RELATIONS_FIELD,
    canonical_relation_name,
)


def declares_dependencies(e: Entry) -> bool:
    """作者是否就「依赖」这件事做了声明（CA302 语义；#14 从 store/model 搬来）。

    两种写法必须是同一句话，所以判据是**声明**而不是「有没有边」：

    - 旧写法 `depends_on: []` —— 字段在，声明了「没有依赖」；
    - 规范形 `relations: []` —— 整张关系表是空的，同样是声明了「没有依赖」；
    - 规范形里只有别的边（例如只有一条 `conflicts-with`）—— 作者对依赖**什么都没说**；
      注意「写了 depends_on 边但形状写错」**算**声明（`relations:` 里有这一项就够）。
    """
    if "depends_on" in e.meta:
        return True
    if any(isinstance(k, str) and canonical_relation_name(k) in MIGRATED_RELATIONS
           for k in e.meta):
        return True
    raw = e.meta.get(RELATIONS_FIELD)
    if not isinstance(raw, list):
        return False
    if not raw:
        return True
    return any(isinstance(i, dict)
               and canonical_relation_name(str(i.get("type") or "")) in
               DEPENDENCY_DECLARING_RELATIONS
               for i in raw)


LOAD_BEARING_KEYWORDS = ["经济", "货币", "税收", "贸易", "铸币", "政治",
                         "政权", "法律", "继承", "选帝", "军队", "征兵", "战争赔款"]
MIN_BODY_CHARS = 200


def check_ca104(e: Entry, rel: str, add) -> None:
    if not e.parse_error and e.status in ("trial", "canon") and len(e.clean_body) < MIN_BODY_CHARS:
        add("warning", f"正文 {len(e.clean_body)} 字，{e.status} 档建议 ≥{MIN_BODY_CHARS} 字")


def check_ca301(e: Entry, rel: str, add) -> None:
    if e.parse_error or e.meta.get("load_bearing") is True:
        return
    hay = str(e.meta.get("title", "")) + e.clean_body
    hits = [kw for kw in LOAD_BEARING_KEYWORDS if kw in hay]
    if hits and e.status in ("trial", "canon"):
        add("warning", f"命中承重墙关键词 {hits}，但未声明 load_bearing——请考虑声明")


def check_ca302(e: Entry, rel: str, add) -> None:
    if e.parse_error or e.meta.get("load_bearing") is not True:
        return
    missing = []
    if "layer" not in e.meta:
        missing.append("layer")
    if not declares_dependencies(e) and not e.edges_of("depends_on"):
        missing.append("depends_on")
    if missing:
        add("error", f"load_bearing: true 但缺 {missing}")
