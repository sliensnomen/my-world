"""core-ca 元数据与结构→内容的引擎日程。"""
from __future__ import annotations

from judges.model import Pack, Rule
from judges.registry import RegistryError

from . import content, structure


PACK = Pack(
    name="core-ca",
    version="1.9",
    engine="canonlint",
    ca106_fields=frozenset(),
    rules=(
        Rule(id="CA100", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca100, default_level="error",
             levels=frozenset({"error"}), order=100),
        Rule(id="CA101", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca101, default_level="error",
             levels=frozenset({"error"}), order=101),
        Rule(id="CA102", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca102, default_level="error",
             levels=frozenset({"error", "info"}), order=102),
        Rule(id="CA103", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca103, default_level="error",
             levels=frozenset({"error"}), order=103),
        Rule(id="CA104", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=content.check_ca104, default_level="warning",
             levels=frozenset({"warning"}), order=104),
        Rule(id="CA105", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca105, default_level="error",
             levels=frozenset({"error"}), order=105),
        Rule(id="CA106", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca106, default_level="error",
             levels=frozenset({"error"}), order=106),
        Rule(id="CA107", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca107, default_level="error",
             levels=frozenset({"error"}), order=107),
        Rule(id="CA108", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca108, default_level="error",
             levels=frozenset({"error", "info"}), order=108),
        Rule(id="CA109", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca109, default_level="error",
             levels=frozenset({"error"}), order=109),
        Rule(id="CA110", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca110, default_level="warning",
             levels=frozenset({"warning"}), order=110),
        Rule(id="CA111", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca111, default_level="warning",
             levels=frozenset({"warning"}), order=111),
        Rule(id="CA112", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=structure.check_ca112, default_level="error",
             levels=frozenset({"error"}), order=112),
        Rule(id="CA114", pack="core-ca", scope="world", entry_domain="",
             check=structure.check_ca114, default_level="error",
             levels=frozenset({"error"}), order=114),
        Rule(id="CA301", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=content.check_ca301, default_level="warning",
             levels=frozenset({"warning"}), order=301),
        Rule(id="CA302", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=content.check_ca302, default_level="error",
             levels=frozenset({"error"}), order=302),
    ),
)


def apply_core_ca(pack: Pack, all_entries, index, issues, known_fields, emit) -> None:
    """先适配 store 的 CA114，再逐条目交错执行结构与内容规则。"""
    rules = {rule.id: rule for rule in pack.rules}

    def adapted_emit(rule: Rule, level, rel, message):
        actual_level = rule.default_level if level is None else level
        if actual_level not in rule.levels:
            raise RegistryError(f"规则 {rule.id} 发出未登记级别: {actual_level!r}")
        emit(rule.id, actual_level, rel, message)

    initial = rules["CA114"]
    initial.check(
        {"all_entries": all_entries, "index": index, "issues": issues},
        lambda level, rel, message: adapted_emit(initial, level, rel, message),
    )

    for entry in all_entries:
        def run_rule(rule_id, **kwargs):
            rule = rules[rule_id]
            if rule.scope != "entry" or rule.entry_domain != "all_entries":
                raise RegistryError(f"core-ca 不能在 all_entries 日程调度规则 {rule.id}")

            def add(level, message):
                adapted_emit(rule, level, entry.rel, message)

            rule.check(entry, entry.rel, add, **kwargs)

        def run_schema_errors(errors):
            for error in errors:
                if error.rule not in ("CA107", "CA109"):
                    raise RegistryError(f"core-ca 收到未知结构错误规则 {error.rule}")
                run_rule(error.rule, error=error)

        run_rule("CA100")
        if entry.parse_error:
            continue
        run_rule("CA101")
        run_rule("CA102", phase="fields")
        run_rule("CA103")
        run_rule("CA105")
        run_rule("CA106", known_fields=known_fields)
        run_rule("CA112")
        run_rule("CA109", phase="booleans")
        run_schema_errors(entry.deps[1])
        run_rule("CA108")
        run_schema_errors(entry.conflicts[1])
        run_rule("CA102", phase="stance")
        run_schema_errors(entry.canon_ref_ids[1])
        run_schema_errors(entry.named_relation_errors)
        run_schema_errors(entry.relation_errors)
        run_rule("CA110")
        run_rule("CA111")
        run_rule("CA104")
        run_rule("CA301")
        run_rule("CA302")
