"""双跑比较工具：把动态量洗掉，留下语义差异。

比较器不替调用方做判定，只做两件事：
1. 把 Finding、CLI stdout/stderr、HTTP 响应和审计日志里的非语义动态量
   （临时根路径、Date 头、日志 ts）归一化；
2. 对归一化后的结果做严格相等比较，不等就抛 AssertionError。

调用方必须同时比较驱动原始序列和出口排序后序列，不能只比最终排序。
"""
from __future__ import annotations

import json
from typing import Any


def finding_tuple(f) -> tuple[str, str, str, str]:
    """把 Finding 转成可严格比较的四元组。"""
    return (f.rule, f.level, f.entry, f.message)


def normalized_cli_result(code: int, stdout: str, stderr: str, root) -> tuple:
    """CLI 输出归一化：把临时根路径换成 <WORLD>，保留退出码和其余字节。"""
    root_s = str(root)
    return (code, stdout.replace(root_s, "<WORLD>"), stderr.replace(root_s, "<WORLD>"))


def normalized_http_result(status: int, body: bytes, headers: dict[str, str]) -> tuple:
    """HTTP 响应归一化：去掉传输级 Date 头，保留 status、body 与语义头部。"""
    semantic = {k: v for k, v in headers.items() if k.lower() != "date"}
    return (status, body, semantic)


def _normalize_log(record: Any, clock: Any) -> dict:
    """把日志记录里的 ts 替换成注入的固定时钟，其余字段不动。"""
    if isinstance(record, str):
        record = json.loads(record)
    rec = dict(record)
    rec["ts"] = clock
    return rec


def _assert_equal(label: str, old, new) -> None:
    if old != new:
        raise AssertionError(
            f"{label} 双跑结果不一致\n  旧: {old!r}\n  新: {new!r}")


def assert_cli_equal(old, new) -> None:
    """比较归一化后的 CLI 结果 (code, stdout, stderr)。"""
    _assert_equal("CLI", old, new)


def assert_http_equal(old, new) -> None:
    """比较归一化后的 HTTP 结果 (status, body, semantic_headers)。"""
    _assert_equal("HTTP", old, new)


def assert_log_equal(old, new, clock) -> None:
    """比较审计日志记录，ts 用注入的固定时钟归一化。"""
    _assert_equal("log", _normalize_log(old, clock), _normalize_log(new, clock))
