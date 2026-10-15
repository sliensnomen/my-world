#!/usr/bin/env python3
"""classlint fixture 测试：tests/<世界>/ 每个目录是一个世界仓库，EXPECTED 钉死期望判定。

用法: python3 tests/run_tests.py   （在 classlint/ 目录内或任意位置均可）
退出码: 0=全部符合期望 1=有偏差
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import classlint  # noqa: E402

TESTS = Path(__file__).resolve().parent

# 期望判定：(规则编号, 级别, 条目路径)。空列表 = 全绿。
EXPECTED: dict[str, list[tuple[str, str, str]]] = {
    "pe001-bad": [
        ("PE001", "error", "codex/lord.md"),
    ],
    "pe001-ok": [],
    "pe002-bad": [
        ("PE002", "error", "codex/guild.md"),      # critical 供养者被镇压
        ("PE002", "warning", "codex/pirates.md"),  # 非 critical 降级为 warning
    ],
    "pe002-ok": [],
    "pe003-bad": [
        ("PE003", "error", "codex/king.md"),       # king↔pope 无锚闭环（报在最小 id 侧）
        ("PE003", "error", "codex/prophet.md"),    # 自环
    ],
    "pe003-ok": [],  # king↔pope 互锁但有 tradition 外部锚点，合法
    # 同一结构的**规范形**写法（derive 方向反过来）：名分依据是关系名，不再是 kind 值
    "legit-canonical-ok": [],
    "legit-canonical-bad": [
        ("PE003", "error", "codex/king.md"),  # 无锚闭环，报在最小 id 侧
    ],
    "clean": [],
    # 真实作品 dogfood：结构自洽的世界应当零误报（真阴性回归锁）
    "world-westeros": [],
    # 真实作品 dogfood：帝位↔CHOAM 合法性闭环无锚（真阳性回归锁）
    "world-arrakis": [
        ("PE003", "error", "codex/choam.md"),
    ],
    "pe004-bad": [
        ("PE004", "error", "codex/chapter.md"),  # chapter↔collegium 互抽，报在最小 id 侧
    ],
    "pe005-bad": [
        ("PE005", "warning", "codex/tenant-farmers.md"),  # 佃农再生产不可见，报在被抽取者侧
    ],
    # 三个经典结构：正确的参考结构应当全绿
    "feudal-rent": [],
    "merchant-capital": [],
    "state-redistribution": [],
    "structure-bad": [
        ("CL101", "error", "codex/no-title.md"),
        ("CL102", "error", "codex/dup-b.md"),
        ("CL103", "error", "codex/bad-field.md"),
        ("CL104", "error", "codex/bad-rel.md"),  # extracts 元素缺 id
        ("CL104", "error", "codex/bad-rel.md"),  # controls 非列表
        ("CL104", "error", "codex/bad-rel.md"),  # critical 非 bool
        ("CL105", "error", "codex/dangling.md"),
    ],
}


def check_cl100_intent() -> int:
    """CL100（文件读不出来）必须有**意图断言**，不能只靠夹具碰巧覆盖。

    变异实验：把 `classlint.py` 里发 CL100 的那一处改成永不发射，15 个夹具世界全绿
    ——因为没有一个夹具里有读不出来的文件。这条断言直接构造那个形态。
    """
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: probe\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        (world / "codex" / "bad.md").write_bytes(b"---\nid: bad\ntitle: \xff\xfe\n---\n\xff\n")
        _, _, findings, _ = classlint.run_checks(world)
        got = [(f.rule, f.level, f.entry) for f in findings]
        if not any(r == "CL100" and lv == "error" and e == "codex/bad.md"
                   for r, lv, e in got):
            print(f"FAIL CL100 意图断言：读不出来的文件没报 CL100，实际 {sorted(got)}")
            failures += 1
        else:
            print("PASS CL100 意图断言（读不出来的文件必须报 CL100）")
    return failures


def _probe_world(td: str, tenant_extra: str, rules: str = "") -> Path:
    world = Path(td)
    (world / "codex").mkdir(parents=True, exist_ok=True)
    (world / "classlint.yaml").write_text(
        "name: probe\nclasslint: \"0.1\"\n" + rules, encoding="utf-8")
    (world / "codex" / "lord.md").write_text(
        "---\nid: lord\ntitle: 地主\ntype: faction\ncontrols: [tenant]\nextracts:\n"
        "  - id: tenant\n    what: 地租\n---\n抽取地租。\n", encoding="utf-8")
    (world / "codex" / "tenant.md").write_text(
        f"---\nid: tenant\ntitle: 佃农\ntype: faction\n{tenant_extra}---\n佃农。\n",
        encoding="utf-8")
    (world / "codex" / "weather.md").write_text(
        "---\nid: weather\ntitle: 天气\ntype: location\n---\n天气。\n", encoding="utf-8")
    return world


def check_pe005_requires_material_source() -> int:
    """PE005 的消音必须是一次**物质关系**的声明，不能靠一条任意出边（评审 ③-b）。

    以前 `depends_on: [weather]` 一行就能让「被抽取者的再生产不可见」消失——自然条件
    既不是生产关系也不承担再生产，消音门槛低到等于没有门槛。这里的形态就是那条边界：
    裸 depends_on 不消音，带物质 kind 的 depends_on 消音，exchanges_with 消音。
    """
    failures = 0
    cases = [
        ("裸 depends_on（无 kind）", "depends_on:\n  - weather\n", True),
        ("带物质 kind 的 depends_on", "depends_on:\n  - id: weather\n    kind: resource\n", False),
        ("exchanges_with（交换=别人也在给我）", "exchanges_with:\n  - weather\n", False),
        ("规范形 relations + 物质 kind",
         "relations:\n  - {type: depends_on, target: weather, kind: resource, critical: true}\n", False),
        ("规范形 relations（裸 depends_on，无 kind）",
         "relations:\n  - {type: depends_on, target: weather}\n", True),
    ]
    for label, extra, should_report in cases:
        with tempfile.TemporaryDirectory() as td:
            world = _probe_world(td, extra)
            _, _, findings, _ = classlint.run_checks(world)
            got = any(f.rule == "PE005" and f.entry == "codex/tenant.md" for f in findings)
            if got != should_report:
                want = "应当报" if should_report else "不应当报"
                print(f"FAIL PE005 消音条件（{label}）：{want} PE005，实际 "
                      f"{sorted(f.rule for f in findings)}")
                failures += 1
    if not failures:
        print("PASS PE005 消音必须是一次物质关系声明（裸 depends_on 不再算数）")
    return failures


def check_disabled_rules_change_exit_code() -> int:
    """关掉规则必须体现在退出码上（评审 ③-a）。

    `rules: {PE005: off}` 以前只在摘要行附注一句，退出码与全规则通过一样是 0——CI 与
    pre-commit 无法区分「这台机器判过了」与「这台机器少了几条规则」。现在默认返回 3，
    显式 `--accept-disabled-rules` 才回到 0。
    """
    failures = 0
    off = "rules:\n  PE005: off\n"
    with tempfile.TemporaryDirectory() as td:
        world = _probe_world(td, "depends_on:\n  - weather\n", off)
        with contextlib.redirect_stdout(io.StringIO()):
            code = classlint.cmd_check(world, True, [], False)
        if code != 3:
            print(f"FAIL 关掉规则时退出码应为 3（判定不完整），实际 {code}")
            failures += 1
        with contextlib.redirect_stdout(io.StringIO()):
            code_accept = classlint.cmd_check(world, True, [], True)
        if code_accept != 0:
            print(f"FAIL --accept-disabled-rules 应回到 0，实际 {code_accept}")
            failures += 1
    with tempfile.TemporaryDirectory() as td:
        world = _probe_world(td, "depends_on:\n  - weather\n")
        with contextlib.redirect_stdout(io.StringIO()):
            code_open = classlint.cmd_check(world, True, [], False)
        if code_open != 0:
            print(f"FAIL 没有关规则时（只有 warning）应为 0，实际 {code_open}")
            failures += 1
    if not failures:
        print("PASS 关掉规则的判定不完整必须可见（退出码 3，可显式接受）")
    return failures


def _legit_world(td: str, king: str, pope: str, tradition: str = "") -> Path:
    world = Path(td)
    (world / "codex").mkdir(parents=True, exist_ok=True)
    (world / "classlint.yaml").write_text("name: legit\nclasslint: \"0.1\"\n", encoding="utf-8")
    for entry_id, body in (("king", king), ("pope", pope), ("tradition", tradition)):
        if not body:
            continue
        (world / "codex" / f"{entry_id}.md").write_text(
            f"---\nid: {entry_id}\ntitle: {entry_id}\ntype: character\n{body}---\n正文。\n",
            encoding="utf-8")
    return world


def check_legitimacy_forms_are_indistinguishable() -> int:
    """「名分依据」的两种写法必须得到同一份判定（拆分 `depends_on` 的核心承诺）。

    新关系名 `A derives_legitimacy_from B` 与旧写法 `B legitimizes A` 是**同一句话**：
    翻译在进图时完成，方向反过来，于是 PE003 的闭环、外部锚点、报在哪一侧全都一致。
    这里同时钉住方向（写反了要么闭环消失、要么凭空多一个闭环）与「名分不冒充生产关系」
    （不触发 PE001/PE004/PE005——它既不是抽取，也不是供给）。
    """
    failures = 0
    # 无锚闭环：两种写法都必须报 PE003，并且报在同一个条目上
    with tempfile.TemporaryDirectory() as td:
        legacy = _legit_world(td, "legitimizes: [pope]\n", "legitimizes: [king]\n")
        _, _, findings_legacy, _ = classlint.run_checks(legacy)
    with tempfile.TemporaryDirectory() as td:
        canonical = _legit_world(
            td,
            "relations:\n  - {type: derives_legitimacy_from, target: pope}\n",
            "relations:\n  - {type: derives_legitimacy_from, target: king}\n")
        _, _, findings_canonical, _ = classlint.run_checks(canonical)
    key = lambda fs: sorted((f.rule, f.level, f.entry) for f in fs)
    if key(findings_canonical) != key(findings_legacy):
        print(f"FAIL 名分依据两种写法判定不一致：\n"
              f"  旧写法 legitimizes：{key(findings_legacy)}\n"
              f"  新关系名：{key(findings_canonical)}")
        failures += 1
    if not any(f.rule == "PE003" for f in findings_canonical):
        print("FAIL 新关系名的无锚闭环没有报 PE003（方向写反会让闭环消失）")
        failures += 1
    # 有外部锚点：两种写法都必须全绿
    with tempfile.TemporaryDirectory() as td:
        canonical_ok = _legit_world(
            td,
            "relations:\n  - {type: derives_legitimacy_from, target: pope}\n",
            "relations:\n  - {type: derives_legitimacy_from, target: king}\n"
            "  - {type: derives_legitimacy_from, target: tradition}\n",
            tradition="legitimizes: [king]\n")
        _, _, findings_ok, _ = classlint.run_checks(canonical_ok)
    if any(f.rule == "PE003" for f in findings_ok):
        print(f"FAIL 有外部锚点的名分闭环被误报：{key(findings_ok)}")
        failures += 1
    # 悬空的名分来源不能凭空当锚点：king↔pope 闭环 + king 另写一条指向不存在的传统，
    # 那条悬空边既不能救活闭环（当锚点），也不能把闭环变成别的形状。
    with tempfile.TemporaryDirectory() as td:
        ghost = _legit_world(
            td,
            "relations:\n  - {type: derives_legitimacy_from, target: pope}\n"
            "  - {type: derives_legitimacy_from, target: ghost-tradition}\n",
            "relations:\n  - {type: derives_legitimacy_from, target: king}\n")
        _, _, findings_ghost, _ = classlint.run_checks(ghost)
    if not any(f.rule == "PE003" for f in findings_ghost):
        print("FAIL 悬空的名分来源被当成了外部锚点（闭环应当照报 PE003）")
        failures += 1
    # 名分不是生产关系：不触发抽取/供给三规则
    spurious = sorted({f.rule for f in findings_canonical} & {"PE001", "PE004", "PE005"})
    if spurious:
        print(f"FAIL 名分依据被当成了生产关系：{spurious}")
        failures += 1
    if not failures:
        print("PASS 名分依据的两种写法同判（方向、锚点、报在哪一侧都一致）")
    return failures


def main() -> int:
    failures = 0
    worlds = sorted(p.name for p in TESTS.iterdir()
                    if p.is_dir() and (p / "classlint.yaml").is_file())
    for name in worlds:
        if name not in EXPECTED:
            print(f"FAIL {name}: 夹具未在 EXPECTED 中登记期望判定")
            failures += 1
            continue
        _, _, findings, _ = classlint.run_checks(TESTS / name)
        got = sorted((f.rule, f.level, f.entry) for f in findings)
        want = sorted(EXPECTED[name])
        if got == want:
            print(f"PASS {name} ({len(got)} 条发现)")
        else:
            failures += 1
            print(f"FAIL {name}")
            for item in got:
                if item not in want:
                    print(f"  多报: {item}")
            for item in want:
                if item not in got:
                    print(f"  漏报: {item}")
    failures += check_cl100_intent()
    failures += check_pe005_requires_material_source()
    failures += check_disabled_rules_change_exit_code()
    failures += check_legitimacy_forms_are_indistinguishable()
    extra = set(EXPECTED) - set(worlds)
    for name in sorted(extra):
        print(f"FAIL {name}: EXPECTED 登记了期望但夹具目录不存在")
        failures += 1
    print(f"\n{len(worlds)} 个夹具世界 | {'全部通过' if not failures else f'{failures} 个失败'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
