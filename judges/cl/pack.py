"""core-cl 元数据与 classlint 私有的 Finding 拼接日程。"""
from __future__ import annotations

from judges.model import Pack, Rule
from judges.registry import RegistryError

from . import structure


PACK = Pack(
    name="core-cl",
    version="0.1",
    engine="classlint",
    ca106_fields=frozenset(),
    rules=(
        Rule(id="CL100", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl100, default_level="error",
             levels=frozenset({"error"}), order=100),
        Rule(id="CL101", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl101, default_level="error",
             levels=frozenset({"error"}), order=101),
        Rule(id="CL102", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl102, default_level="error",
             levels=frozenset({"error"}), order=102),
        Rule(id="CL103", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl103, default_level="error",
             levels=frozenset({"error"}), order=103),
        Rule(id="CL104", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl104, default_level="error",
             levels=frozenset({"error"}), order=104),
        Rule(id="CL105", pack="core-cl", scope="world", entry_domain="",
             check=structure.check_cl105, default_level="error",
             levels=frozenset({"error"}), order=105),
        Rule(id="CL106", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl106, default_level="warning",
             levels=frozenset({"warning"}), order=106),
        Rule(id="CL107", pack="core-cl", scope="entry", entry_domain="all_entries",
             check=structure.check_cl107, default_level="warning",
             levels=frozenset({"warning"}), order=107),
    ),
)


def apply_core_cl(pack: Pack, entries, index, model, known_fields, emit) -> None:
    """保留 collect 的逐卡顺序、CL106 后扫与最后 CL105，而非按 Rule.order 排序。"""
    rules = {rule.id: rule for rule in pack.rules}
    context = {"all_entries": entries, "index": index, "model": model}

    def adapted_emit(rule: Rule, level, rel, message):
        actual_level = rule.default_level if level is None else level
        if actual_level not in rule.levels:
            raise RegistryError(f"规则 {rule.id} 发出未登记级别: {actual_level!r}")
        emit(rule.id, actual_level, rel, message)

    def run_entry(rule_id, entry, **kwargs):
        rule = rules[rule_id]
        if rule.scope != "entry" or rule.entry_domain != "all_entries":
            raise RegistryError(f"core-cl 不能在条目日程调度规则 {rule.id}")

        def add(level, message):
            adapted_emit(rule, level, entry.rel, message)

        return rule.check(entry, entry.rel, add, **kwargs)

    def run_world(rule_id):
        rule = rules[rule_id]
        if rule.scope != "world":
            raise RegistryError(f"core-cl 不能在仓库日程调度规则 {rule.id}")
        return rule.check(
            context, lambda level, rel, message: adapted_emit(rule, level, rel, message))

    for entry in entries:
        run_entry("CL100", entry)
        if entry.parse_error:
            continue
        run_entry("CL101", entry)
        run_entry("CL103", entry, known_fields=known_fields)
        run_entry("CL107", entry)
        run_entry("CL102", entry, index=index)
        run_entry("CL104", entry)
    for entry in entries:
        run_entry("CL106", entry)
    run_world("CL105")
