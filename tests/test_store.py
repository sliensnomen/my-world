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
    ("relations:\n  - type: depends_on\n    target: BAD ID\n    kind: production\n"
     "    critical: true\n", None,
     "relations[0].target='BAD ID' 不符合 id 格式"),
    # §5.4：depends_on 的 kind / critical 是必填的。这一条以前只对旧写法生效，
    # 于是规范形省掉 kind 就能让 CA501 整条静默跳过（评审 F2）。
    ("relations:\n  - type: depends_on\n    target: b-node\n    critical: true\n", None,
     "relations[0] 是 depends_on 边，缺必填字段 `kind`"),
    ("relations:\n  - type: depends_on\n    target: b-node\n    kind: production\n", None,
     "relations[0] 是 depends_on 边，缺必填字段 `critical`"),
    ("relations:\n  - type: affects\n    target: b-node\n    nope: 1\n", None,
     "relations[0] 含未定义字段 `nope`"),
    # 旧具名字段的形状错误必须**照样报 CA107**：变异实验里把 store/model.py 里
    # 具名字段那三条的 CA107 改成 CA109，六套命令全绿——因为这里只覆盖了规范形那条路。
    ("depends_on:\n  - just-a-string\n", None, "depends_on[0] 必须是对象"),
    ("depends_on:\n  - kind: resource\n", None, "depends_on[0] 缺字段 `id`"),
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
        root = make_world(Path(td), {
            "a-node": entry_text(
                "a-node", "relations:\n  - type: legitimizes\n    target: b-node\n"),
            # 目标必须真实存在：生产关系（owns/controls/... 六个）的**悬空引用**从
            # v1.1 起会报 CA401——判定层看不见写坏的引用正是这次要修的毛病一类。
            "b-node": entry_text("b-node"),
        })
        e = parsed(root, "a-node")
        assert not e.relation_errors, e.relation_errors
        assert [r.type for r in e.relations] == ["legitimizes"], e.relations
        rc, out, _ = run([root])
        assert rc == 0 and "0 错误" in out, f"未知关系名今天不下判语:\n{out}"


def check_undeclared_annotations_are_visible():
    """「缺注解」按关系族分：depends_on 的 kind/critical 是**必填**（§5.4，缺 = CA107），
    其余族今天不要求注解——那种边「还没想好」是合法状态，能查得到、不算错误。
    """
    assert store.Relation("depends_on", "x", {}).undeclared == ("kind", "critical")
    assert store.Relation("depends_on", "x",
                          {"kind": "resource", "critical": True}).undeclared == ()
    for fam in ("canon_refs", "conflicts_with", "owns", "controls"):
        assert store.Relation(fam, "x", {}).undeclared == (), fam

    with tempfile.TemporaryDirectory() as td:
        root = make_world(Path(td), {
            # 不带注解的边：canon_refs 由契约规定不带注解，所以这条是合法的
            "a-node": entry_text(
                "a-node", "relations:\n  - type: canon_refs\n    target: b-node\n"),
            "b-node": entry_text("b-node"),
        })
        e = parsed(root, "a-node")
        assert not e.relation_errors, e.relation_errors
        assert [r.target for r in e.relations] == ["b-node"], e.relations
        assert e.undeclared_annotations == []      # 这一族不要求注解
        rc, out, _ = run([root])
        assert rc == 0 and "0 错误" in out, f"不带注解的 canon_refs 边不是错误:\n{out}"


def check_mixed_forms_are_recorded():
    with tempfile.TemporaryDirectory() as td:
        root = make_world(Path(td), {"a-node": entry_text(
            "a-node", LEGACY_ALL + "relations:\n  - type: depends_on\n    target: c-node\n"
                                    "    kind: resource\n    critical: true\n")})
        e = parsed(root, "a-node")
        assert e.mixed_relation_forms, "两种写法混用必须被记录"
        assert [r.target for r in e.relations] == ["b-node", "b-node", "b-node", "c-node"], \
            "旧字段在前、relations 在后"


# ---- 6/7. 与判定侧的常量不许漂移 ------------------------------------------

def check_field_table_matches_rules():
    # 契约 x-relation-source.aliases 的九个具名字段全部接线（旧「六种待接线」漂移已关闭）
    assert set(store.FIELD_TABLE) == set(canonlint.REQUIRED_FIELDS) | {
        "layer", "superseded_by", store.RELATIONS_FIELD} \
        | set(store.LEGACY_RELATION_FIELDS), \
        "存储层的字段表与判定侧已知字段不一致——两张表必须同时改"
    assert canonlint.KNOWN_FIELDS == store.FIELD_TABLE, "CA106 的词表必须就是存储层的字段表"


def check_type_vocabulary_matches_layout():
    assert canonlint.VALID_TYPES == set(store.TYPE_DIRS), (
        f"严格档的 type 词表 {sorted(canonlint.VALID_TYPES)} "
        f"与存储布局 {sorted(store.TYPE_DIRS)} 不一致；要分开就先改这条测试")


# ---- 8. 关系名真值表：契约与工具不许有两种拼法 -----------------------------

def check_relation_alias_drift():
    """契约的九个具名字段必须**全部**接线，而契约声明的每一种拼法都必须认。

    这条测试的前身只钉「还有哪六个没接线」，于是漏掉了真正的缺陷：契约
    `x-relation-source.aliases` 把 canon_refs 的 type 写作 `canon-ref`，而工具按规范名
    精确匹配——契约自己声明的写法对判定完全隐形（整族 CA4xx 静默失效），depends_on
    却因为两边恰好同拼法而正常体检。钉数量抓不到拼法漂移，所以这里逐条钉拼法与归属。
    """
    schema = json.loads((ROOT / "world.schema.json").read_text(encoding="utf-8"))
    src = schema["x-relation-source"]
    aliases = src["aliases"]
    canonical = src["canonical"]
    assert canonical == store.RELATIONS_FIELD, (
        f"契约的规范形叫 {canonical!r}，存储层叫 {store.RELATIONS_FIELD!r}")

    # (1) 九个具名字段全部接线，一个不漏
    unconsumed = sorted(set(aliases) - set(store.LEGACY_RELATION_FIELDS))
    assert not unconsumed, (
        f"契约列了但工具没接线的关系字段：{unconsumed}——"
        f"未接线会让它们对判定隐形（CA106 未定义字段）")

    # (2) 规范名真值表：契约的 type 与工具认的规范名逐字相同，且变体互通
    names = schema["x-relation-vocabulary"]["names"]
    for field, spec in aliases.items():
        declared = spec["type"]
        assert declared in names, (
            f"契约字段 {field} 的 type={declared!r} 不在 x-relation-vocabulary.names 里")
        assert store.canonical_relation_name(declared) == declared, (
            f"契约字段 {field} 声明的 type={declared!r} 不是规范名"
            f"（工具会归一成 {store.canonical_relation_name(declared)!r}）")
        for variant in names[declared]["accept"]:
            assert store.canonical_relation_name(variant) == declared, (
                f"契约声明 {declared} 可以写作 {variant!r}，但工具归一成 "
                f"{store.canonical_relation_name(variant)!r}——判定会静默漏掉这一族")

    # (3) 存储层从契约读到的词表，就是契约里那张（修 bug 不许绕过契约另写一份）
    assert set(store.RELATION_VOCABULARY) == set(names), (
        "存储层的关系名词表与契约 x-relation-vocabulary 不是同一份")

    # (4) 每个关系名都必须有定义（means），且具名字段与词表一一对应。
    #     词表一度只有拼法没有定义：工具按名字建图、作者按直觉选词，双方对「这条边
    #     算不算承重」没有共识——depends_on 一个词同时装了「我靠它活着」与「我在说法
    #     上以它为依据」两种意思。加名字而不写定义，就是让下一个作者继续猜。
    for name, spec in names.items():
        assert str(spec.get("means") or "").strip(), (
            f"契约的关系名 {name} 没有 means（定义）——加名字必须同时说清它是什么意思")
    assert set(aliases) == set(names), (
        f"具名字段与关系名不是一一对应：字段多出 {sorted(set(aliases) - set(names))}，"
        f"词表多出 {sorted(set(names) - set(aliases))}")

    # (5) 每个关系名都必须是可写的字段。`properties` 是第三张清单（词表一张、具名字段一张、
    #     JSON Schema 的属性一张），而 `additionalProperties: false` 意味着漏一项就等于
    #     「契约允许你写这个关系，但校验器拒收」——上一轮加 exchanges_with 时正是漏在这里，
    #     因为没有夹具用它，所以没有任何测试发现。
    declared_props = set(schema["properties"])
    unwritable = sorted(set(names) - declared_props)
    assert not unwritable, (
        f"契约词表声明了但 properties 里没有的关系名：{unwritable}——"
        f"additionalProperties: false 会让用了它的世界校验失败")


def check_kind_vocabulary_has_one_truth():
    """`kind` 的类别表只能有一份：契约 x-strict-vocabulary.depends_on.kind ↔ 判定常量。

    物质依赖是本次评审里被反复问到的一句话（「物质依赖到底是什么」）。它在代码里表现为
    CA501/CA502/CA503/CA504 的门禁常量 `canonlint.KIND_INITIAL_SET`，在契约里表现为
    `x-strict-vocabulary.depends_on.kind`——两份不一致就会一边判一边不判，而且没人会发现。

    拆分 `depends_on` 之前，这里另有一张 `material-kinds`（kinds + normative）与词表互补，
    用来区分「物质依赖」和「名分依据」；现在名分是关系名，那张中介表已删除。同一条断言仍要
    守着：`kind` 的取值集合不许有两处真值。
    """
    schema = json.loads((ROOT / "world.schema.json").read_text(encoding="utf-8"))
    declared = set(schema["x-strict-vocabulary"]["depends_on.kind"])
    assert declared == set(canonlint.KIND_INITIAL_SET), (
        f"契约说 kind 可以是 {sorted(declared)}，CA501/502/503 用的却是 "
        f"{sorted(canonlint.KIND_INITIAL_SET)}")
    # 名分依据已经搬出 kind 词表——它现在是关系名，不许再作为类别出现。
    names = schema["x-relation-vocabulary"]["names"]
    assert "legitimacy" not in declared, "名分已拆成关系名，不该再留在 kind 词表里"
    assert "derives_legitimacy_from" in names, "名分依据必须作为关系名有定义"


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
    # 契约声明的关系名。名字里带理论词是历史包袱（它从 `depends_on` 的某个 kind 值搬出来），
    # 但存储在**名字**上认识它，不解释它的含义——名字由 world.schema.json 定义，理论在判定层。
    "derives_legitimacy_from",
)
THEORY_NAMES = ("LAYERS", "LAYER_INDEX", "KIND_INITIAL_SET",
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


def check_canonical_edges_are_judged():
    """规范形 `relations` 和旧具名字段必须**判定等价**：关系到不到得了人，两种写法一样判。

    这是 Codex 评审第 3 条（统一视图 `Entry.relations` 当时还没接给判定器）的回归锁：
    以前写成 `relations:` 就一条都不报、退出码 0。
    """
    canonical = ("relations:\n"
                 "  - type: depends_on\n    target: missing-node\n"
                 "    kind: resource\n    critical: true\n"
                 "  - type: canon_refs\n    target: also-missing\n"
                 "  - type: conflicts_with\n    target: third-missing\n")
    legacy = ("depends_on:\n  - id: missing-node\n    kind: resource\n    critical: true\n"
              "canon_refs:\n  - also-missing\n"
              "conflicts_with:\n  - third-missing\n")

    def judged(text):
        """只看 CA4xx/CA5xx 那些真的在读边的规则。"""
        return sorted(l.strip() for l in text.splitlines()
                      if l.strip().startswith(("[CA4", "[CA5")))

    with tempfile.TemporaryDirectory() as td:
        new_root = make_world(Path(td) / "a", {"a-node": entry_text(
            "a-node", canonical, legacy_empty=False)})
        old_root = make_world(Path(td) / "b", {"a-node": entry_text(
            "a-node", legacy, legacy_empty=False)})
        rc_new, out_new, _ = run([new_root])
        rc_old, out_old, _ = run([old_root])
        assert judged(out_new), f"规范形写法一条都没判：\n{out_new}"
        assert rc_new == rc_old == 1, (rc_new, rc_old, out_new, out_old)
        assert judged(out_new) == judged(out_old), (
            "两种写法的判定结果不一样：\n规范形：\n" + "\n".join(judged(out_new))
            + "\n旧写法：\n" + "\n".join(judged(out_old)))


def check_load_bearing_declaration_forms_agree():
    """CA302 判的是「有没有**声明**依赖」，不是「有没有边」——两种写法必须同判。

    评审实测的旧行为：`depends_on: []`（旧写法，字段在）→ rc=0，而语义相同的
    `relations: []`（规范形空表）→ CA302 error。契约 §5.3 明写「可为空列表，但字段
    必须在」，所以规范形空表也是合格的声明；而「只写了别的边、对依赖什么都没说」
    两种写法都必须报。这张表就是 §5.3 的可执行版本。
    """
    def card(extra: str) -> str:
        return (f"---\nid: a-node\ntitle: a-node\ntype: location\nauthor: t\n"
                f"date: 2026-01-01\nstatus: canon\nload_bearing: true\nlayer: geo\n"
                f"canon_refs: []\nconflicts_with: []\n{extra}ai_assisted: false\n"
                f"---\n\n{BODY}\n")

    only_other_canonical = "relations:\n  - type: conflicts_with\n    target: a-node\n"
    cases = [
        ("什么都没写", "", True),
        ("旧写法 depends_on: []", "depends_on: []\n", False),
        ("规范形 relations: []", "relations: []\n", False),
        ("规范形只有 conflicts-with（对依赖没表态）", only_other_canonical, True),
        ("旧写法只有 conflicts_with:（对依赖没表态）",
         "conflicts_with:\n  - a-node\n", True),
        ("混用：规范形放别的边 + depends_on: [] 显式声明空",
         only_other_canonical + "depends_on: []\n", False),
        ("规范形里真的有 depends_on 边",
         "relations:\n  - type: depends_on\n    target: a-node\n"
         "    kind: resource\n    critical: true\n", False),
    ]
    for label, extra, want_error in cases:
        with tempfile.TemporaryDirectory() as td:
            root = make_world(Path(td), {"a-node": card(extra)})
            rc, out, err = run([root])
            got_error = "CA302" in out
            assert got_error == want_error, (
                f"{label}：期望 CA302 {'报' if want_error else '不报'}，实际 rc={rc}\n{out}")
            assert not err, f"{label} 把 traceback 写到了 stderr：{err!r}"


def check_relation_forms_are_indistinguishable():
    """同一句话写成规范形或旧写法，退出码与规则集合必须**逐条一致**。

    这是 CONTRIBUTING §7 铁律 6（判定一致性）的可执行版本，也是评审 B1 的回归锁：
    修复前 `relations:` 里的 canon-ref / conflicts-with 对判定层完全隐形（CA401/402/
    403 静默失效），而 `depends_on` 恰好两边同拼法而正常体检——同一份契约三个族两种
    下场。修复后每个族都必须给出**同一个**答案，拼法变体（连字符/下划线）也算同族。
    """
    def card(extra: str) -> str:
        return (f"---\nid: a-node\ntitle: a-node\ntype: faction\nauthor: t\n"
                f"date: 2026-01-01\nstatus: canon\nload_bearing: true\nlayer: political\n"
                f"canon_refs: []\nconflicts_with: []\n{extra}ai_assisted: false\n"
                f"---\n\n{BODY}\n")

    def target(extra: str = "") -> str:
        return (f"---\nid: b-node\ntitle: b-node\ntype: faction\nauthor: t\n"
                f"date: 2026-01-01\nstatus: canon\nload_bearing: false\nlayer: ideology\n"
                f"canon_refs: []\nconflicts_with: []\n{extra}ai_assisted: false\n"
                f"---\n\n{BODY}\n")

    def judge(left: str, right: str = ""):
        with tempfile.TemporaryDirectory() as td:
            root = make_world(Path(td), {"a-node": card(left), "b-node": target(right)})
            rc, out, err = run([root])
            assert not err, f"stderr：{err!r}"
            rules = sorted(l.split("]")[0] + "]" for l in out.splitlines()
                           if l.startswith("["))
            return rc, rules

    pairs = [
        # 依赖边：三个必填字段齐全时两种写法同判（CA501 层级方向该报就报）
        ("depends_on 齐全",
         "relations:\n  - type: depends_on\n    target: b-node\n"
         "    kind: production\n    critical: true\n",
         "depends_on:\n  - id: b-node\n    kind: production\n    critical: true\n"),
        # §5.4 的必填字段缺一个：两种写法都必须 CA107，而不是「规范形省了 kind
        # 就整族跳过 CA501」——那正是评审 F2 的绕过口
        ("depends_on 缺 kind（§5.4 必填）",
         "relations:\n  - type: depends_on\n    target: b-node\n    critical: true\n",
         "depends_on:\n  - id: b-node\n    critical: true\n"),
        ("depends_on 缺 critical（§5.4 必填）",
         "relations:\n  - type: depends_on\n    target: b-node\n    kind: production\n",
         "depends_on:\n  - id: b-node\n    kind: production\n"),
        # 引用边：悬空目标必须报 CA401
        ("canon_refs 悬空",
         "relations:\n  - type: canon_refs\n    target: ghost\n",
         "canon_refs:\n  - ghost\n"),
        ("conflicts_with 无回指",
         "relations:\n  - type: conflicts_with\n    target: b-node\n",
         "conflicts_with:\n  - b-node\n"),
        # 拼法变体：连字符写法也是同一族，必须同判
        ("contract 拼法变体 canon-ref",
         "relations:\n  - type: canon-ref\n    target: ghost\n",
         "relations:\n  - type: canon_refs\n    target: ghost\n"),
        ("contract 拼法变体 conflicts-with",
         "relations:\n  - type: conflicts-with\n    target: b-node\n",
         "relations:\n  - type: conflicts_with\n    target: b-node\n"),
        ("contract 拼法变体 depends-on",
         "relations:\n  - type: depends-on\n    target: b-node\n"
         "    kind: production\n    critical: true\n",
         "relations:\n  - type: depends_on\n    target: b-node\n"
         "    kind: production\n    critical: true\n"),
    ]
    for label, canonical, legacy in pairs:
        rc_c, rules_c = judge(canonical)
        rc_l, rules_l = judge(legacy)
        assert (rc_c, rules_c) == (rc_l, rules_l), (
            f"{label}：两种写法判定不同\n  规范形 rc={rc_c} {rules_c}\n"
            f"  旧写法 rc={rc_l} {rules_l}")

    # F17 的「双向出错」锁：连字符拼法既不许漏判，也不许**凭空造错**。
    # 修复前 `depends-on` → 漏掉 CA501，同时冒出 CA302 + CA503（谎称作者没声明依赖），
    # 而作者明明写了 kind: production / critical: true。
    rc_typo, rules_typo = judge("relations:\n  - type: depends-on\n    target: b-node\n"
                                "    kind: production\n    critical: true\n")
    assert rc_typo == 1 and "[CA501]" in rules_typo, (
        f"连字符拼法必须和 depends_on 同判（CA501 该报就报），实际 rc={rc_typo} {rules_typo}")
    for fabricated in ("[CA302]", "[CA503]"):
        assert fabricated not in rules_typo, (
            f"连字符拼法凭空造出了 {fabricated}（作者声明是完整的），实际 {rules_typo}")
    # 真正未知的关系名今天不下判语：不能因为不认识就报层级方向错
    _, rules_junk = judge("relations:\n  - type: florb\n    target: b-node\n")
    assert "[CA501]" not in rules_junk, (
        f"未知关系名不得触发图规则（今天不下判语），实际 {rules_junk}")


def check_superseded_by_null_is_not_a_successor():
    """`superseded_by: null` = 「没有承接者」，不能拿它把 CA405 关掉（评审 F4）。

    契约把 null 定义为「无承接者」的合法写法（CA101 文案），那正是降级处置不完整的
    情形：CA402（报在引用方）与 CA405（报在目标方）必须把 null 与字段缺当成同一件事。
    修复前填一个 null 就能让 CA405 消失，而 CA402 的文案还会把 Python 的 `None`
    印进给作者看的报告里。
    """
    def archived(extra: str) -> str:
        return (f"---\nid: b-node\ntitle: b-node\ntype: location\nauthor: t\n"
                f"date: 2026-01-01\nstatus: archived\nload_bearing: false\n"
                f"canon_refs: []\nconflicts_with: []\n{extra}ai_assisted: false\n"
                f"---\n\n{BODY}\n")

    def referrer() -> str:
        return entry_text("a-node", "canon_refs:\n  - b-node\n")

    for label, extra, want in [
        ("字段缺", "", "CA405"),
        ("显式 null", "superseded_by: null\n", "CA405"),
        ("真有承接者", "superseded_by: c-node\n", "CA402"),
    ]:
        with tempfile.TemporaryDirectory() as td:
            root = make_world(Path(td), {"a-node": referrer(), "b-node": archived(extra)})
            rc, out, err = run([root])
            assert not err, f"{label} 把 traceback 写到了 stderr：{err!r}"
            assert want in out, f"{label}：期望 {want}\n{out}"
            assert "None" not in out, f"{label}：报告里印出了 Python 的 None\n{out}"
            if want == "CA402":
                assert "CA405" not in out, f"{label}：有承接者时不该报 CA405\n{out}"


def check_write_path_refuses_to_clobber():
    """写入路径的三条静默覆盖必须变成响亮的拒绝。

    评审实测：`new` 撞同路径的他人文件会静默覆盖（rc=0 且打印「已建卡」）、
    `init` 无条件吃掉既有 `.git/hooks/pre-commit`（无备份）、`link` 只按
    `depends_on:` 具名字段去重（边写在规范形 `relations:` 里时会重复插入）。
    三条都不是"判定"问题，是**数据丢失**问题，所以钉在存储层测试里。
    """
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "w"
        assert store.cmd_init(world, exe="canonlint") == 0

        # (1) new 撞路：文件里的 id 与请求的 id 不同，索引查不到，但路已被占
        squatted = world / "entries" / "locations" / "foo.md"
        squatted.parent.mkdir(parents=True, exist_ok=True)
        squatted.write_text("---\nid: bar\ntitle: 手写的\n---\n原内容\n", encoding="utf-8")
        rc, out, err = run(["new", "location", "新建", "--id", "foo", "--root", str(world)])
        assert rc == 1, f"撞路必须拒绝（rc=1），实际 rc={rc}\n{out}\n{err}"
        assert "已存在" in err, err
        assert "手写的" in squatted.read_text(encoding="utf-8"), "原有文件被吃掉了"

        # (2) init 撞钩子：覆盖前必须留备份
        world.joinpath(".git", "hooks").mkdir(parents=True, exist_ok=True)
        hook = world / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho SENTINEL\n", encoding="utf-8")
        assert store.cmd_init(world, exe="canonlint") == 0
        backup = world / ".git" / "hooks" / "pre-commit.bak"
        assert backup.exists() and "SENTINEL" in backup.read_text(encoding="utf-8"), \
            "覆盖既有 pre-commit 钩子却没留备份"

        # (3) link 按规范化后的边去重：边已经写在规范形 relations 里
        for eid, extra in (("a-node", "relations:\n  - type: depends_on\n"
                                       "    target: b-node\n    kind: fiscal\n"
                                       "    critical: true\n"),
                           ("b-node", "depends_on: []\n")):
            (world / "entries" / "factions").mkdir(parents=True, exist_ok=True)
            (world / "entries" / "factions" / f"{eid}.md").write_text(
                entry_text(eid, extra, legacy_empty=False), encoding="utf-8")
        rc, out, err = run(["link", "--kind", "fiscal", "--root", str(world), "a-node", "b-node"])
        assert rc == 0 and "边已存在" in out, f"rc={rc} out={out!r} err={err!r}"
        text = (world / "entries" / "factions" / "a-node.md").read_text(encoding="utf-8")
        assert text.count("kind: fiscal") == 1, f"同一条边被插了两次：\n{text}"


CHECKS = (
    ("规范形与旧写法等价（三种关系）", check_canonical_equals_legacy),
    ("规范形的形状错误会出现在报告里", check_shape_errors_reach_the_report),
    ("未知关系名原样保留、不下判语", check_unknown_relation_names_are_kept),
    ("规范形的边与旧写法判定等价", check_canonical_edges_are_judged),
    ("缺注解的边可查、且不算错误", check_undeclared_annotations_are_visible),
    ("两种写法混用被记录（旧字段在前）", check_mixed_forms_are_recorded),
    ("字段表与判定侧常量一致", check_field_table_matches_rules),
    ("type 词表与存储布局一致", check_type_vocabulary_matches_layout),
    ("关系别名漂移被钉住（十一个都接线 + 拼法/定义与契约逐字一致）", check_relation_alias_drift),
    ("kind 的类别表只有一份真值（契约 ↔ CA501/502/503）", check_kind_vocabulary_has_one_truth),
    ("存储层不认识理论（不 import 判定侧）", check_store_keeps_theory_out),
    ("通过符号链接调用也能 import store", check_symlink_invocation),
    ("init 装的钩子指向 canonlint（不是 store）", check_init_hook_points_at_canonlint),
    ("写入路径往返：init→new→link→--strict", check_write_path_round_trip),
    ("写入路径不静默覆盖（new 撞路 / init 钩子 / link 去重）", check_write_path_refuses_to_clobber),
    ("承重墙义务：两种写法的「声明」同判", check_load_bearing_declaration_forms_agree),
    ("关系写法不可区分（规范形/旧写法/拼法变体同判）", check_relation_forms_are_indistinguishable),
    ("superseded_by: null 不是承接者（CA405 不能被关掉）", check_superseded_by_null_is_not_a_successor),
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
