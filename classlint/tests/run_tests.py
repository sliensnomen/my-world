#!/usr/bin/env python3
"""classlint fixture 测试：tests/<世界>/ 每个目录是一个世界仓库，EXPECTED 钉死期望判定。

用法: python3 tests/run_tests.py   （在 classlint/ 目录内或任意位置均可）
退出码: 0=全部符合期望 1=有偏差
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import classlint  # noqa: E402

from judges.compare import finding_tuple  # noqa: E402

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
    "pe009-bad": [
        ("PE009", "warning", "codex/debtor.md"),  # 债收不回来：债主没有任何收账通道
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


def check_pe009_requires_a_collection_channel() -> int:
    """PE009：记一笔债，就要说清它凭什么收得回来。

    两种通道都算数——债主对债务人的支配（controls/coerces/extracts/legitimizes），
    或债务人依赖债主（depends_on，断供即崩）。都没有才是问题：那样的 owes 只是一句
    记账，模型里没有任何能兑现它的结构。这里钉住每条通道各自都能消音，以及一个都
    没有时必须报。
    """
    failures = 0

    def probe(debtor_extra: str, creditor_extra: str = "") -> bool:
        with tempfile.TemporaryDirectory() as td:
            world = Path(td)
            (world / "codex").mkdir()
            (world / "classlint.yaml").write_text("name: p\nclasslint: \"0.1\"\n",
                                                 encoding="utf-8")
            (world / "codex" / "debtor.md").write_text(
                "---\nid: debtor\ntitle: 债务人\ntype: faction\n"
                f"owes:\n  - id: creditor\n    what: 借款\n{debtor_extra}---\n正文。\n",
                encoding="utf-8")
            (world / "codex" / "creditor.md").write_text(
                "---\nid: creditor\ntitle: 债主\ntype: institution\n"
                f"{creditor_extra}---\n正文。\n", encoding="utf-8")
            _, _, findings, _ = classlint.run_checks(world)
            return any(f.rule == "PE009" and f.entry == "codex/debtor.md"
                       for f in findings)

    cases = [
        ("没有任何通道", "", "", True),
        ("债主 controls 债务人", "", "controls: [debtor]\n", False),
        ("债主 coerces 债务人", "", "coerces: [debtor]\n", False),
        ("债主 extracts 债务人（欠租/利息）", "", "extracts:\n  - id: debtor\n    what: 利息\n", False),
        ("债主 legitimizes 债务人", "", "legitimizes: [debtor]\n", False),
        ("债务人 depends_on 债主（断供即崩）",
         "depends_on:\n  - id: creditor\n    critical: true\n", "", False),
        # 裸依赖不算通道（与 PE005 同口径）：只说「我依赖他」，不足以上升成「他能收得回」
        ("债务人裸依赖债主（无 critical、无物质 kind）",
         "depends_on:\n  - id: creditor\n", "", True),
        ("债务人靠物质类别依赖债主（kind: fiscal）",
         "depends_on:\n  - id: creditor\n    kind: fiscal\n", "", False),
        ("债务人非 critical 但有物质 kind（economy）",
         "depends_on:\n  - id: creditor\n    kind: economy\n", "", False),
        ("债务人靠 x- 实验类别依赖债主（不算物质族）",
         "depends_on:\n  - id: creditor\n    kind: x-mine-weather\n", "", True),
    ]
    for label, d_extra, c_extra, should_report in cases:
        got = probe(d_extra, c_extra)
        if got != should_report:
            want = "应当报" if should_report else "不应当报"
            print(f"FAIL PE009 收账通道（{label}）：{want} PE009，实际"
                  f"{'报了' if got else '没报'}")
            failures += 1
    if not failures:
        print("PASS 债务必须收得回来（四条支配通道 + 承重的债务人依赖，各自都能消音）")
    return failures


def check_shadowed_entries_are_still_judged() -> int:
    """两张卡撞同一个 id 时，被遮蔽那一张写下的边照样要判（CL105 不许消失）。

    以前 `World.__init__` 只遍历 `index.values()`，撞 id 的那一份整个掉出判定图：
    世界里明明躺着一条指向不存在条目的边，输出却只剩一条 CL102。canonlint 侧对同一个
    世界报 CA114 + 悬空引用，两个引擎结论不同——而「同一份数据同一份判定」是这套东西
    的全部意义。这里钉住：撞 id 时，被遮蔽那一份的悬空边照样报 CL105。
    """
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: shadow\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        # 按路径序 a.md 先入索引，b.md 被遮蔽；悬空边写在被遮蔽的 b.md 里。
        (world / "codex" / "a.md").write_text(
            "---\nid: dup\ntitle: 先来的\ntype: faction\n---\n。\n", encoding="utf-8")
        (world / "codex" / "b.md").write_text(
            "---\nid: dup\ntitle: 被遮蔽的\ntype: faction\n"
            "extracts: [ghost-nowhere]\n---\n。\n", encoding="utf-8")
        _, _, findings, _ = classlint.run_checks(world)
        rules = {f.rule for f in findings}
        hits = [f for f in findings if f.rule == "CL105" and "ghost-nowhere" in f.message]
        if "CL102" not in rules:
            print(f"FAIL 撞 id 没报 CL102（实际 {sorted(rules)}）")
            failures += 1
        elif not hits:
            print(f"FAIL 被遮蔽条目的悬空边没报 CL105（实际 {sorted(rules)}）")
            failures += 1
        elif hits[0].entry != "codex/b.md":
            print(f"FAIL CL105 报在了 {hits[0].entry}，应当报在写下那条边的 codex/b.md")
            failures += 1
    if not failures:
        print("PASS 被遮蔽条目的边照样进图（CL102 + 它自己的 CL105，且报对文件）")
    return failures


def check_rule_guards_and_usage_errors() -> int:
    """四条「判得不对 / 静默通过」的守卫（评审 3、4、6、10）。

    - PE001 对**不存在**的目标论证「没有基础」：CL105 已经报过，这句是空话；
    - `--impact` 在环里把主体带回自己的下游：CA504 早就不这么做了，本引擎没跟上；
    - 指错目录时 0 条目 + `judgement_complete: true` + exit 0：整机版的「看起来在审」；
    - 近失拼写（`extractss`）让 PE 族永久失明：边要按规范名建，且必须说出来。
    """
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        world = _probe_world(td, "")
        # PE001：extracts 指向不存在的目标，只许有 CL105，许没有 PE001
        (world / "codex" / "dangling.md").write_text(
            "---\nid: dangling\ntitle: 悬空\ntype: faction\nextracts: [ghost]\n---\n。\n",
            encoding="utf-8")
        _, _, findings, _ = classlint.run_checks(world)
        rules = {f.rule for f in findings if f.entry == "codex/dangling.md"}
        if "CL105" not in rules or "PE001" in rules:
            print(f"FAIL PE001 不该对不存在的目标下判语，实际 {sorted(rules)}")
            failures += 1
        else:
            print("PASS PE001 跳过悬空目标（CL105 已报，不双报）")

    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: probe\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        (world / "codex" / "a.md").write_text(
            "---\nid: a\ntitle: A\ntype: faction\ndepends_on: [a]\n---\n。\n",
            encoding="utf-8")
        index = classlint.collect(world)[1]
        reports = classlint.impact_report(index, ["a"])
        # `reports` 为空、或下游为空的写法要分开断言：原来写成
        # `if reports and reports[0]["downstream"]`，于是 `return []` 直接跳过判断，
        # 锁全绿（评审 high）。主体存在时，报告本身必须有。
        if not reports:
            print("FAIL --impact 对存在的条目没给报告")
            failures += 1
        elif reports[0]["downstream"]:
            print(f"FAIL --impact 把主体列进了自己的下游：{reports}")
            failures += 1
        else:
            print("PASS --impact 不把主体列进自己的下游（自环也一样）")

    with tempfile.TemporaryDirectory() as td:
        empty = Path(td)
        (empty / "classlint.yaml").write_text("name: nope\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        (empty / "entries").mkdir()
        (empty / "entries" / "a.md").write_text("---\nid: a\n---\n。\n", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = classlint.cmd_check(empty, as_json=False, impact_ids=[])
        if rc != 2 or "指错目录" not in err.getvalue():
            print(f"FAIL 指错目录应 exit 2 并说明原因，实际 rc={rc} err={err.getvalue()!r}")
            failures += 1
        else:
            print("PASS 指错目录是用法错误（exit 2，不再给全绿报告）")

    with tempfile.TemporaryDirectory() as td:
        world = _probe_world(td, "")
        (world / "codex" / "typo.md").write_text(
            "---\nid: typo\ntitle: 手滑\ntype: faction\n"
            "relations:\n  - type: extractss\n    target: tenant\n---\n。\n",
            encoding="utf-8")
        _, _, findings, _ = classlint.run_checks(world)
        got = {(f.rule, f.entry) for f in findings}
        # 边按 extracts 建 → PE001 判得到；同时 CL107 说明「你写的是 extractss」
        if ("PE001", "codex/typo.md") not in got or ("CL107", "codex/typo.md") not in got:
            print(f"FAIL 近失拼写既不提示也不判定，实际 {sorted(got)}")
            failures += 1
        else:
            print("PASS 近失拼写按规范名判定，并报 CL107")
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


def _mentions_world(td: str, body: str, registry: str | None = None) -> Path:
    world = Path(td) / "w"
    (world / "codex").mkdir(parents=True)
    (world / "classlint.yaml").write_text(
        "name: mentions\nclasslint: \"0.1\"\nrules: {}\n", encoding="utf-8")
    (world / "codex" / "gray-harbor.md").write_text(
        "---\nid: gray-harbor\ntitle: 灰港\ntype: faction\n"
        f"controls: [tenant]\nextracts: [tenant]\n---\n{body}\n", encoding="utf-8")
    (world / "codex" / "tenant.md").write_text(
        "---\nid: tenant\ntitle: 佃户\ntype: faction\n---\n正文。\n", encoding="utf-8")
    if registry is not None:
        (world / "codex" / "entities.yaml").write_text(registry, encoding="utf-8")
    return world


def _check_json(world: Path) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = classlint.cmd_check(world, True, [])
    return code, json.loads(out.getvalue())


def check_entity_mentions_in_json() -> int:
    failures = 0

    def expect(condition, message):
        nonlocal failures
        if not condition:
            print(f"FAIL {message}")
            failures += 1

    body = ("灰港城先征税，灰港随后跟进，灰港城再次争议。\n"
            "```\n灰港\n```\nharbor Harbor harbor-master harbormaster gray-harbor")
    registry = "entities:\n  gray-harbor:\n    aliases: [灰港, 灰港城, harbor]\n"
    with tempfile.TemporaryDirectory() as td:
        world = _mentions_world(td, body)
        code, baseline = _check_json(world)
        expect(code == 0, f"缺 entities.yaml 应兼容，exit={code}")
        expect(all(e["mentions"] == [] for e in baseline["entries"]),
               f"缺注册表时 mentions 应全为空：{baseline['entries']}")
        baseline_text = io.StringIO()
        with contextlib.redirect_stdout(baseline_text):
            classlint.cmd_check(world, False, [])
        baseline_graph = io.StringIO()
        with contextlib.redirect_stdout(baseline_graph):
            classlint.cmd_graph(world, "json")
        baseline_graph_data = json.loads(baseline_graph.getvalue())
        (world / "codex" / "entities.yaml").write_text(registry, encoding="utf-8")
        code, data = _check_json(world)
        expect(code == 0, f"合法别名表应通过，exit={code}")
        expect(data["findings"] == baseline["findings"],
               f"别名识别改变了 CL/PE findings：{data['findings']} != {baseline['findings']}")
        gray = next(e for e in data["entries"] if e["id"] == "gray-harbor")
        expected = [
            {"entity": "gray-harbor", "alias": "灰港城", "count": 2},
            {"entity": "gray-harbor", "alias": "灰港", "count": 2},
            {"entity": "gray-harbor", "alias": "harbor", "count": 1},
        ]
        expect(gray["mentions"] == expected,
               f"最长匹配/边界/计数/排序不对：{gray['mentions']} != {expected}")
        tenant = next(e for e in data["entries"] if e["id"] == "tenant")
        expect(tenant["mentions"] == [], f"无匹配正文应为空：{tenant['mentions']}")
        baseline_meta = {e["id"]: e["meta"] for e in baseline["entries"]}
        after_meta = {e["id"]: e["meta"] for e in data["entries"]}
        expect(after_meta == baseline_meta, "别名识别改变了 frontmatter 关系或元数据")
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            classlint.cmd_check(world, False, [])
        expect(text.getvalue() == baseline_text.getvalue(),
               f"文本输出被正文提及改变：{text.getvalue()} != {baseline_text.getvalue()}")
        graph = io.StringIO()
        with contextlib.redirect_stdout(graph):
            classlint.cmd_graph(world, "json")
        graph_data = json.loads(graph.getvalue())
        expect(graph_data == baseline_graph_data,
               f"graph 被别名改变：{graph_data} != {baseline_graph_data}")
    with tempfile.TemporaryDirectory() as td:
        world = _mentions_world(td, "没有注册别名。", "entities: {}\n")
        code, data = _check_json(world)
        expect(code == 0 and all(e["mentions"] == [] for e in data["entries"]),
               "空注册表应输出空 mentions")
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "w"
        with contextlib.redirect_stdout(io.StringIO()):
            init_code = classlint.cmd_init(world)
        expect(init_code == 0, f"classlint init 应成功，exit={init_code}")
        code, data = _check_json(world)
        expect(code == 0 and data["entries"] == [],
               f"init 生成的 entities.yaml 必须可读：exit={code}")
    if not failures:
        print("PASS 正文别名进入 check --json（计数/边界/兼容/不改变判定）")
    return failures


def check_finding_order_matters() -> int:
    """Finding 顺序是判定的一部分：仅交换顺序必须不等，排序后必须相等。"""
    failures = 0
    try:
        a = classlint.Finding("PE001", "error", "codex/a.md", "msg a")
        b = classlint.Finding("PE002", "warning", "codex/b.md", "msg b")
        raw_a = [finding_tuple(f) for f in [a, b]]
        raw_b = [finding_tuple(f) for f in [b, a]]
        if raw_a == raw_b:
            print("FAIL Finding 顺序：仅交换顺序后仍相等")
            failures += 1
        elif sorted(raw_a) != sorted(raw_b):
            print("FAIL Finding 顺序：排序后不相等")
            failures += 1
        else:
            print("PASS Finding 顺序：原始序列不等，排序后相等")
    except Exception as e:
        print(f"FAIL Finding 顺序断言异常：{e}")
        failures += 1
    return failures


def check_entity_registry_errors_are_config_errors() -> int:
    failures = 0
    bad = {
        "未知稳定 id": "entities:\n  ghost:\n    aliases: [灰港]\n",
        "非法稳定 id": "entities:\n  Bad_ID:\n    aliases: [灰港]\n",
        "重复别名": "entities:\n  gray-harbor:\n    aliases: [灰港, 灰港]\n",
        "跨实体重复别名": "entities:\n  gray-harbor:\n    aliases: [灰港]\n  tenant:\n    aliases: [灰港]\n",
        "空别名": "entities:\n  gray-harbor:\n    aliases: ['']\n",
        "非字符串别名": "entities:\n  gray-harbor:\n    aliases: [1]\n",
        "实体记录非映射": "entities:\n  gray-harbor: []\n",
        "aliases 非列表": "entities:\n  gray-harbor:\n    aliases: 灰港\n",
        "entities 非映射": "entities: []\n",
        "顶层非映射": "- entities\n",
        "坏 YAML": "entities: [\n",
    }
    for name, registry in bad.items():
        with tempfile.TemporaryDirectory() as td:
            world = _mentions_world(td, "灰港", registry)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = classlint.cmd_check(world, True, [])
            if code != 2 or "entities.yaml" not in err.getvalue() or out.getvalue():
                print(f"FAIL {name} 应是干净的配置错误：exit={code}, "
                      f"stdout={out.getvalue()!r}, stderr={err.getvalue()!r}")
                failures += 1
    if not failures:
        print("PASS entities.yaml 的坏形状/冲突全部是退出码 2")
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


def _backend_call(backend: str, operation):
    """Registry 不得借 legacy collect/PE 函数偷偷满足双跑。"""
    import os
    from unittest import mock

    with mock.patch.dict(os.environ, {"WGP_JUDGE_BACKEND": backend}):
        if backend == "legacy":
            return operation()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                classlint, "collect", return_value=([], {}, [])))
            for registered in classlint.RULES.values():
                stack.enter_context(mock.patch.object(registered, "fn", return_value=None))
            return operation()


def _capture_backend(world: Path, backend: str, operation):
    from judges.compare import normalized_cli_result

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _backend_call(backend, operation)
    return normalized_cli_result(code, out.getvalue(), err.getvalue(), world)


def check_registry_cl_pe_dual_run() -> int:
    """每条 CL/PE 的真实正反例、原始顺序和完整外部行为都必须双跑一致。"""
    import os
    from unittest import mock
    from judges.compare import finding_tuple
    from judges.registry import select_packs

    failures = 0

    def expect(condition, message):
        nonlocal failures
        if not condition:
            print(f"FAIL {message}")
            failures += 1

    try:
        registry = select_packs("classlint", ["core-cl", "pe"])
        core, pe = registry.selected
        expect([r.id for r in core.rules] == [f"CL{n}" for n in range(100, 108)],
               f"core-cl 必须逐规则登记 CL100–CL107：{[r.id for r in core.rules]}")
        expect([r.id for r in pe.rules] == ["PE001", "PE002", "PE003", "PE004", "PE005", "PE009"],
               f"pe 必须按原顺序登记六条规则：{[r.id for r in pe.rules]}")
        expect(core.ca106_fields == frozenset() and pe.ca106_fields == frozenset(),
               "classlint 的 CL103 私有字段政策不得写进 ca106_fields")
        expect(all(r.scope == "entry" and r.entry_domain == "all_entries"
                   for r in core.rules if r.id != "CL105"),
               "CL100–CL104/106/107 必须逐条目遍历 all_entries（含被遮蔽条目）")
    except Exception as exc:
        expect(False, f"classlint Registry Pack 应可独立加载：{type(exc).__name__}: {exc}")

    def compare_world(label, world, expected=(), forbidden=()):
        nonlocal failures
        try:
            old = _backend_call("legacy", lambda: classlint.run_checks(world))
            new = _backend_call("registry", lambda: classlint.run_checks(world))
        except Exception as exc:
            expect(False, f"{label}：双跑异常 {type(exc).__name__}: {exc}")
            return None
        old_raw = [finding_tuple(f) for f in old[2]]
        new_raw = [finding_tuple(f) for f in new[2]]
        expect(old_raw == new_raw,
               f"{label}：原始 Finding 双跑不同\n旧 {old_raw!r}\n新 {new_raw!r}")
        order = {"error": 0, "warning": 1}
        key = lambda f: (order.get(f.level, 2), f.rule, f.entry)
        old_final = [finding_tuple(f) for f in sorted(old[2], key=key)]
        new_final = [finding_tuple(f) for f in sorted(new[2], key=key)]
        expect(old_final == new_final, f"{label}：出口排序 Finding 双跑不同")
        old_shape = ([(e.rel, e.id) for e in old[0]], list(old[1]), sorted(old[3]))
        new_shape = ([(e.rel, e.id) for e in new[0]], list(new[1]), sorted(new[3]))
        expect(old_shape == new_shape, f"{label}：条目/索引/disabled 双跑不同：{old_shape} != {new_shape}")
        for backend, findings in (("legacy", old[2]), ("registry", new[2])):
            rules = {f.rule for f in findings}
            expect(set(expected) <= rules,
                   f"{label}/{backend} 缺真实阳性 Finding：{sorted(set(expected) - rules)}")
            expect(not (set(forbidden) & rules),
                   f"{label}/{backend} 真阴性误报：{sorted(set(forbidden) & rules)}")
        return old, new

    worlds = sorted(p for p in TESTS.iterdir()
                    if p.is_dir() and (p / "classlint.yaml").is_file())
    for world in worlds:
        compare_world(f"18 世界/{world.name}", world)
        for label, operation in (
            ("check-text", lambda w=world: classlint.cmd_check(w, False, [])),
            ("check-json", lambda w=world: classlint.cmd_check(w, True, [])),
            ("graph-dot", lambda w=world: classlint.cmd_graph(w, "dot")),
            ("graph-json", lambda w=world: classlint.cmd_graph(w, "json")),
        ):
            old = _capture_backend(world, "legacy", operation)
            new = _capture_backend(world, "registry", operation)
            expect(old == new, f"18 世界/{world.name}/{label}：CLI 双跑不同")

    cl_rules = {f"CL{n}" for n in range(100, 108)}
    compare_world("CL 真阴性", TESTS / "clean", forbidden=cl_rules)
    compare_world("CL101–CL105 真阳性", TESTS / "structure-bad",
                  expected={"CL101", "CL102", "CL103", "CL104", "CL105"})
    for name, rule in (("pe001", "PE001"), ("pe002", "PE002"), ("pe003", "PE003")):
        compare_world(f"{rule} 真阳性", TESTS / f"{name}-bad", expected={rule})
        compare_world(f"{rule} 真阴性", TESTS / f"{name}-ok", forbidden={rule})
    compare_world("PE004 真阳性", TESTS / "pe004-bad", expected={"PE004"})
    compare_world("PE004 真阴性", TESTS / "merchant-capital", forbidden={"PE004"})
    compare_world("PE005 真阳性", TESTS / "pe005-bad", expected={"PE005"})
    compare_world("PE005 真阴性", TESTS / "feudal-rent", forbidden={"PE005"})
    compare_world("PE009 真阳性", TESTS / "pe009-bad", expected={"PE009"})
    compare_world("PE009 真阴性", TESTS / "state-redistribution", forbidden={"PE009"})

    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: probe\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        (world / "codex" / "bad.md").write_bytes(b"---\nid: bad\ntitle: \xff\xfe\n---\n\xff\n")
        compare_world("CL100 真阳性", world, expected={"CL100"})

    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: probe\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        (world / "codex" / "a.md").write_text(
            "---\nid: a\ntitle: A\ntype: faction\ndepends_on:\n"
            "  - id: b\n    kind: legitimacy\n---\n。\n", encoding="utf-8")
        (world / "codex" / "b.md").write_text(
            "---\nid: b\ntitle: B\ntype: faction\n---\n。\n", encoding="utf-8")
        compare_world("CL106 真阳性/名分旧写法", world, expected={"CL106"})

    with tempfile.TemporaryDirectory() as td:
        world = _probe_world(td, "depends_on:\n  - id: weather\n    kind: resource\n")
        (world / "codex" / "typo.md").write_text(
            "---\nid: typo\ntitle: 手滑\ntype: faction\n"
            "relations:\n  - type: extractss\n    target: tenant\n---\n。\n",
            encoding="utf-8")
        compare_world("CL107 真阳性", world, expected={"CL107"})

    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: shadow\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        (world / "codex" / "a.md").write_text(
            "---\nid: dup\ntitle: 先来的\ntype: faction\n---\n。\n", encoding="utf-8")
        (world / "codex" / "b.md").write_text(
            "---\nid: dup\ntitle: 被遮蔽的\ntype: faction\nextracts: [ghost]\n---\n。\n",
            encoding="utf-8")
        result = compare_world("被遮蔽条目", world, expected={"CL102", "CL105"})
        if result:
            for backend, run in zip(("legacy", "registry"), result):
                hits = [f for f in run[2] if f.rule == "CL105"]
                expect([f.entry for f in hits] == ["codex/b.md"],
                       f"被遮蔽条目/{backend} 的 CL105 必须报在 codex/b.md：{hits}")

    with tempfile.TemporaryDirectory() as td:
        world = Path(td)
        (world / "codex").mkdir()
        (world / "classlint.yaml").write_text("name: order\nclasslint: \"0.1\"\n",
                                              encoding="utf-8")
        cards = {
            "a": "---\nid: a\ntype: faction\nextracts: [ghost]\ndepends_on:\n"
                 "  - id: tenant\n    kind: legitimacy\n---\n。\n",
            "lord": "---\nid: lord\ntitle: 地主\ntype: faction\nextracts: [tenant]\n---\n。\n",
            "tenant": "---\nid: tenant\ntitle: 佃农\ntype: faction\ndepends_on:\n"
                      "  - id: weather\n    kind: resource\n---\n。\n",
            "weather": "---\nid: weather\ntitle: 天气\ntype: location\n---\n。\n",
        }
        for name, text in cards.items():
            (world / "codex" / f"{name}.md").write_text(text, encoding="utf-8")
        result = compare_world("collect→CL105→PE 顺序", world,
                               expected={"CL101", "CL106", "CL105", "PE001"})
        if result:
            for backend, run in zip(("legacy", "registry"), result):
                sequence = [f.rule for f in run[2]]
                expect(sequence == ["CL101", "CL106", "CL105", "PE001"],
                       f"collect→CL105→PE/{backend} 原始顺序错误：{sequence}")

    with tempfile.TemporaryDirectory() as old_td, tempfile.TemporaryDirectory() as new_td:
        old_world = _legit_world(old_td, "legitimizes: [pope]\n", "legitimizes: [king]\n")
        new_world = _legit_world(
            new_td,
            "relations:\n  - {type: derives_legitimacy_from, target: pope}\n",
            "relations:\n  - {type: derives_legitimacy_from, target: king}\n")
        for backend in ("legacy", "registry"):
            old = _backend_call(backend, lambda: classlint.run_checks(old_world))[2]
            new = _backend_call(backend, lambda: classlint.run_checks(new_world))[2]
            expect([finding_tuple(f) for f in old] == [finding_tuple(f) for f in new],
                   f"名分两种写法/{backend} 的完整 Finding 不同")
            expect(any(f.rule == "PE003" for f in new),
                   f"名分两种写法/{backend} 缺 PE003 真阳性")

    for off_value in ("off", '"off"'):
        with tempfile.TemporaryDirectory() as td:
            rules = f"rules:\n  PE005: {off_value}\n"
            world = _probe_world(td, "depends_on:\n  - weather\n", rules)
            result = compare_world(f"rules off={off_value}", world, forbidden={"PE005"})
            if result:
                for backend, run in zip(("legacy", "registry"), result):
                    expect(run[3] == {"PE005"},
                           f"rules off={off_value}/{backend} disabled 应为 PE005：{run[3]}")
            for accept in (False, True):
                old = _capture_backend(world, "legacy",
                                       lambda: classlint.cmd_check(world, True, [], accept))
                new = _capture_backend(world, "registry",
                                       lambda: classlint.cmd_check(world, True, [], accept))
                expect(old == new, f"rules off={off_value}/accept={accept}：JSON/退出码双跑不同")
                expect(old[0] == (0 if accept else 3),
                       f"rules off={off_value}/accept={accept}：退出码应为 {0 if accept else 3}，实际 {old[0]}")
                payload = json.loads(old[1])
                expect(payload["rules_disabled"] == ["PE005"]
                       and payload["judgement_complete"] is False,
                       "rules: off 必须保留 rules_disabled 与 judgement_complete=false")

    with tempfile.TemporaryDirectory() as td:
        world = _mentions_world(
            td, "灰港城先征税，灰港随后跟进，灰港城再次争议。",
            "entities:\n  gray-harbor:\n    aliases: [灰港, 灰港城]\n")
        for label, operation in (
            ("check-text", lambda: classlint.cmd_check(world, False, [])),
            ("check-json", lambda: classlint.cmd_check(world, True, [])),
            ("graph-dot", lambda: classlint.cmd_graph(world, "dot")),
            ("graph-json", lambda: classlint.cmd_graph(world, "json")),
        ):
            old = _capture_backend(world, "legacy", operation)
            new = _capture_backend(world, "registry", operation)
            expect(old == new, f"mentions/graph/{label} 双跑不同")
            if label == "check-json" and new[1]:
                payload = json.loads(new[1])
                gray = next(e for e in payload["entries"] if e["id"] == "gray-harbor")
                expect(gray["mentions"] == [
                    {"entity": "gray-harbor", "alias": "灰港城", "count": 2},
                    {"entity": "gray-harbor", "alias": "灰港", "count": 1},
                ], f"mentions 内容改变：{gray['mentions']}")
                expect(payload["judgement_complete"] is True,
                       "未关规则时 judgement_complete 必须为 true")

    for bad_rule in ("PE999", "CL100"):
        with tempfile.TemporaryDirectory() as td:
            world = _probe_world(td, "", f"rules:\n  {bad_rule}: off\n")
            for backend in ("legacy", "registry"):
                result = _capture_backend(world, backend,
                                          lambda: classlint.cmd_check(world, True, []))
                expect(result[0] == 2 and not result[1] and "未知规则编号" in result[2],
                       f"{bad_rule}/{backend} 必须在执行前配置失败：{result}")

    with tempfile.TemporaryDirectory() as td:
        world = _probe_world(td, "")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"WGP_JUDGE_BACKEND": "future"}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = classlint.cmd_check(world, True, [])
        result = (code, out.getvalue(), err.getvalue())
        expect(result[0] == 2 and not result[1] and "WGP_JUDGE_BACKEND" in result[2],
               f"非法后端必须在审计前 exit 2：{result}")

    with tempfile.TemporaryDirectory() as old_td, tempfile.TemporaryDirectory() as new_td:
        old_world, new_world = Path(old_td) / "w", Path(new_td) / "w"
        old = _capture_backend(old_world, "legacy", lambda: classlint.cmd_init(old_world))
        new = _capture_backend(new_world, "registry", lambda: classlint.cmd_init(new_world))
        expect(old == new, "classlint init 的输出/退出码双跑不同")
        tree = lambda root: {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts
        }
        expect(tree(old_world) == tree(new_world), "classlint init 生成的文件双跑不同")
        old = _capture_backend(old_world, "legacy", lambda: classlint.cmd_check(old_world, True, []))
        new = _capture_backend(new_world, "registry", lambda: classlint.cmd_check(new_world, True, []))
        expect(old == new, "init 后首次 check 双跑不同")

    if not failures:
        print("PASS core-cl/pe 双跑：14 条规则正反例、原始顺序、JSON/graph/mentions/init 全一致")
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
    failures += check_pe009_requires_a_collection_channel()
    failures += check_rule_guards_and_usage_errors()
    failures += check_shadowed_entries_are_still_judged()
    failures += check_disabled_rules_change_exit_code()
    failures += check_legitimacy_forms_are_indistinguishable()
    failures += check_entity_mentions_in_json()
    failures += check_entity_registry_errors_are_config_errors()
    failures += check_finding_order_matters()
    failures += check_registry_cl_pe_dual_run()
    extra = set(EXPECTED) - set(worlds)
    for name in sorted(extra):
        print(f"FAIL {name}: EXPECTED 登记了期望但夹具目录不存在")
        failures += 1
    print(f"\n{len(worlds)} 个夹具世界 | {'全部通过' if not failures else f'{failures} 个失败'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
