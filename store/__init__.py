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
  collect / iter_entry_paths / ENTRY_DIRS / SKIP_DIRS / TYPE_DIRS
  cmd_init / cmd_new / cmd_link / slugify / CONSTITUTION_SKELETON

改动清单与「30 分钟上手」见 store/README.md。
"""
from .layout import ENTRY_DIRS, SKIP_DIRS, TYPE_DIRS, collect, iter_entry_paths
from .model import (CANONICAL_RELATION_ITEMS, CORE_REQUIRED_FIELDS, FIELD_TABLE, ID_RE,
                    LEGACY_RELATION_FIELDS, RELATIONS_FIELD, ConflictRef, Dep, Entry,
                    Relation, SchemaError, ShapeIssue, parse_entry)
from .write import CONSTITUTION_SKELETON, cmd_init, cmd_link, cmd_new, slugify

__all__ = [
    "ENTRY_DIRS", "SKIP_DIRS", "TYPE_DIRS", "collect", "iter_entry_paths",
    "CANONICAL_RELATION_ITEMS", "CORE_REQUIRED_FIELDS", "FIELD_TABLE", "ID_RE",
    "LEGACY_RELATION_FIELDS", "RELATIONS_FIELD", "ConflictRef", "Dep", "Entry",
    "Relation", "SchemaError", "ShapeIssue", "parse_entry",
    "CONSTITUTION_SKELETON", "cmd_init", "cmd_link", "cmd_new", "slugify",
]
