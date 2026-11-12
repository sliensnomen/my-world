"""存储层（store）——「世界里写了什么」的读写契约。

本包的职责边界，一句话：**文件格式的读写，与理论无关**。

  放这里：条目模型与解析（model）、字段表与 id 语法（model）、文件布局与扫描（layout）、
          写入命令（write）。
  不放这里：任何「这样写对不对」的**判断**。层级方向、承重墙、盲区、合法性闭环、
          一条关系讲不讲得通——全部属于判定器（canonlint.py 的规则，未来 rules/）。

判据：只改存储的人，不需要读任何政治经济学文档就能改对；只写规则的人，不需要碰文件
     读写就能加一条检查。

对外接口（canonlint.py 只用这些）：
  Entry / Relation / Dep / ConflictRef / SchemaError / ShapeIssue / parse_entry
  FIELD_TABLE / CORE_REQUIRED_FIELDS / ID_RE / LEGACY_RELATION_FIELDS / RELATIONS_FIELD
  EVENT_FIELDS（事件流水六字段，协议 1.2）
  collect / iter_entry_paths / looks_like_world / ENTRY_DIRS / SKIP_DIRS / TYPE_DIRS
  cmd_init / cmd_new / cmd_link / set_fields / restore_bytes / slugify / CONSTITUTION_SKELETON

改动清单与「30 分钟上手」见 store/README.md。
"""

# 契约加载本身要轻：`import store` 不能因为契约坏掉就在包初始化里炸成 traceback，
# 引擎需要先拿到 `ContractError` 才能把失败打印成一句人话（见 #12）。
# 其余名字按需加载（PEP 562）：真正读卡时才触发 `store.parse` 的契约体检。
from .contract import ContractError, contract_status, get_contract  # noqa: F401

_LAZY = {
    # 布局
    "ENTRY_DIRS": "layout", "SKIP_DIRS": "layout", "TYPE_DIRS": "layout",
    "collect": "layout", "iter_entry_paths": "layout", "looks_like_world": "layout",
    # 模型 / 解析
    "CANONICAL_RELATION_ITEMS": "model", "CORE_REQUIRED_FIELDS": "model",
    "EVENT_FIELDS": "model", "FIELD_TABLE": "model", "ID_RE": "model",
    "LEGACY_RELATION_FIELDS": "model", "NAMED_RELATION_ATTRS": "model",
    "RELATIONS_FIELD": "model", "RELATION_TYPE_NAMES": "model",
    "RELATION_VOCABULARY": "model",
    "ConflictRef": "model", "Dep": "model", "Entry": "model", "Relation": "model",
    "SchemaError": "model", "ShapeIssue": "model",
    "canonical_relation_name": "model", "nearest_relation_name": "model",
    "parse_entry": "model", "parse_text": "model", "read_frontmatter": "model",
    "RawEntry": "model", "load_meta": "model",
    # 写入
    "CONSTITUTION_SKELETON": "write", "cmd_init": "write", "cmd_link": "write",
    "cmd_new": "write", "restore_bytes": "write", "set_fields": "write",
    "slugify": "write",
    # 判定口径（#14）
    "JudgmentPolicy": "policy", "CANONLINT_POLICY": "policy", "CLASSLINT_POLICY": "policy",
}

_SUBMODULES = {"layout", "model", "write", "parse", "contract", "policy"}

__all__ = [
    "ENTRY_DIRS", "SKIP_DIRS", "TYPE_DIRS", "collect", "iter_entry_paths",
    "looks_like_world",
    "CANONICAL_RELATION_ITEMS", "CORE_REQUIRED_FIELDS", "EVENT_FIELDS", "FIELD_TABLE",
    "ID_RE",
    "LEGACY_RELATION_FIELDS", "NAMED_RELATION_ATTRS", "RELATIONS_FIELD",
    "RELATION_TYPE_NAMES", "RELATION_VOCABULARY", "ConflictRef", "Dep", "Entry",
    "Relation", "SchemaError", "ShapeIssue", "canonical_relation_name",
    "nearest_relation_name", "parse_entry",
    "CONSTITUTION_SKELETON", "cmd_init", "cmd_link", "cmd_new", "restore_bytes",
    "set_fields", "slugify",
    "ContractError", "contract_status", "get_contract",
]


def __getattr__(name: str):
    if name in _SUBMODULES:
        import importlib
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
