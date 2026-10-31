"""规则包加载、选择与元数据校验。"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from types import MappingProxyType
from typing import Mapping

from .model import Pack, Rule


class RegistryError(ValueError):
    """规则包或后端配置无效。"""


_VALID_SCOPES = frozenset({"entry", "world"})
_VALID_ENTRY_DOMAINS = frozenset({"all_entries", "all_parseable", "index_parseable"})
_VALID_LEVELS = frozenset({"error", "warning", "info"})
_PACK_MODULES = {
    ("canonlint", "core-ca"): "judges.ca.pack",
    ("canonlint", "econ"): "judges.econ_pack",
    ("classlint", "core-cl"): "judges.cl.pack",
    ("classlint", "pe"): "judges.pe.pack",
}
_MODULE_CACHE = {}


@dataclass(frozen=True)
class Registry:
    packs: Mapping[str, Pack]
    selected: tuple[Pack, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "packs", MappingProxyType(dict(self.packs)))
        object.__setattr__(self, "selected", tuple(self.selected))
        self._validate()

    @property
    def ca106_fields(self) -> frozenset[str]:
        fields = set()
        for pack in self.selected:
            fields.update(pack.ca106_fields)
        return frozenset(fields)

    def _validate(self) -> None:
        for name, pack in self.packs.items():
            if name != pack.name:
                raise RegistryError(f"Pack 映射键 {name!r} 与 Pack 名 {pack.name!r} 不一致")
            _validate_pack(pack)

        selected_packs = set()
        rule_ids = set()
        field_owners = {}
        for pack in self.selected:
            if self.packs.get(pack.name) is not pack:
                raise RegistryError(f"选中的 Pack {pack.name!r} 不在注册表映射中")
            if pack.name in selected_packs:
                continue
            selected_packs.add(pack.name)
            for rule in pack.rules:
                if rule.id in rule_ids:
                    raise RegistryError(f"当前选择集存在重复规则 id: {rule.id}")
                rule_ids.add(rule.id)
            for field in pack.ca106_fields:
                if field.startswith("x-"):
                    continue
                if field in field_owners:
                    raise RegistryError(
                        f"当前选择集的 ca106_fields 冲突: {field!r} "
                        f"同时属于 {field_owners[field]!r} 与 {pack.name!r}")
                field_owners[field] = pack.name


def _validate_pack(pack: Pack) -> None:
    orders = set()
    rule_ids = set()
    for rule in pack.rules:
        if rule.pack != pack.name:
            raise RegistryError(f"规则 {rule.id} 的 pack={rule.pack!r} 与所属 Pack {pack.name!r} 不一致")
        if rule.id in rule_ids:
            raise RegistryError(f"Pack {pack.name!r} 存在重复规则 id: {rule.id}")
        rule_ids.add(rule.id)
        if rule.order in orders:
            raise RegistryError(f"Pack {pack.name!r} 存在重复 order: {rule.order}")
        orders.add(rule.order)
        _validate_rule(rule)


def _validate_rule(rule: Rule) -> None:
    if rule.scope not in _VALID_SCOPES:
        raise RegistryError(f"规则 {rule.id} 的 scope 非法: {rule.scope!r}")
    if rule.scope == "entry" and rule.entry_domain not in _VALID_ENTRY_DOMAINS:
        raise RegistryError(f"规则 {rule.id} 的 entry_domain 非法: {rule.entry_domain!r}")
    if not rule.levels or not rule.levels <= _VALID_LEVELS:
        raise RegistryError(f"规则 {rule.id} 的 levels 非法: {sorted(rule.levels)!r}")
    if rule.default_level not in _VALID_LEVELS or rule.default_level not in rule.levels:
        raise RegistryError(
            f"规则 {rule.id} 的 default_level={rule.default_level!r} 不在 levels 中")
    if not callable(rule.check):
        raise RegistryError(f"规则 {rule.id} 的 check 不可调用")


def load_backend(env=None) -> str:
    """读取判定后端；缺省保持 legacy，非法值在任何审计前失败。"""
    env = os.environ if env is None else env
    backend = env.get("WGP_JUDGE_BACKEND", "legacy")
    if backend not in ("legacy", "registry"):
        raise RegistryError(
            f"WGP_JUDGE_BACKEND={backend!r} 非法，只接受 legacy 或 registry")
    return backend


def select_packs(engine: str, names) -> Registry:
    """按选择列表加载内置 Pack；模块缓存不影响重复选择语义。"""
    selected = []
    packs = {}
    for name in names:
        key = (engine, name)
        module_name = _PACK_MODULES.get(key)
        if module_name is None:
            raise RegistryError(f"未知 Pack: {engine}/{name}")
        if key not in _MODULE_CACHE:
            try:
                _MODULE_CACHE[key] = importlib.import_module(module_name)
            except ImportError as e:
                raise RegistryError(f"Pack {engine}/{name} 加载失败: {e}") from e
        pack = getattr(_MODULE_CACHE[key], "PACK", None)
        if not isinstance(pack, Pack):
            raise RegistryError(f"Pack {engine}/{name} 未提供有效的 PACK 元数据")
        if pack.name != name or pack.engine != engine:
            raise RegistryError(f"Pack {engine}/{name} 的元数据名称或引擎不一致")
        packs.setdefault(name, pack)
        selected.append(pack)
    return Registry(packs, tuple(selected))
