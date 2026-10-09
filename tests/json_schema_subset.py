"""手写的 JSON Schema 子集校验器 —— 只为 world.schema.json 服务，不引任何新依赖。

为什么手写：这个仓库的原则是「零安装也能跑」（CI 里只装 pyyaml）。引入
jsonschema 会让契约的验证依赖一个第三方包，而契约本身必须是最容易跑起来的东西。

只有一条铁律：**不认识的关键字一律报错**（`UnsupportedKeyword`）。
如果校验器默默跳过看不懂的约束，契约就可以悄悄长出「看起来被约束、其实没人检查」
的部分——那正是这个项目一直在犯的病（散文说已冻结、代码说不是）。
所以：schema 里出现任何本文件没实现的关键字，校验器直接拒绝，
而不是「宽容地忽略」，逼着契约和校验器一起长大。
"""

from __future__ import annotations

import re

# 本校验器真正实现了的关键字。x- 开头的是我们自己的注释性扩展，一律允许。
SUPPORTED = {
    # 结构
    "$schema", "$id", "$defs", "$ref",
    "title", "description",
    # 类型与对象
    "type", "properties", "patternProperties", "additionalProperties", "required",
    # 数组
    "items", "minItems", "maxItems", "uniqueItems",
    # 取值
    "enum", "const",
    # 逻辑
    "oneOf", "anyOf", "allOf", "not",
    # 字符串
    "pattern", "minLength", "maxLength",
}


class UnsupportedKeyword(Exception):
    """schema 里出现了校验器看不懂的关键字（契约长过了校验器）。"""


class ValidationError(Exception):
    """实例不符合 schema。"""


def _type_ok(value, t: str) -> bool:
    # 注意顺序：Python 里 bool 是 int 的子类，必须先判 bool。
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    raise UnsupportedKeyword(f"未知 type: {t!r}")


def check_schema_supported(schema, root=None, path: str = "$") -> None:
    """遍历 schema 本体，任何没实现的关键字都报错。"""
    if root is None:
        root = schema
    if not isinstance(schema, dict):
        return
    for key in schema:
        if key.startswith("x-"):
            continue
        if key not in SUPPORTED:
            raise UnsupportedKeyword(f"{path} 使用了校验器不支持的关键字 `{key}`")
    for key, value in schema.items():
        if key == "$defs":
            for name, sub in value.items():
                check_schema_supported(sub, root, f"{path}.$defs.{name}")
        elif key in ("properties", "patternProperties"):
            for name, sub in value.items():
                check_schema_supported(sub, root, f"{path}.{key}.{name}")
        elif key in ("items", "additionalProperties", "not"):
            check_schema_supported(value, root, f"{path}.{key}")
        elif key in ("oneOf", "anyOf", "allOf"):
            for i, sub in enumerate(value):
                check_schema_supported(sub, root, f"{path}.{key}[{i}]")


def _resolve(ref: str, root):
    """只支持 `#/$defs/<name>` 这一种 $ref 形式：够用，且容易人工审查。"""
    if not ref.startswith("#/"):
        raise UnsupportedKeyword(f"只支持 #/ 开头的 $ref，得到 {ref!r}")
    node = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise UnsupportedKeyword(f"$ref 指向不存在的节点: {ref!r}")
        node = node[part]
    return node


def _validate(instance, schema, root, path: str, out: list[str]) -> None:
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        _validate(instance, _resolve(schema["$ref"], root), root, path, out)
        return

    if "type" in schema:
        types = schema["type"]
        types = [types] if isinstance(types, str) else types
        if not any(_type_ok(instance, t) for t in types):
            out.append(f"{path}: 类型应为 {'/'.join(types)}，得到 {type(instance).__name__}")

    if "enum" in schema and not any(instance == v and type(instance) is type(v)
                                    for v in schema["enum"]):
        out.append(f"{path}: 取值必须在 {schema['enum']!r} 内，得到 {instance!r}")

    if "const" in schema and not (instance == schema["const"]
                                  and type(instance) is type(schema["const"])):
        out.append(f"{path}: 取值必须恰为 {schema['const']!r}，得到 {instance!r}")

    if "oneOf" in schema:
        branch_problems = []
        for sub in schema["oneOf"]:
            sub_out: list[str] = []
            _validate(instance, sub, root, path, sub_out)
            branch_problems.append(sub_out)
        hits = [i for i, problems in enumerate(branch_problems) if not problems]
        if len(hits) != 1:
            out.append(f"{path}: 必须恰好满足 oneOf 中的一个分支，实际满足 {hits}")
            # 一个都不满足时把各分支的问题贴出来，否则报错无法定位到字段
            if not hits:
                for problems in branch_problems:
                    for msg in problems:
                        if msg not in out:
                            out.append(msg)

    if "anyOf" in schema:
        if not any(_branch_ok(instance, sub, root, path) for sub in schema["anyOf"]):
            out.append(f"{path}: 必须满足 anyOf 中的至少一个分支")

    if "allOf" in schema:
        for sub in schema["allOf"]:
            _validate(instance, sub, root, path, out)

    if "not" in schema and _branch_ok(instance, schema["not"], root, path):
        out.append(f"{path}: 命中了 not 分支")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            out.append(f"{path}: 长度 {len(instance)} < minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            out.append(f"{path}: 长度 {len(instance)} > maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            out.append(f"{path}: {instance!r} 不匹配 ^[a-z0-9-]+$ 形式的 {schema['pattern']!r}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            out.append(f"{path}: 元素数 {len(instance)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            out.append(f"{path}: 元素数 {len(instance)} > maxItems {schema['maxItems']}")
        if schema.get("uniqueItems") and len(instance) != len(_unique(instance)):
            out.append(f"{path}: 元素必须互不相同")
        if "items" in schema:
            for i, item in enumerate(instance):
                _validate(item, schema["items"], root, f"{path}[{i}]", out)

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        for name in schema.get("required", []):
            if name not in instance:
                out.append(f"{path}: 缺少必填字段 `{name}`")
        for key, value in instance.items():
            matched = False
            if key in props:
                _validate(value, props[key], root, f"{path}.{key}", out)
                matched = True
            for pattern, sub in patterns.items():
                if re.search(pattern, key):
                    _validate(value, sub, root, f"{path}.{key}", out)
                    matched = True
            if matched:
                continue
            if "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    out.append(f"{path}.{key}: 未定义字段 `{key}`（扩展字段须 x- 前缀）")
                elif isinstance(extra, dict):
                    _validate(value, extra, root, f"{path}.{key}", out)


def _branch_ok(instance, schema, root, path: str) -> bool:
    probe: list[str] = []
    _validate(instance, schema, root, path, probe)
    return not probe


def _unique(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def validate(instance, schema) -> list[str]:
    """返回违反项列表（空 = 通过）。任何不支持的关键字都会抛 UnsupportedKeyword。"""
    check_schema_supported(schema)
    out: list[str] = []
    _validate(instance, schema, schema, "$", out)
    return out


def validate_or_raise(instance, schema) -> None:
    problems = validate(instance, schema)
    if problems:
        raise ValidationError("\n".join(problems))
