"""canonlint 的正文相似度查重规则。"""
from __future__ import annotations

import difflib
from collections import Counter

from .vocab import MIN_DUP_CHARS, MIN_EXACT_DUP_CHARS


def _supersede_pairs(index) -> set[frozenset[str]]:
    pairs = set()
    for e in index.values():
        if e.parse_error or not e.id:
            continue
        # 审计 §1.2：只有归档方声明的承接对才豁免；canon 卡不能拿一行字段关掉查重。
        if e.meta.get("status") != "archived":
            continue
        successor = e.meta.get("superseded_by")
        if isinstance(successor, str) and successor and successor != e.id:
            pairs.add(frozenset((e.id, successor)))
    return pairs


_SAMPLE_STRIDE = 8


def _sample_grams(text: str) -> frozenset[int]:
    """8 字步长取 8 字 shingle 的哈希样本：O(n/8)；重复正文样本重合度 ≈ 相似度。"""
    return frozenset(hash(text[i:i + 8]) for i in range(0, max(1, len(text) - 7),
                                                      _SAMPLE_STRIDE))


def _max_ratio(len1: int, len2: int) -> float:
    """两个字符串的 difflib 相似度上界（相似度 = 2·M/(len1+len2)，M ≤ min）。"""
    if len1 <= 0 or len2 <= 0:
        return 0.0
    return 2.0 * min(len1, len2) / (len1 + len2)


def check_ca201(world: dict, emit) -> None:
    index = world["index"]
    threshold = world["dup_threshold"]
    exempt = _supersede_pairs(index)
    items = [(e.id, e.rel, e.clean_body) for e in index.values() if not e.parse_error]
    exact: dict[str, list[tuple[str, str]]] = {}
    for item in items:
        body = item[2]
        if MIN_EXACT_DUP_CHARS <= len(body) < MIN_DUP_CHARS:
            exact.setdefault(body, []).append((item[0], item[1]))
    for body, group in exact.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                id_i, rel_i = group[i]
                id_j, rel_j = group[j]
                if id_i and id_j and frozenset((id_i, id_j)) in exempt:
                    continue
                emit("warning", f"{rel_i} ↔ {rel_j}",
                     f"正文完全重复（{len(body)} 字，低于常规查重长度 {MIN_DUP_CHARS}）"
                     "——精确重复不设长度豁免，疑似重复")
    items = [item for item in items if len(item[2]) >= MIN_DUP_CHARS]
    # #15：每张卡的字频表只建一次；相似度上界 = 2·重叠字频/(len1+len2)。
    # 上界低于阈值的候选对直接剪掉——上界是 difflib ratio 的严格上界，
    # 所以召回率不变，O(n²) 的 SequenceMatcher 只留给真正可能重复的对。
    counters = [Counter(text) for _id, _rel, text in items]
    lengths = [len(text) for _id, _rel, text in items]
    grams = [_sample_grams(text) for _id, _rel, text in items]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            id_i, rel_i, text_i = items[i]
            id_j, rel_j, text_j = items[j]
            if id_i and id_j and frozenset((id_i, id_j)) in exempt:
                continue
            upper = 2.0 * sum((counters[i] & counters[j]).values()) / (
                lengths[i] + lengths[j] or 1)
            if upper < threshold:
                continue
            # 字频上界对「同一词表洗牌」无区分力；再看 8 字 shingle 样本的
            # 重合率（≈ 真实相似度），远低于阈值的一律剪掉。
            common = len(grams[i] & grams[j])
            sample_est = common / min(len(grams[i]), len(grams[j]) or 1)
            if sample_est < threshold * 0.5:
                continue
            matcher = difflib.SequenceMatcher(None, text_i, text_j)
            if matcher.quick_ratio() < threshold:
                continue
            ratio = matcher.ratio()
            if ratio >= threshold:
                emit("warning", f"{rel_i} ↔ {rel_j}",
                     f"正文相似度 {ratio:.0%} ≥ {threshold:.0%}，疑似重复")


def apply(run_world, dup_threshold: float) -> None:
    run_world("CA201", dup_threshold=dup_threshold)
