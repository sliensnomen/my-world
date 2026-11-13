"""CA 协议词表与阈值：唯一定义点。

canonlint.py 的 legacy 后端与 judges/ca 的 registry 后端都从这里转发
（评审 docs/代码评审报告-架构.md §4.2：原先这些常量字面量双抄，只靠输出级
双跑贴住，夹具没踩到的漂移抓不住）。改动这里的任何值 = 协议变更，须按
AGENTS.md 升 PROTOCOL_VERSION 并同步 PROTOCOL.md §6.3 规则表；
tests/test_store.py 的「只有一份定义」锁禁止在别处再绑定这些名字。
"""
from __future__ import annotations

import re

import store

# 顶层字段表归存储层（store/model.py 的 FIELD_TABLE）；这里取它的快照当 CA106 的默认词表，
# 扩展包再用 --pack 往 extra_known 里加自己的字段。
KNOWN_FIELDS = store.FIELD_TABLE

REQUIRED_FIELDS = [
    "id", "title", "type", "author", "date", "status", "load_bearing",
    "canon_refs", "conflicts_with", "ai_assisted",
]
VALID_TYPES = {"location", "faction", "character", "event", "item"}
# 实验类型（1.1）：x-<命名空间>-<名称>，与 kind 的 x- 泄压阀同一套（§5.4）——
# 能存、不判错，CA102 记 info；确定普适了再进 VALID_TYPES（那一步才是收紧词表）。
X_TYPE_RE = re.compile(r"^x-[a-z0-9]+-[a-z0-9-]+$")
VALID_STATUS = {"draft", "trial", "canon", "archived"}
VALID_STANCE = {"official", "heretic", "unknown"}
LAYERS = ["geo", "resource", "production", "economy", "fiscal", "military",
          "political", "ideology"]
LAYER_INDEX = {name: i for i, name in enumerate(LAYERS)}

# `depends_on` 的 kind 词表：这五类就是「哪一类物资」（契约 x-strict-vocabulary.depends_on.kind）。
# 「算不算承重」不再由 kind 决定——那是关系名的事：物质承重是 `depends_on`，
# 名分依据是 `derives_legitimacy_from`（拆分前写作 depends_on + kind: legitimacy）。
KIND_INITIAL_SET = {"resource", "production", "economy", "fiscal", "manpower"}
CA503_LAYERS = {"economy", "fiscal", "military", "political"}  # ideology 豁免
CA505_TRIGGER_LAYERS = {"military", "political"}

WORLD_REF_RE = re.compile(r"^[a-z0-9-]+:")  # world:id 形式，本版不支持（ID_RE 见 store/model.py）

# 已经有专属引用检查的关系（各自带状态语义：canon_refs 的 CA402/CA405、depends_on 的
# CA404 等）。剩下的关系没有专属规则，但**目标存在性**是结构问题，不属于哪一层的理论：
# 从前这六种字段一条都不查，于是 `owns: [幽灵]` 在 canonlint 里完全隐形。
# 只取**规范名**：`RELATION_TYPE_NAMES` 的键包含每一种可接受拼法，按它遍历会把同一条
# 边按 canon-ref / canon-refs / canonrefs 报三遍。
# 有专属引用检查的关系（各自带状态语义，见下）。
_RELATIONS_WITH_OWN_REFERENCE_RULES = frozenset({
    "canon_refs", "conflicts_with", "depends_on", "exchanges_with",
    "derives_legitimacy_from"})

# 附录 A · 承重墙关键词清单
LOAD_BEARING_KEYWORDS = ["经济", "货币", "税收", "贸易", "铸币", "政治",
                         "政权", "法律", "继承", "选帝", "军队", "征兵", "战争赔款"]

MIN_BODY_CHARS = 200        # CA104
MIN_DUP_CHARS = 100         # CA201 最短参与长度
