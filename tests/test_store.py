#!/usr/bin/env python3
"""存储层测试（store/）——把「存储与判定分开」这条边界变成机器可查的东西。

跑：python3 tests/test_store.py

这些检查的用途不是「证明代码能跑」（那是 tests/run_tests.py 的九套世界夹具），而是
**证明边界还在**：存储层不认识理论、规范形与旧写法归一化到同一组对象、形状错误一定
报得出来、写入路径产出的文件仍然是工具能读的文件。哪一条红了，说明那条边界被破坏。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import canonlint  # noqa: E402
import store  # noqa: E402

TOOL = ROOT / "canonlint.py"
BODY = "正文" * 120  # clean_body 240 字，避开 CA104 噪声


# ---- 工具 ----------------------------------------------------------------

def run(args, cwd=None, env=None):
    p = subprocess.run([sys.executable, str(TOOL)] + [str(a) for a in args],
                       capture_output=True, text=True, cwd=str(cwd or ROOT), env=env)
    return p.returncode, p.stdout, p.stderr


def entry_text(entry_id: str, extra: str = "", legacy_empty: bool = True) -> str:
    """一张合法的最小卡片；extra 插在 frontmatter 里（用来放关系字段）。

    legacy_empty=False 时不写 `canon_refs: []` / `conflicts_with: []`——用来构造
    「只用规范形、完全不碰旧字段」的卡片（存储层测试不需要满足 CA101 的必填项）。
    """
    legacy = "canon_refs: []\nconflicts_with: []\n" if legacy_empty else ""
    return (f"---\nid: {entry_id}\ntitle: {entry_id}\ntype: location\n"
            f"author: t\ndate: 2026-01-01\nstatus: canon\nload_bearing: false\n"
            f"{legacy}{extra}ai_assisted: false\n---\n\n{BODY}\n")


def make_world(tmp: Path, entries: dict[str, str]) -> Path:
    root = tmp / "world"
    (root / "entries").mkdir(parents=True, exist_ok=True)
    for name, text in entries.items():
        (root / "entries" / f"{name}.md").write_text(text, encoding="utf-8")
    return root


def parsed(root: Path, name: str):
    return store.parse_entry(root / "entries" / f"{name}.md", root)


# ---- 1. 两种写法归一化到同一组内部对象 ------------------------------------

LEGACY_ALL = (
    "depends_on:\n  - id: b-node\n    kind: fiscal\n    critical: true\n"
    "conflicts_with:\n  - id: b-node\n    stance: official\n"
    "canon_refs:\n  - b-node\n"
)
CANONICAL_ALL = (
    "relations:\n"
    "  - type: depends_on\n    target: b-node\n    kind: fiscal\n    critical: true\n"
    "  - type: conflicts_with\n    target: b-node\n    stance: official\n"
    "  - type: canon_refs\n    target: b-node\n"
)


def check_canonical_equals_legacy():
    with tempfile.TemporaryDirectory() as td:
        root = make_world(Path(td), {"legacy": entry_text("a-node", LEGACY_ALL),
                                     "canonical": entry_text("a-node", CANONICAL_ALL,
                                                             legacy_empty=False)})
        legacy, canonical = parsed(root, "legacy"), parsed(root, "canonical")
        assert legacy.uses_legacy_relations and not legacy.uses_canonical_relations
        assert canonical.uses_canonical_relations and not canonical.uses_legacy_relations
        assert not legacy.relation_errors and not canonical.relation_errors
        assert legacy.relations == canonical.relations, (
            f"两种写法应归一化到同一组边\n legacy={legacy.relations}\n canonical={canonical.relations}")
        assert [(r.type, r.target) for r in legacy.relations] == [
            ("depends_on", "b-node"), ("conflicts_with", "b-node"), ("canon_refs", "b-node")]
        dep = legacy.relations[0]
        assert (dep.kind, dep.critical, dep.undeclared) == ("fiscal", True, ())
        assert canonical.relations[0].attrs.get("critical") is True


# ---- 2. 规范形的形状错误必须报出来（不能被静默丢掉）------------------------

SHAPE_CASES = (
    ("relations: notalist\n", None, "relations 必须是列表"),
    ("relations:\n  - just-a-string\n", None, "relations[0] 必须是对象"),
    ("relations:\n  - type: depends_on\n", None, "relations[0] 缺字段 `target`"),
    ("relations:\n  - type: depends_on\n    target: b-node\n    kind: 3\n", None,
     "relations[0].kind 必须是字符串"),
    ("relations:\n  - type: depends_on\n    target: BAD ID\n", None,
     "relations[0].target='BAD ID' 不符合 id 格式"),
    ("relations:\n  - type: affects\n    target: b-node\n    nope: 1\n", None,
     "relations[0] 含未定义字段 `nope`"),
)


def check_shape_errors_reach_the_report():
    for extra, _level, want in SHAPE_CASES:
        with tempfile.TemporaryDirectory() as td:
            root = make_world(Path(td), {"a-node": entry_text("a-node", extra)})
            rc, out, err = run([root])
            assert not err, f"stderr 不该有内容: {err!r}"
            assert want in out, f"应报 {want!r}\n实际输出:\n{out}"
            assert rc == 1, f"形状错误必须算 error（exit 1），实际 exit={rc}"


# ---- 3/4/5. 存储层如实记录，不替判定器下结论 -------------------------------

def check_unknown_relation_names_are_kept():
    with tempfile.TemporaryDirectory() as td:
        root = make_world(Path(td), {"a-node": entry_text(
            "a-node", "relations:\n  - type: legitimizes\n    target: b-node\n")})
        e = parsed(root, "a-node")
        assert not e.relation_errors, e.relation_errors
        assert [r.type for r in e.relations] == ["legitimizes"], e.relations
        rc, out, _ = run([root])
        assert rc == 0 and "0 错误" in out, f"未知关系名今天不下判语:\n{out}"


def check_undeclared_annotations_are_visible():
    with tempfile.TemporaryDirectory() as td:
        root = make_world(Path(td), {"a-node": entry_text(
            "a-node", "relations:\n  - type: depends_on\n    target: b-node\n")})
        e = parsed(root, "a-node")
        assert e.undeclared_annotations and e.undeclared_annotations[0].undeclared == (
            "kind", "critical"), e.undeclared_annotations
        assert not e.relation_errors, e.relation_errors
        rc, out, _ = run([root])
        assert rc == 0 and "0 错误" in out, f"「还没想好」不是错误:\n{out}"


def check_mixed_forms_are_recorded():
    with tempfile.TemporaryDirectory() as td:
        root = make_world(Path(td), {"a-node": entry_text(
            "a-node", LEGACY_ALL + "relations:\n  - type: depends_on\n    target: c-node\n")})
        e = parsed(root, "a-node")
        assert e.mixed_relation_forms, "两种写法混用必须被记录"
        assert [r.target for r in e.relations] == ["b-node", "b-node", "b-node", "c-node"], \
            "旧字段在前、relations 在后"


# ---- 6/7. 与判定侧的常量不许漂移 ------------------------------------------

def check_field_table_matches_rules():
    assert set(store.FIELD_TABLE) == set(canonlint.REQUIRED_FIELDS) | {
        "layer", "depends_on", "superseded_by", store.RELATIONS_FIELD}, \
        "存储层的字段表与判定侧已知字段不一致——两张表必须同时改"
    assert canonlint.KNOWN_FIELDS == store.FIELD_TABLE, "CA106 的词表必须就是存储层的字段表"


def check_type_vocabulary_matches_layout():
    assert canonlint.VALID_TYPES == set(store.TYPE_DIRS), (
        f"严格档的 type 词表 {sorted(canonlint.VALID_TYPES)} "
        f"与存储布局 {sorted(store.TYPE_DIRS)} 不一致；要分开就先改这条测试")


# ---- 8. 已知漂移：九个关系别名，今天只读三种 -------------------------------

def check_relation_alias_drift():
    schema = json.loads((ROOT / "world.schema.json").read_text(encoding="utf-8"))
    aliases = set(schema["x-relation-source"]["aliases"])
    canonical = schema["x-relation-source"]["canonical"]
    assert canonical == store.RELATIONS_FIELD, (
        f"契约的规范形叫 {canonical!r}，存储层叫 {store.RELATIONS_FIELD!r}")
    missing = set(store.LEGACY_RELATION_FIELDS) - aliases
    assert not missing, f"工具已经在读 {sorted(missing)}，契约却没把它们列为来源"
    unconsumed = sorted(aliases - set(store.LEGACY_RELATION_FIELDS))
    assert unconsumed == ["coerces", "controls", "extracts", "legitimizes", "owes", "owns"], (
        f"未接线的关系别名变了：{unconsumed}；若你在收口漂移，请同时更新本测试")
    leaked = sorted(a for a in unconsumed if a in store.FIELD_TABLE)
    assert not leaked, f"{leaked} 已进字段表，但它们还没有判定器接上——收口时请一并处理"


# ---- 9. 存储层不认识理论 ---------------------------------------------------

FORBIDDEN = ("geo", "resource", "production", "economy", "fiscal", "military",
             "political", "ideology", "manpower", "legitimacy",
             "承重墙", "盲区", "政治经济学", "合法性闭环", "层级方向")
# 允许出现理论词的既有提示语：它们是**已经发出去的老输出**，改动等于改行为。
# 新增的理论措辞必须走判定层，不许住在 store/。
ALLOWED_SNIPPETS = (
    "承重墙条目？[y/N]",            # cmd_new 的交互提示
    "承重墙条目必须给 layer",       # cmd_new 的错误提示
    "--kind fiscal 连线",          # cmd_new 打印的连线示例
    "层级方向/环/状态",             # cmd_link 打印的收尾提示
)
THEORY_NAMES = ("LAYERS", "LAYER_INDEX", "KIND_INITIAL_SET", "MATERIAL_KINDS",
                "CA503_LAYERS", "CA505_TRIGGER_LAYERS", "LOAD_BEARING_KEYWORDS",
                "MIN_BODY_CHARS", "MIN_DUP_CHARS", "VALID_STATUS", "VALID_STANCE")


def check_store_keeps_theory_out():
    for path in sorted((ROOT / "store").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        # (a) 不许 import 判定侧（不许出现环）
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                assert m.split(".")[0] not in ("canonlint", "classlint", "econ"), \
                    f"{path.name} import 了判定侧模块 {m}"
        # (b) 不许出现理论常量名
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        hit = sorted(names & set(THEORY_NAMES))
        assert not hit, f"{path.name} 里出现了理论常量 {hit}"
        # (c) 理论词只许出现在允许的既有提示语里（docstring 不算逻辑，跳过）
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstrings:
                seg = ast.get_source_segment(src, node) or ""
                for term in FORBIDDEN:
                    if term in seg and not any(s in seg for s in ALLOWED_SNIPPETS):
                        raise AssertionError(
                            f"{path.name} 的新字符串里出现理论词 {term!r}：{seg.strip()}\n"
                            "（存储层不许替判定器表达理论；老提示语见 ALLOWED_SNIPPETS）")


# ---- 10. 通过符号链接调用（~/.local/bin/canonlint 的真实形态）--------------

def check_symlink_invocation():
    with tempfile.TemporaryDirectory() as td:
        link = Path(td) / "canonlint"
        link.symlink_to(TOOL)
        p = subprocess.run([sys.executable, str(link), str(ROOT / "tests" / "world-clean")],
                           capture_output=True, text=True, cwd=td)
        assert p.returncode == 0, f"符号链接调用失败（import store 找不到？）\n{p.stderr}"
        assert "0 错误" in p.stdout, p.stdout
        assert not p.stderr, p.stderr


# ---- 11/12. 写入侧：钩子指向谁、产出的文件还能不能读 -----------------------

def check_init_hook_points_at_canonlint():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fakebin = tmp / "bin"
        fakebin.mkdir()
        fake = fakebin / "canonlint"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
        world = tmp / "w"
        (world / ".git").mkdir(parents=True)  # 伪装成 git 仓库
        import os
        rc, out, err = run(["init", str(world)], env={**os.environ, "PATH": str(fakebin)})
        assert rc == 0, f"init 失败: {out} {err}"
        hook = world / ".git" / "hooks" / "pre-commit"
        assert hook.is_file(), "pre-commit 钩子没装上"
        text = hook.read_text(encoding="utf-8")
        assert str(fake) in text, f"钩子应指向 PATH 上的 canonlint（{fake}），实际：{text!r}"
        assert "write.py" not in text, \
            f"钩子指向了存储层自己（Path(__file__) 陷阱）：{text!r}"
        assert (world / "CONSTITUTION.md").is_file()
        assert (world / "entries" / "locations").is_dir()


def check_write_path_round_trip():
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "w"
        rc, out, err = run(["init", str(world)])
        assert rc == 0, f"{out} {err}"
        rc, out, err = run(["new", "location", "灰港", "--id", "grey-harbor",
                            "--root", str(world)])
        assert rc == 0, f"{out} {err}"
        card = world / "entries" / "locations" / "grey-harbor.md"
        assert card.is_file(), f"新建的卡不在约定的位置：{sorted(p.name for p in world.rglob('*.md'))}"
        rc, out, err = run(["new", "faction", "王都", "--id", "crown-capital",
                            "--root", str(world)])
        assert rc == 0, f"{out} {err}"
        rc, out, err = run(["link", "grey-harbor", "crown-capital", "--kind", "fiscal",
                            "--critical", "--root", str(world)])
        assert rc == 0, f"{out} {err}"
        text = card.read_text(encoding="utf-8")
        assert "  - id: crown-capital" in text and "kind: fiscal" in text \
            and "critical: true" in text, text
        rc, out, err = run([world, "--strict"])
        assert rc == 0, f"写入路径产出的世界在 --strict 下必须干净：\n{out}"
        # 承重墙（load_bearing）必须有 layer；词表由判定侧提供，存储层只照收
        rc, out, err = run(["new", "location", "无层", "--id", "no-layer",
                            "--load-bearing", "--root", str(world)])
        assert rc == 2 and "承重墙条目必须给 layer" in err, f"rc={rc} out={out!r} err={err!r}"


CHECKS = (
    ("规范形与旧写法等价（三种关系）", check_canonical_equals_legacy),
    ("规范形的形状错误会出现在报告里", check_shape_errors_reach_the_report),
    ("未知关系名原样保留、不下判语", check_unknown_relation_names_are_kept),
    ("缺注解的边可查、且不算错误", check_undeclared_annotations_are_visible),
    ("两种写法混用被记录（旧字段在前）", check_mixed_forms_are_recorded),
    ("字段表与判定侧常量一致", check_field_table_matches_rules),
    ("type 词表与存储布局一致", check_type_vocabulary_matches_layout),
    ("关系别名漂移被钉住（六种待接线）", check_relation_alias_drift),
    ("存储层不认识理论（不 import 判定侧）", check_store_keeps_theory_out),
    ("通过符号链接调用也能 import store", check_symlink_invocation),
    ("init 装的钩子指向 canonlint（不是 store）", check_init_hook_points_at_canonlint),
    ("写入路径往返：init→new→link→--strict", check_write_path_round_trip),
)


def main() -> int:
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
        except AssertionError as e:
            print(f"FAIL {name}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001 —— 任何异常都是失败，不能逃逸成 traceback
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            failed += 1
        else:
            print(f"PASS {name}")
    total = len(CHECKS)
    if failed:
        print(f"\n{total} 项检查 | {failed} 项失败")
        return 1
    print(f"\n{total} 项检查 | 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
