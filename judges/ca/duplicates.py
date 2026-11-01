"""canonlint 的正文相似度查重规则。"""
from __future__ import annotations

import difflib


MIN_DUP_CHARS = 100


def _supersede_pairs(index) -> set[frozenset[str]]:
    pairs = set()
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        successor = e.meta.get("superseded_by")
        if isinstance(successor, str) and successor and successor != e.id:
            pairs.add(frozenset((e.id, successor)))
    return pairs


def check_ca201(world: dict, emit) -> None:
    index = world["index"]
    threshold = world["dup_threshold"]
    exempt = _supersede_pairs(index)
    items = [(e.id, e.rel, e.clean_body) for e in index.values() if not e.parse_error]
    items = [item for item in items if len(item[2]) >= MIN_DUP_CHARS]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            id_i, rel_i, text_i = items[i]
            id_j, rel_j, text_j = items[j]
            if id_i and id_j and frozenset((id_i, id_j)) in exempt:
                continue
            ratio = difflib.SequenceMatcher(None, text_i, text_j).ratio()
            if ratio >= threshold:
                emit("warning", f"{rel_i} ↔ {rel_j}",
                     f"正文相似度 {ratio:.0%} ≥ {threshold:.0%}，疑似重复")


def apply(run_world, dup_threshold: float) -> None:
    run_world("CA201", dup_threshold=dup_threshold)
