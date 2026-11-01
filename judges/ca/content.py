"""canonlint 的 CA 内容规则。"""
from __future__ import annotations

from store import Entry


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
    if not e.declares_dependencies and not e.edges_of("depends_on"):
        missing.append("depends_on")
    if missing:
        add("error", f"load_bearing: true 但缺 {missing}")
