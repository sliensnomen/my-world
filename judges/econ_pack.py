"""WGP-econ 的 Registry 元数据与 Finding 适配。"""
from __future__ import annotations

import econ

from .model import Pack, Rule


def _check_rule(rule_id, meta, rel, add) -> None:
    def forward(actual_id, level, message):
        if actual_id == rule_id:
            add(level, message)

    econ.check_entry(meta, rel, forward)


def check_ca601(meta, rel, add) -> None:
    _check_rule("CA601", meta, rel, add)


def check_ca602(meta, rel, add) -> None:
    _check_rule("CA602", meta, rel, add)


PACK = Pack(
    name=econ.PACK_NAME,
    version=econ.PACK_VERSION,
    engine="canonlint",
    ca106_fields=frozenset(econ.KNOWN_FIELDS),
    rules=(
        Rule(id="CA601", pack="econ", scope="entry",
             entry_domain="index_parseable", check=check_ca601,
             default_level="error", levels=frozenset({"error"}), order=1),
        Rule(id="CA602", pack="econ", scope="entry",
             entry_domain="index_parseable", check=check_ca602,
             default_level="warning", levels=frozenset({"warning"}), order=2),
    ),
)
