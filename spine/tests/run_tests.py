#!/usr/bin/env python3
"""spine（事件脊柱，协议 2.0）的骨架回归网。

三组锁：
1. 契约自检——event.schema.json 的机器可读行为（好样本过、坏样本红）；
2. 依赖方向 AST 锁——宪章 §4 的机器执行：1.x 不得 import spine；
   spine 顶层模块除 migrate.py（只许读 store）不得 import 1.x 模块；
3. 迁移对账——tests/world-ledger 迁到临时账本：事件卡逐张直译、断言转期初、
   产出全部过契约、源世界一个字节不动。

与 1.x 的六套平行运行；切换日之前两边的网都必须绿。
用法: python3 spine/tests/run_tests.py    退出码: 0=全绿 1=有偏差
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCHEMA_PATH = ROOT / "spine" / "event.schema.json"
MIGRATE = ROOT / "spine" / "migrate.py"
PY = sys.executable

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
DEFS = SCHEMA.get("$defs", {})


# ---- 契约最小校验器（骨架级：只实现 event.schema.json 用到的子集） -------------

def _resolve(ref: str) -> dict:
    assert ref.startswith("#/$defs/"), f"不支持的 $ref：{ref}"
    return DEFS[ref.split("/", 2)[2]]


def _check_value(value, spec: dict, path: str) -> list[str]:
    if "$ref" in spec:
        spec = _resolve(spec["$ref"])
    errors = []
    t = spec.get("type")
    if t == "string" and not isinstance(value, str):
        errors.append(f"{path} 必须是字符串")
    elif t == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        errors.append(f"{path} 必须是数字")
    elif t == "array":
        if not isinstance(value, list):
            errors.append(f"{path} 必须是数组")
        else:
            for i, item in enumerate(value):
                errors += _check_value(item, spec.get("items", {}), f"{path}[{i}]")
    if "pattern" in spec and isinstance(value, str) and not re.match(spec["pattern"], value):
        errors.append(f"{path}={value!r} 不符合 {spec['pattern']}")
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}={value!r} 不在 {spec['enum']}")
    if "minimum" in spec and isinstance(value, (int, float)) and value < spec["minimum"]:
        errors.append(f"{path}={value} 小于 minimum {spec['minimum']}")
    if "maximum" in spec and isinstance(value, (int, float)) and value > spec["maximum"]:
        errors.append(f"{path}={value} 大于 maximum {spec['maximum']}")
    return errors


def validate_event(meta) -> list[str]:
    """按契约校验一个事件的 frontmatter（已解析为 dict）。"""
    if not isinstance(meta, dict):
        return ["frontmatter 必须是键值映射"]
    errors = []
    props = SCHEMA.get("properties", {})
    patterns = [re.compile(p) for p in SCHEMA.get("patternProperties", {})]
    if SCHEMA.get("additionalProperties") is False:
        for key in meta:
            if key in props or any(p.match(key) for p in patterns):
                continue
            errors.append(f"未定义字段 `{key}`")
    for req in SCHEMA.get("required", []):
        if req not in meta:
            errors.append(f"缺少必填字段 `{req}`")
    for key, value in meta.items():
        if key in props:
            errors += _check_value(value, props[key], key)
    return errors


def _read_event(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}


# ---- 1. 契约自检 -------------------------------------------------------------

def check_contract_accepts_good_samples() -> list[str]:
    good = [
        {"id": "ev-1", "type": "transfer"},
        {"id": "ev-2", "type": "x-transfer", "by": ["anna"], "to": ["bob"],
         "object": ["sword-x"], "when": "元年", "when_sort": 1,
         "source": "第一部 第三章 第2段", "evidence": "inferred",
         "confirmed_by": "anker", "confirmed_at": "2026-11-23",
         "x-extract-confidence": 0.42, "x-custom-note": "自由扩展"},
    ]
    problems = []
    for i, meta in enumerate(good):
        errs = validate_event(meta)
        if errs:
            problems.append(f"好样本 {i} 被误拒：{errs}")
    return problems


def check_contract_rejects_bad_samples() -> list[str]:
    bad = [
        ({"type": "transfer"}, "缺 id"),
        ({"id": "Bad_Id", "type": "transfer"}, "id 非法字符"),
        ({"id": "ev-1", "type": "transfer", "title": "多出来的字段"}, "未定义字段"),
        ({"id": "ev-1", "type": "transfer", "evidence": "guessed"}, "evidence 枚举外"),
        ({"id": "ev-1", "type": "transfer", "by": "anna"}, "腿不是数组"),
        ({"id": "ev-1", "type": "transfer", "by": ["Bad Id"]}, "腿元素 id 非法"),
        ({"id": "ev-1", "type": "transfer", "x-extract-confidence": 1.5}, "置信度越界"),
        ({"id": "ev-1", "type": "transfer", "when_sort": "元年"}, "when_sort 非数字"),
    ]
    problems = []
    for meta, label in bad:
        errs = validate_event(meta)
        if not errs:
            problems.append(f"坏样本（{label}）被静默放过：{meta}")
    return problems


def check_contract_meta() -> list[str]:
    problems = []
    if SCHEMA.get("x-contract-version") != "0.1":
        problems.append(f"x-contract-version 应为 0.1，实际 {SCHEMA.get('x-contract-version')!r}")
    if SCHEMA.get("required") != ["id", "type"]:
        problems.append(f"必填表应为 ['id', 'type']，实际 {SCHEMA.get('required')!r}")
    if SCHEMA.get("additionalProperties") is not False:
        problems.append("additionalProperties 必须为 false（x- 由 patternProperties 放行）")
    return problems


# ---- 2. 依赖方向 AST 锁 -------------------------------------------------------

_LEGACY_ROOTS = ("canonlint.py", "serve.py", "econ.py", "ledger.py")
_LEGACY_DIRS = ("store", "judges", "classlint", "tests")
_BANNED_FOR_SPINE = {"store", "judges", "canonlint", "econ", "ledger", "serve", "classlint"}


def _imported_modules(tree) -> list[str]:
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def _scan_dependency_direction(legacy_files, spine_files) -> list[str]:
    problems = []
    for f in legacy_files:
        for mod in _imported_modules(ast.parse(f.read_text(encoding="utf-8"))):
            top = mod.split(".")[0]
            if top == "spine":
                problems.append(f"1.x 文件 {_display(f)} import 了 {mod}")
    for f in spine_files:
        allowed = {"store"} if f.name == "migrate.py" else set()
        for mod in _imported_modules(ast.parse(f.read_text(encoding="utf-8"))):
            top = mod.split(".")[0]
            if top in _BANNED_FOR_SPINE and top not in allowed:
                problems.append(f"spine 模块 {f.name} import 了 1.x 模块 {mod}")
    return problems


def check_dependency_direction_lock() -> list[str]:
    legacy = [ROOT / name for name in _LEGACY_ROOTS]
    for d in _LEGACY_DIRS:
        legacy += sorted((ROOT / d).rglob("*.py"))
    spine_top = sorted((ROOT / "spine").glob("*.py"))  # 只锁运行时模块；tests/ 是测试基建
    problems = _scan_dependency_direction(legacy, spine_top)
    # 守卫自证：合成一个越界 import，锁必须报警（锁死了等于没有锁）
    td = Path(tempfile.mkdtemp())
    try:
        bad_legacy = td / "fake_legacy.py"
        bad_legacy.write_text("import spine.migrate\n", encoding="utf-8")
        bad_spine = td / "fake_spine.py"
        bad_spine.write_text("import judges.ca.ledger\n", encoding="utf-8")
        if not _scan_dependency_direction([bad_legacy], [bad_spine]):
            problems.append("依赖方向锁对合成的越界 import 没有报警（锁失效）")
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return problems


# ---- 3. 迁移对账 ---------------------------------------------------------------

def _fixture_counts(world: Path) -> tuple[int, int]:
    """数夹具里 type:event 卡的张数与实体卡断言的条数（迁移产出的期望值）。"""
    events, assertions = 0, 0
    for card in sorted((world / "entries").rglob("*.md")):
        meta = _read_event(card)
        if not isinstance(meta, dict):
            continue
        if meta.get("type") == "event":
            events += 1
        else:
            for field in ("owns", "custody_of", "member_of"):
                if isinstance(meta.get(field), list):
                    assertions += len(meta[field])
    return events, assertions


def check_migrate_world_ledger() -> list[str]:
    world = ROOT / "tests" / "world-ledger"
    expected_events, expected_imports = _fixture_counts(world)
    before = {p.relative_to(world): p.read_bytes()
              for p in sorted(world.rglob("*")) if p.is_file()}
    problems = []
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "ledger"
        p = subprocess.run([PY, str(MIGRATE), str(world), str(out)],
                           cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0 or p.stderr:
            problems.append(f"迁移工具异常：exit={p.returncode} stderr={p.stderr!r}")
            return problems
        files = sorted((out / "events").glob("*.md"))
        real = [f for f in files if _read_event(f).get("type") != "import"]
        initial = [f for f in files if _read_event(f).get("type") == "import"]
        if len(real) != expected_events:
            problems.append(f"事件卡直译数不符：期望 {expected_events}，实际 {len(real)}")
        if len(initial) != expected_imports:
            problems.append(f"期初建台数不符：期望 {expected_imports}，实际 {len(initial)}")
        for f in files:
            errs = validate_event(_read_event(f))
            if errs:
                problems.append(f"产出 {f.name} 不过契约：{errs}")
        for f in initial:
            meta = _read_event(f)
            if meta.get("source") != "import" or "x-import-kind" not in meta:
                problems.append(f"期初事件 {f.name} 缺 source/x-import-kind 标记：{meta}")
    after = {p.relative_to(world): p.read_bytes()
             for p in sorted(world.rglob("*")) if p.is_file()}
    if before != after:
        problems.append("迁移工具改动了源世界（只读纪律被破坏）")
    return problems


CHECKS = [
    ("契约收好样本", check_contract_accepts_good_samples),
    ("契约拒坏样本", check_contract_rejects_bad_samples),
    ("契约元信息（版本/必填/封闭性）", check_contract_meta),
    ("依赖方向 AST 锁（含锁的自证）", check_dependency_direction_lock),
    ("迁移对账：world-ledger 直译 + 期初 + 只读", check_migrate_world_ledger),
]


def main() -> int:
    failures = []
    for label, check in CHECKS:
        problems = check()
        if problems:
            failures.extend(problems)
            print(f"FAIL {label}")
            for p in problems:
                print(f"     {p}")
        else:
            print(f"PASS {label}")
    print()
    if failures:
        print(f"{len(CHECKS)} 项检查 | {len(failures)} 项失败")
        return 1
    print(f"{len(CHECKS)} 项检查 | 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
