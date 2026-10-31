"""PE 独立 Pack、编号顺序与 rules: off 执行适配。"""
from __future__ import annotations

from judges.model import Pack, Rule
from judges.registry import RegistryError

from . import rules as pe_rules


PACK = Pack(
    name="pe",
    version="0.1",
    engine="classlint",
    ca106_fields=frozenset(),
    rules=(
        Rule(id="PE001", pack="pe", scope="world", entry_domain="",
             check=pe_rules.check_pe001, default_level="error",
             levels=frozenset({"error"}), order=1),
        Rule(id="PE002", pack="pe", scope="world", entry_domain="",
             check=pe_rules.check_pe002, default_level="error",
             levels=frozenset({"error", "warning"}), order=2),
        Rule(id="PE003", pack="pe", scope="world", entry_domain="",
             check=pe_rules.check_pe003, default_level="error",
             levels=frozenset({"error"}), order=3),
        Rule(id="PE004", pack="pe", scope="world", entry_domain="",
             check=pe_rules.check_pe004, default_level="error",
             levels=frozenset({"error"}), order=4),
        Rule(id="PE005", pack="pe", scope="world", entry_domain="",
             check=pe_rules.check_pe005, default_level="warning",
             levels=frozenset({"warning"}), order=5),
        Rule(id="PE009", pack="pe", scope="world", entry_domain="",
             check=pe_rules.check_pe009, default_level="warning",
             levels=frozenset({"warning"}), order=9),
    ),
)


def apply_pe(pack: Pack, world, disabled, emit) -> None:
    for rule in sorted(pack.rules, key=lambda item: item.order):
        if rule.id in disabled:
            continue
        if rule.scope != "world":
            raise RegistryError(f"pe 不能在仓库日程调度规则 {rule.id}")

        def adapted_emit(level, entry, message, _rule=rule):
            actual_level = _rule.default_level if level is None else level
            if actual_level not in _rule.levels:
                raise RegistryError(f"规则 {_rule.id} 发出未登记级别: {actual_level!r}")
            emit(_rule.id, actual_level, entry, message)

        rule.check(world, adapted_emit)
