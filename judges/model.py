"""判定规则与规则包的不可变元数据。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    pack: str
    scope: str
    entry_domain: str
    check: object
    default_level: str
    levels: frozenset[str]
    order: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "levels", frozenset(self.levels))


@dataclass(frozen=True)
class Pack:
    name: str
    version: str
    engine: str
    ca106_fields: frozenset[str]
    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ca106_fields", frozenset(self.ca106_fields))
        object.__setattr__(self, "rules", tuple(self.rules))
