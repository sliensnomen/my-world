"""core-ca 元数据与结构→内容的引擎日程。"""
from __future__ import annotations

from judges.model import Pack, Rule
from judges.registry import RegistryError

from . import chain, content, duplicates, events, refs, structure
from . import ledger as ca_ledger


def _check_ca102(e, rel, add, phase="all"):
    if phase == "events":
        return events.check_ca102(e, rel, add)
    return structure.check_ca102(e, rel, add, phase=phase)


def _check_ca109(e, rel, add, phase="all", error=None, **kwargs):
    if phase == "superseded_by":
        return refs.check_ca109_superseded(e, rel, add, **kwargs)
    if phase == "assertion":
        return refs.check_ca109_assertion(e, rel, add, **kwargs)
    if phase == "events":
        return events.check_ca109(e, rel, add)
    return structure.check_ca109(e, rel, add, phase=phase, error=error)


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
             check=_check_ca102, default_level="error",
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
             check=_check_ca109, default_level="error",
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
        Rule(id="CA201", pack="core-ca", scope="world", entry_domain="",
             check=duplicates.check_ca201, default_level="warning",
             levels=frozenset({"warning"}), order=201),
        Rule(id="CA301", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=content.check_ca301, default_level="warning",
             levels=frozenset({"warning"}), order=301),
        Rule(id="CA302", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=content.check_ca302, default_level="error",
             levels=frozenset({"error"}), order=302),
        Rule(id="CA401", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=refs.check_ca401, default_level="error",
             levels=frozenset({"error"}), order=401),
        Rule(id="CA402", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=refs.check_ca402, default_level="error",
             levels=frozenset({"error"}), order=402),
        Rule(id="CA403", pack="core-ca", scope="world", entry_domain="",
             check=refs.check_ca403, default_level="warning",
             levels=frozenset({"warning"}), order=403),
        Rule(id="CA404", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=refs.check_ca404, default_level="error",
             levels=frozenset({"error"}), order=404),
        Rule(id="CA405", pack="core-ca", scope="world", entry_domain="",
             check=refs.check_ca405, default_level="error",
             levels=frozenset({"error"}), order=405),
        Rule(id="CA501", pack="core-ca", scope="entry", entry_domain="index_parseable",
             check=chain.check_ca501, default_level="error",
             levels=frozenset({"error"}), order=501),
        Rule(id="CA502", pack="core-ca", scope="world", entry_domain="",
             check=chain.check_ca502, default_level="error",
             levels=frozenset({"error"}), order=502),
        Rule(id="CA503", pack="core-ca", scope="entry", entry_domain="index_parseable",
             check=chain.check_ca503, default_level="warning",
             levels=frozenset({"warning"}), order=503),
        Rule(id="CA504", pack="core-ca", scope="world", entry_domain="",
             check=chain.check_ca504, default_level="info",
             levels=frozenset({"info"}), order=504),
        Rule(id="CA505", pack="core-ca", scope="world", entry_domain="",
             check=chain.check_ca505, default_level="warning",
             levels=frozenset({"warning"}), order=505),
        Rule(id="CA701", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca701, default_level="warning",
             levels=frozenset({"warning"}), order=701),
        Rule(id="CA702", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=events.check_ca702, default_level="error",
             levels=frozenset({"error"}), order=702),
        Rule(id="CA703", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca703, default_level="warning",
             levels=frozenset({"warning"}), order=703),
        Rule(id="CA704", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca704, default_level="error",
             levels=frozenset({"error", "warning"}), order=704),
        Rule(id="CA705", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca705, default_level="warning",
             levels=frozenset({"warning"}), order=705),
        Rule(id="CA706", pack="core-ca", scope="entry", entry_domain="all_entries",
             check=events.check_ca706, default_level="warning",
             levels=frozenset({"warning"}), order=706),
        Rule(id="CA707", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca707, default_level="warning",
             levels=frozenset({"warning"}), order=707),
        Rule(id="CA708", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca708, default_level="warning",
             levels=frozenset({"warning"}), order=708),
        Rule(id="CA709", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca709, default_level="error",
             levels=frozenset({"error", "warning"}), order=709),
        Rule(id="CA710", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca710, default_level="warning",
             levels=frozenset({"warning"}), order=710),
        Rule(id="CA711", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca711, default_level="warning",
             levels=frozenset({"warning"}), order=711),
        Rule(id="CA712", pack="core-ca", scope="world", entry_domain="",
             check=ca_ledger.check_ca712, default_level="error",
             levels=frozenset({"error"}), order=712),
    ),
)


def apply_core_ca(pack: Pack, all_entries, index, issues, known_fields, emit,
                  dup_threshold=0.85) -> None:
    """按结构→内容→引用→链→事件→流水→查重执行完整 core-ca。"""
    rules = {rule.id: rule for rule in pack.rules}
    world = {"all_entries": all_entries, "index": index, "issues": issues}

    def adapted_emit(rule: Rule, level, rel, message):
        actual_level = rule.default_level if level is None else level
        if actual_level not in rule.levels:
            raise RegistryError(f"规则 {rule.id} 发出未登记级别: {actual_level!r}")
        emit(rule.id, actual_level, rel, message)

    def run_entry(rule_id, entry, **kwargs):
        rule = rules[rule_id]
        if rule.scope != "entry":
            raise RegistryError(f"core-ca 不能在条目日程调度规则 {rule.id}")

        def add(level, message):
            adapted_emit(rule, level, entry.rel, message)

        return rule.check(entry, entry.rel, add, **kwargs)

    def run_world(rule_id, **kwargs):
        rule = rules[rule_id]
        if rule.scope != "world":
            raise RegistryError(f"core-ca 不能在仓库日程调度规则 {rule.id}")
        context = dict(world)
        context.update(kwargs)
        return rule.check(
            context, lambda level, rel, message: adapted_emit(rule, level, rel, message))

    run_world("CA114")
    for entry in all_entries:
        def run_schema_errors(errors):
            for error in errors:
                if error.rule not in ("CA107", "CA109"):
                    raise RegistryError(f"core-ca 收到未知结构错误规则 {error.rule}")
                run_entry(error.rule, entry, error=error)

        run_entry("CA100", entry)
        if entry.parse_error:
            continue
        run_entry("CA101", entry)
        run_entry("CA102", entry, phase="fields")
        run_entry("CA103", entry)
        run_entry("CA105", entry)
        run_entry("CA106", entry, known_fields=known_fields)
        run_entry("CA112", entry)
        run_entry("CA109", entry, phase="booleans")
        run_schema_errors(entry.deps[1])
        run_entry("CA108", entry)
        run_schema_errors(entry.conflicts[1])
        run_entry("CA102", entry, phase="stance")
        run_schema_errors(entry.canon_ref_ids[1])
        run_schema_errors(entry.named_relation_errors)
        run_schema_errors(entry.relation_errors)
        run_entry("CA110", entry)
        run_entry("CA111", entry)
        run_entry("CA104", entry)
        run_entry("CA301", entry)
        run_entry("CA302", entry)

    refs.apply(all_entries, index, run_entry, run_world)
    chain.apply(index, run_entry, run_world)
    events.apply(all_entries, run_entry)
    ca_ledger.apply(run_world)
    duplicates.apply(run_world, dup_threshold)


def apply_core_ca_ledger(pack: Pack, index, emit) -> None:
    """只执行 ledger 报告所需的 core-ca 流水规则，保持既有族内顺序。"""
    rules = {rule.id: rule for rule in pack.rules}
    world = {"all_entries": list(index.values()), "index": index, "issues": []}

    def run_world(rule_id):
        rule = rules[rule_id]
        if rule.scope != "world":
            raise RegistryError(f"core-ca 不能在流水日程调度规则 {rule.id}")

        def adapted_emit(level, rel, message):
            actual_level = rule.default_level if level is None else level
            if actual_level not in rule.levels:
                raise RegistryError(f"规则 {rule.id} 发出未登记级别: {actual_level!r}")
            emit(rule.id, actual_level, rel, message)

        return rule.check(world, adapted_emit)

    ca_ledger.apply(run_world)


def apply_core_ca_reports(pack: Pack, index, subjects):
    rule = next(rule for rule in pack.rules if rule.id == "CA504")

    def reject_emit(level, rel, message):
        raise RegistryError("CA504 只能生成 report，不能发射 Finding")

    return rule.check({"index": index, "subjects": subjects}, reject_emit)
