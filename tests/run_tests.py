#!/usr/bin/env python3
"""canonlint 夹具测试：钉死每个夹具世界的逐字节输出与退出码。

夹具世界（tests/world-*/）是唯一的回归网：每条规则的判定、每条提示的措辞、
每个退出码都被冻结在这里。任何一条悄悄变了，这里就会变红。

快照文件首行是 `exit=N`，其余是标准输出的原文。
快照只能证明「行为和上次一样」，所以另有一组**意图断言**证明「守卫生效」——
守卫被撤销时它们必定变红。

用法:
  python3 tests/run_tests.py            校验
  python3 tests/run_tests.py --update   用当前行为重新生成快照（只在有意变更时用）
退出码: 0=全部一致 1=有偏差
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

SNAPS = HERE / "snapshots"
TOOL = ROOT / "canonlint.py"
PY = sys.executable

# (快照名, 命令行参数)。退出码与标准输出一起被快照钉死。
CASES: list[tuple[str, list[str]]] = [
    ("world-clean", ["tests/world-clean"]),
    # --strict（warning 也算失败）以前**一条夹具都没钉**：README 把 world-clean 称作
    # 「唯一的全绿基准」，而它在 --strict 下曾是 exit 1（三条 CA104），没有测试变红。
    # 这一条把那句话变成可回归的事实：基准世界在两种模式下都必须 exit 0。
    ("world-clean+strict", ["tests/world-clean", "--strict"]),
    ("world-bad", ["tests/world-bad"]),
    ("world-arrakis", ["tests/world-arrakis"]),
    ("world-westeros", ["tests/world-westeros"]),
    ("world-middle-earth", ["tests/world-middle-earth"]),
    ("world-econ", ["tests/world-econ"]),
    ("world-econ+pack-econ", ["tests/world-econ", "--pack", "econ"]),
    ("world-crash", ["tests/world-crash"]),
    # CA504 只能靠 --impact 触发；这是它的第一条覆盖。
    # 钉住的是「报告行长什么样」与「它仍然是 exit=0」。
    ("world-arrakis+impact", ["tests/world-arrakis", "--impact", "sandworm-cycle"]),
    # 事件流水（协议 1.2）：world-ledger 是流水族的全绿基准（默认与 --strict 都 exit 0）；
    # world-ledger-bad 把 CA701–CA706 每条至少踩一次（触发矩阵见 tests/make_ledger.py）。
    ("world-ledger", ["tests/world-ledger"]),
    ("world-ledger+strict", ["tests/world-ledger", "--strict"]),
    ("world-ledger-bad", ["tests/world-ledger-bad"]),
    # ledger 子命令是 report 级输出：快照钉住报告形状，钉住它 exit 0
    ("world-ledger+ledger", ["ledger", "tests/world-ledger"]),
    # 真实作品的流水：冰火世界补了期初与 9 笔账，ledger 输出是 dogfood 的验收物
    ("world-westeros+ledger", ["ledger", "tests/world-westeros"]),
]

# 崩溃守卫的意图断言：(说明, 规则编号, 必须出现在同一条发现里的条目路径)
# 这三条在 PR#0.1 之前都会以 traceback 收场（整个审计崩掉，一条发现都不出）。
# 锁的是「坏输入变成一条发现」这件事；注释里的条数以前写「四条」而列表只有三条（评审 low）。
CRASH_INTENT: list[tuple[str, str, str]] = [
    ("非 UTF-8 文件应报 CA100 而不是崩溃", "CA100", "entries/bad-utf8.md"),
    ("type 取值非字符串应报 CA102", "CA102", "entries/list-type.md"),
    ("stance 取值非字符串应报 CA102", "CA102", "entries/list-stance.md"),
]


def run_case(args: list[str]) -> tuple[int, str, str]:
    """在仓库根运行工具，返回 (退出码, stdout, stderr)。"""
    p = subprocess.run([PY, str(TOOL), *args], cwd=ROOT,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def snapshot_path(name: str) -> Path:
    return SNAPS / f"{name}.txt"


def load_snapshot(name: str) -> tuple[int, str] | None:
    p = snapshot_path(name)
    if not p.is_file():
        return None
    head, _, rest = p.read_text(encoding="utf-8").partition("\n")
    return int(head.split("=", 1)[1]), rest


def dump_snapshot(name: str, code: int, out: str) -> None:
    SNAPS.mkdir(parents=True, exist_ok=True)
    snapshot_path(name).write_text(f"exit={code}\n{out}", encoding="utf-8")


def last_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else "(空输出)"


def diff(want: str, got: str) -> str:
    return "".join(difflib.unified_diff(
        want.splitlines(keepends=True), got.splitlines(keepends=True),
        fromfile="快照", tofile="实际", n=1))


def check_undeclarable_shapes() -> list[str]:
    """悬空软链与名为 *.md 的目录：无法作为可移植夹具提交，运行时构造。

    期望：两者都被静默跳过，输出与 world-clean 完全一致（不崩、不误报）。
    """
    want = None
    for name, args in CASES:
        if name == "world-clean":
            want = load_snapshot(name)
    if want is None:
        return ["缺少 world-clean 快照，无法比对跳过行为"]
    src = HERE / "world-clean" / "entries"
    with tempfile.TemporaryDirectory(prefix="canonlint-shapes-") as tmp:
        world = Path(tmp)
        shutil.copytree(src, world / "entries")
        (world / "entries" / "fake.md").mkdir()          # 名为 *.md 的目录
        os.symlink(world / "no-such-target",             # 悬空软链
                   world / "entries" / "dangling.md")
        p = subprocess.run([PY, str(TOOL), str(world)],
                           cwd=ROOT, capture_output=True, text=True)
    if p.stderr:
        return [f"悬空软链/同名目录让工具把 traceback 写到了 stderr：\n{p.stderr}"]
    if (p.returncode, p.stdout) != (want[0], want[1]):
        return ["悬空软链/同名目录改变了输出（应当被静默跳过）：\n"
                + diff(want[1], p.stdout)]
    return []


def check_json_schema() -> list[str]:
    """§6.5 机器可读契约：键名与类型不能被悄悄改掉。"""
    code, out, err = run_case(["tests/world-bad", "--json"])
    if err:
        return [f"--json 把 traceback 写到了 stderr：\n{err}"]
    if code != 1:
        return [f"--json 在有错误的世界上应返回 1，实际 {code}"]
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return [f"--json 输出不是合法 JSON：{e}"]
    want_keys = {"protocol_version", "entries", "findings", "reports"}
    if set(data) != want_keys:
        return [f"--json 顶层键应为 {sorted(want_keys)}，实际 {sorted(data)}"]
    if not isinstance(data["entries"], int):
        return ["--json 的 entries 应为整数"]
    if not isinstance(data["protocol_version"], str):
        return ["--json 的 protocol_version 应为字符串"]
    if not isinstance(data["reports"], list):
        return ["--json 的 reports 应为数组"]
    for f in data["findings"]:
        if set(f) != {"rule", "level", "entry", "message"}:
            return [f"--json 发现项的键应为 rule/level/entry/message，实际 {sorted(f)}"]
        # 「键名与类型不能被悄悄改掉」这条锁以前只查了 entries 一个 int（评审 medium）：
        # 把 level 改成数字、rule 改成别名，照样绿。
        if not re.fullmatch(r"CA\d{3}", str(f["rule"])):
            return [f"--json 发现项的 rule 应形如 CA123，实际 {f['rule']!r}"]
        if f["level"] not in ("error", "warning", "info"):
            return [f"--json 发现项的 level 只能是 error/warning/info，实际 {f['level']!r}"]
        for key in ("entry", "message"):
            if not isinstance(f[key], str):
                return [f"--json 发现项的 {key} 应为字符串，实际 {type(f[key]).__name__}"]
    return []


def check_impact_is_advisory() -> list[str]:
    """CA504 影响报告是只读的：它不得改变退出码，也不得变成 error/warning。

    job 曾经在这里翻车：旧 CI 的最后一条命令是
        [ -n "$ID" ] && python3 canonlint.py . --json --impact "$ID"
    $ID 为空时整条命令返回 1，于是自称「不拦截，仅提示」的步骤把 job 判红了。
    所以这里把「报告不参与拦截」钉成不变量，而不是靠 shell 的短路语义。
    """
    problems = []
    code_plain, out_plain, err_plain = run_case(["tests/world-arrakis"])
    if err_plain:
        problems.append(f"world-arrakis 把 traceback 写到了 stderr：\n{err_plain}")
    for label, subject in (("已知 subject", "sandworm-cycle"),
                           ("不存在的 subject", "no-such-id")):
        code, out, err = run_case(["tests/world-arrakis", "--impact", subject])
        if err:
            problems.append(f"--impact {subject} 把 traceback 写到了 stderr：\n{err}")
        if code != code_plain:
            problems.append(f"--impact {subject}（{label}）改变了退出码："
                            f"无 --impact={code_plain}，有={code}")
        if last_line(out) != last_line(out_plain):
            problems.append(f"--impact {subject}（{label}）改变了汇总行——"
                            "报告被当成了发现项")
        if not any(ln.startswith("[CA504] report") for ln in out.splitlines()):
            problems.append(f"--impact {subject}（{label}）没有输出 [CA504] report 行")
        bad = [ln for ln in out.splitlines()
               if ln.startswith("[CA504] error") or ln.startswith("[CA504] warning")]
        if bad:
            problems.append(f"--impact {subject}（{label}）以 error/warning 级别报告，"
                            f"它就会开始拦截提交：{bad}")
    return problems


def check_help_discoverable() -> list[str]:
    """--help 必须提到 init/new/link，否则它们只存在于源码里。"""
    code, out, err = run_case(["--help"])
    if code != 0:
        return [f"--help 应返回 0，实际 {code}"]
    if err:
        return [f"--help 往 stderr 写了东西：\n{err}"]
    missing = [c for c in ("init", "new", "link") if f"canonlint {c}" not in out]
    if missing:
        return [f"--help 没有列出子命令 {missing}——不读源码就发现不了它们"]
    return []


def check_missing_dependency_is_clean() -> list[str]:
    """缺 pyyaml 时应当是「一行提示 + 退出码 2」，而不是 traceback。

    做法：临时造一个会抛 ImportError 的 yaml 包，用 PYTHONPATH 盖住真包。
    """
    with tempfile.TemporaryDirectory(prefix="canonlint-noyaml-") as tmp:
        pkg = Path(tmp) / "yaml"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(
            'raise ImportError("simulated: pyyaml 不可用")\n', encoding="utf-8")
        p = subprocess.run([PY, str(TOOL), "tests/world-clean"], cwd=ROOT,
                           capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=tmp))
    if p.returncode != 2:
        return [f"缺 pyyaml 时退出码应为 2，实际 {p.returncode}（stdout={p.stdout!r}）"]
    if "Traceback" in p.stderr:
        return [f"缺 pyyaml 时抛了 traceback：\n{p.stderr}"]
    if "pyyaml" not in p.stderr:
        return [f"缺 pyyaml 时 stderr 应说清缺什么，实际：{p.stderr!r}"]
    return []


# ---- 评审修复的意图断言 ---------------------------------------------------
# 上面五条 extras 与快照网证明「没变」；下面这组证明「评审发现的四个失效模式
# 真的被堵住了」——它们各自对应六域评审里的一条可复现发现，且修复前必然变红。


def _card(entry_id: str, extra: str = "", status: str = "canon",
          body: str | None = None, load_bearing: bool = False,
          template_relations: bool = True) -> str:
    # template_relations=False：不要那两行空的 canon_refs/conflicts_with。
    # 要测「这两种关系的悬空引用」时必须关掉——否则同一张卡里同一个键写两遍，
    # YAML 只留最后一个，测到的是重复键而不是被锁的那件事（评审指出过这个假通过）。
    rels = "canon_refs: []\nconflicts_with: []\n" if template_relations else ""
    return (f"---\nid: {entry_id}\ntitle: {entry_id}\ntype: location\nauthor: t\n"
            f"date: 2026-01-01\nstatus: {status}\n"
            f"load_bearing: {'true' if load_bearing else 'false'}\n"
            f"{rels}{extra}ai_assisted: false\n"
            f"---\n\n{body if body is not None else '正文' * 120}\n")


def _temp_world(prefix: str, entries: dict[str, str]) -> tuple[str, Path]:
    tmp = tempfile.TemporaryDirectory(prefix=prefix)
    world = Path(tmp.name)
    (world / "entries").mkdir(parents=True, exist_ok=True)
    for name, text in entries.items():
        (world / "entries" / f"{name}.md").write_text(text, encoding="utf-8")
    return tmp, world


def _judge(world: Path, *args: str) -> tuple[int, str, str]:
    p = subprocess.run([PY, str(TOOL), str(world), *args], cwd=ROOT,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def _issue38_body(entry_id: str) -> str:
    return (entry_id + "正文") * 120


def _expect_strict_rejection(
    prefix: str,
    entries: dict[str, str],
    *,
    label: str,
    rules: tuple[str, ...],
    entry_any: tuple[str, ...],
) -> list[str]:
    problems = []
    tmp, world = _temp_world(prefix, entries)
    with tmp:
        code, out, err = _judge(world, "--strict")
        if err:
            problems.append(f"{label}：traceback 写到了 stderr：\n{err}")
        if code != 1:
            problems.append(f"{label}：--strict 应 exit 1，实际 exit {code}：\n{out}")
        hits = [
            line for line in out.splitlines()
            if any(entry in line for entry in entry_any)
            and any(f"[{rule}]" in line for rule in rules)
        ]
        if not hits:
            problems.append(
                f"{label}：没有出现预期规则 {rules} 作用于 {entry_any}：\n{out}")
    return problems


def check_strict_only_changes_the_exit_code() -> list[str]:
    """`--strict` 只许改退出码，不许改判定。

    它是 pre-commit 的门禁开关：同一份数据、同一批 findings，`--strict` 只是把
    「有警告」也算失败。如果它顺手改了判定（比如让 CA301/CA104 对草稿也发），
    审计器就替作者做了决定——评审 F8 就是这条。这里钉住三件事：
    无错只有警告时 0 → 1；findings 的 JSON 逐字相同；有 error 时两者都 1。
    """
    problems = []
    # 只有警告的世界：trial 档 + 正文不足 200 字 → CA104 warning
    tmp, world = _temp_world("canonlint-strict-", {
        "thin": _card("thin", status="trial", body="短正文。"),
    })
    with tmp:
        code_plain, out_plain, _ = _judge(world, "--json")
        code_strict, out_strict, _ = _judge(world, "--strict", "--json")
        if code_plain != 0:
            problems.append(f"只有警告时默认应当通过（exit 0），实际 {code_plain}")
        if code_strict != 1:
            problems.append(f"--strict 下警告应当算失败（exit 1），实际 {code_strict}")
        a = json.loads(out_plain)["findings"]
        b = json.loads(out_strict)["findings"]
        if a != b:
            problems.append(f"--strict 改了判定：\n  {a}\n  {b}")
        if not any(f["rule"] == "CA104" for f in a):
            problems.append(f"这个夹具本该触发 CA104 警告，实际 {a}")

    # 有 error 的世界：两者都必须 1
    tmp, world = _temp_world("canonlint-strict-err-", {
        "ref": _card("ref", extra="canon_refs: [ghost-nowhere]\n"),
    })
    with tmp:
        for extra in ((), ("--strict",)):
            code, _, _ = _judge(world, *extra)
            if code != 1:
                problems.append(f"有 error 时 {' '.join(extra) or '默认'} 应当 exit 1，实际 {code}")
    return problems


def check_dup_threshold_is_a_bounded_knob() -> list[str]:
    """`--dup-threshold` 的边界与效果都要钉住（评审 §9：三个开关没做守卫审计）。

    边界：必须在 (0, 1] 内，越界是**用法错误**（exit 2），不能静默取默认值。
    效果：它是真旋钮——同一对相似卡片，阈值放宽到 0.99 会消音，默认 0.85 会报。
    """
    problems = []
    base = "铁王座在君临，龙石岛在海上，北境有长城。" * 12
    near = base[:-40] + "最后一句不一样，再补一点点东西。"
    tmp, world = _temp_world("canonlint-dup-", {
        "one": _card("one", body=base),
        "two": _card("two", body=near),
    })
    with tmp:
        code, out, _ = _judge(world)
        if "CA201" not in out:
            problems.append(f"相似正文没报 CA201：\n{out.strip()}")
        code, out, _ = _judge(world, "--dup-threshold", "0.99")
        if "CA201" in out:
            problems.append("阈值放宽到 0.99 之后仍在报 CA201（旋钮没接上）")
        if code != 0:
            problems.append(f"提高阈值后应当通过（exit 0），实际 {code}")
        for bad in ("0", "-0.1", "1.5", "nan"):
            code, _, err = _judge(world, "--dup-threshold", bad)
            if code != 2:
                problems.append(f"--dup-threshold {bad} 应当 exit 2（用法错误），实际 {code}")
            if "dup-threshold" not in err:
                problems.append(f"--dup-threshold {bad} 的报错没点名参数：{err.strip()[:120]}")
        # 边界值 1.0 是合法的（只有完全一样才报）
        code, _, err = _judge(world, "--dup-threshold", "1")
        if code == 2:
            problems.append(f"--dup-threshold 1 是合法边界，不该当用法错误：{err.strip()[:120]}")
    return problems


def check_impact_reports_are_well_formed() -> list[str]:
    """`--impact` 的输出要说实话（评审 §9：CA504 没有守卫审计）。

    - 悬空的主体：不崩，下游为空；
    - 主体不在自己的下游（环里也不行——环由 CA502 单独报）；
    - 两跳闭包要跨得过去，且按层序降序；
    - 报告不影响退出码（它是报告，不是判定）。
    """
    problems = []
    tmp, world = _temp_world("canonlint-impact-", {
        "a": _card("a", extra="layer: core\n"),
        "b": _card("b", extra="layer: detail\ndepends_on: [{id: a, kind: fiscal, critical: true}]\n"),
        "c": _card("c", extra="layer: flavor\ndepends_on: [{id: b, kind: fiscal, critical: true}]\n"),
        "loop1": _card("loop1", extra="depends_on: [{id: loop2, kind: fiscal, critical: true}]\n"),
        "loop2": _card("loop2", extra="depends_on: [{id: loop1, kind: fiscal, critical: true}]\n"),
    })
    with tmp:
        code, out, _ = _judge(world, "--impact", "a", "--json")
        data = json.loads(out)
        reports = {r["subject"]: r for r in data["reports"]}
        if "a" not in reports:
            problems.append(f"--impact a 没给出报告：{data.get('reports')}")
        else:
            got = reports["a"]["downstream"]
            if set(got) != {"b", "c"}:
                problems.append(f"两跳闭包不对：{got}")
            if got != ["b", "c"]:
                problems.append(f"下游没按层序降序（core 在前）：{got}")
        code_without, _, _ = _judge(world, "--json")
        if code != code_without:
            problems.append(f"报告本身不该影响退出码：带 --impact 是 {code}，不带是 {code_without}")

        code, out, _ = _judge(world, "--impact", "loop1", "--json")
        reports = {r["subject"]: r for r in json.loads(out)["reports"]}
        if "loop1" in reports and "loop1" in reports["loop1"]["downstream"]:
            problems.append(f"环里把主体列进了自己的下游：{reports['loop1']['downstream']}")

        code, out, _ = _judge(world, "--impact", "根本没有这个条目", "--json")
        reports = {r["subject"]: r for r in json.loads(out)["reports"]}
        r = reports.get("根本没有这个条目")
        if r is None:
            problems.append("悬空主体没有报告（应当给一份空下游，不是崩）")
        elif r["downstream"]:
            problems.append(f"悬空主体的下游应当是空的，实际 {r['downstream']}")
        if code != code_without:
            problems.append(f"悬空主体不该影响退出码：带 --impact 是 {code}，不带是 {code_without}")
    return problems


def check_every_relation_reference_is_checked() -> list[str]:
    """契约列过的每一种关系，悬空引用都要报 CA401——不管语义归哪一层管。

    生产关系（owns / controls / extracts / coerces / legitimizes / owes）的规则住在
    classlint，但「引用指向不存在的 id」是结构问题：从前这六种字段一条都不查，
    于是 `owns: [幽灵]` 在 canonlint 里完全隐形（只在 classlint 那边有 CL105）。

    两处被评审抓住过的洞，这里一并堵掉：
      · 清单不许手写——上一版手写了五个家族、漏掉 `owes`，于是「删掉 owes 的检查」
        这个变异全绿。现在样本表的键必须**等于**契约的关系名全集，契约加一个名字
        而这里没跟上，本锁直接红。
      · 不许以「它有专属检查」为由把某个名字排除在覆盖之外——上一版把
        `conflicts_with` 排除掉，注释说它有专属检查，实际它的唯一存在性检查就在
        被锁的那个函数里，删掉它六套全绿（评审 blocker）。
    """
    problems = []
    contract = json.loads((ROOT / "world.schema.json").read_text(encoding="utf-8"))
    declared = set(contract["x-relation-vocabulary"]["names"])
    # 每种关系「写一条合法但悬空的边」的写法。形状必须合法，否则先报形状错、边不进图，
    # 测到的就不是「悬空引用有没有被查」了。
    well_formed = {
        "canon_refs": "canon_refs:\n  - ghost-x\n",
        "conflicts_with": "conflicts_with:\n  - id: ghost-x\n",
        "depends_on": "depends_on:\n  - id: ghost-x\n    kind: economy\n    critical: true\n",
        "exchanges_with": "exchanges_with:\n  - id: ghost-x\n",
        "derives_legitimacy_from": "derives_legitimacy_from:\n  - ghost-x\n",
        "owns": "owns:\n  - ghost-x\n",
        "controls": "controls:\n  - ghost-x\n",
        "extracts": "extracts:\n  - ghost-x\n",
        "coerces": "coerces:\n  - ghost-x\n",
        "legitimizes": "legitimizes:\n  - ghost-x\n",
        "owes": "owes:\n  - ghost-x\n",
    }
    if set(well_formed) != declared:
        return [f"本锁的样本表与契约的关系名不一致：多 {sorted(set(well_formed) - declared)}，"
                f"少 {sorted(declared - set(well_formed))}（契约加了名字就要在这里补一条合法写法）"]
    for fam in sorted(declared) + ["mentor-of"]:
        if fam == "mentor-of":
            # 自由档：作者自定义的关系名，指向不存在的 id 同样是结构问题。以前 canonlint
            # 只查契约登记过的那几种，而 classlint 的 CL105 查全部——同一份数据两个引擎
            # 两种结论，且这处差异没在任何地方登记（评审 low）。
            styles = [("规范形", "relations:\n  - type: mentor-of\n    target: ghost-x\n")]
        else:
            styles = [("具名字段", well_formed[fam]),
                      ("规范形", f"relations:\n  - type: {fam}\n    target: ghost-x\n"
                                 + ("    kind: economy\n    critical: true\n"
                                    if fam == "depends_on" else ""))]
        for style, extra in styles:
            # 模板里自带空的 canon_refs/conflicts_with；这两族要自己写一条，就得把
            # 模板的同名行让开（否则同键两遍，YAML 丢掉一条，测到的是重复键）。
            twin = {"canon_refs": "conflicts_with: []\n",
                    "conflicts_with": "canon_refs: []\n"}.get(fam, "")
            tmp, world = _temp_world("canonlint-relref-",
                                     {"a-node": _card("a-node", twin + extra,
                                                      template_relations=not twin)})
            with tmp:
                code, out, _ = _judge(world)
                if "[CA401]" not in out or "ghost-x" not in out:
                    problems.append(f"{fam}（{style}）的悬空引用没报 CA401：{out.strip()!r}")
                if "CA112" in out:
                    problems.append(f"{fam}（{style}）的夹具自己写重了键，测的不是悬空引用："
                                    f"{out.strip()!r}")
    # 反面：目标存在时不许报（别把「有这条边」本身当成错）
    tmp, world = _temp_world("canonlint-relref-ok-", {
        "a-node": _card("a-node", "owns:\n  - b-node\n"),
        "b-node": _card("b-node"),
    })
    with tmp:
        code, out, _ = _judge(world)
        if "CA401" in out:
            problems.append(f"目标存在时不该报 CA401：{out.strip()!r}")
    return problems


def check_near_miss_names_are_judged_under_the_canonical_name() -> list[str]:
    """拼错一个字符的关系名，边要**真的按规范名进图**，而不是只发一句提示。

    评审 blocker：CA110 的文案说「已按归一化后的规范名判定该边」，实现里这条边却以
    拼错的名字留在图里，于是谁都不判它——漏判 CA401/CA501/CA504、冤报 CA302/CA503。
    另有第二处缝：契约 `x-relation-vocabulary.value.accept` 登记的历史拼法（`canon-ref:`）
    写成字段名时被报 CA106「未定义字段」，同一张卡在两个引擎里一个硬错误、一个整族规则
    静默失效。
    """
    problems = []
    cases = [
        # (说明, 卡片里写的关系, 期望出现, 期望不出现)
        ("近失：depend_on", "relations:\n  - type: depend_on\n    target: ghost-x\n"
                            "    kind: fiscal\n    critical: true\n",
         ["CA110", "CA401"], []),
        ("近失：分隔符风格不同（depends-onn）",
         "relations:\n  - type: depends-onn\n    target: ghost-x\n"
         "    kind: fiscal\n    critical: true\n", ["CA110", "CA401"], []),
        ("近失：extractss", "relations:\n  - type: extractss\n    target: ghost-x\n",
         ["CA110", "CA401"], []),
        # 真正的新词必须继续 fail-open：不提示、不换名、原样保留
        ("自由档：mentor-of", "relations:\n  - type: mentor-of\n    target: b-node\n",
         [], ["CA110"]),
        # 契约登记的拼法：认下，不冤报 CA106
        ("登记拼法：canon-ref:", "canon-ref:\n  - b-node\n", [], ["CA106"]),
        ("登记拼法：depends-on:", "depends-on:\n  - id: b-node\n    kind: fiscal\n"
                                   "    critical: true\n", [], ["CA106"]),
    ]
    for label, extra, must, must_not in cases:
        tmp, world = _temp_world("canonlint-nearmiss-", {
            "a-node": _card("a-node", extra), "b-node": _card("b-node")})
        with tmp:
            _, out, _ = _judge(world)
            for token in must:
                if token not in out:
                    problems.append(f"{label}：应当出现 {token}\n{out.strip()}")
            for token in must_not:
                if token in out:
                    problems.append(f"{label}：不该出现 {token}\n{out.strip()}")
    # 换名必须真的影响**判定**，不能只影响一条提示。两个只有换名才会正确的结论：
    #   (a) 承重墙的 depends_on 义务：near-miss 的边也算数（否则 CA302 冤报「缺 depends_on」）
    #   (b) 层级方向：near-miss 的边照样要过 CA501（否则漏判）
    tmp, world = _temp_world("canonlint-nearmiss-ca302-", {
        "a-node": _card("a-node", "relations:\n  - type: depend_on\n    target: b-node\n"
                                   "    kind: fiscal\n    critical: true\n",
                        load_bearing=True).replace("load_bearing: true\n",
                                                   "load_bearing: true\nlayer: political\n"),
        "b-node": _card("b-node"),
    })
    with tmp:
        _, out, _ = _judge(world)
        if "CA302" in out:
            problems.append(f"near-miss 的 depends_on 没算数（CA302 冤报缺 depends_on）：\n{out.strip()}")
    tmp, world = _temp_world("canonlint-nearmiss-ca501-", {
        "a-node": _card("a-node", "relations:\n  - type: depend_on\n    target: b-node\n"
                                   "    kind: fiscal\n    critical: true\n",
                        load_bearing=True).replace("load_bearing: true\n",
                                                   "load_bearing: true\nlayer: military\n"),
        "b-node": _card("b-node").replace("layer: ", "").replace(
            "type: location", "type: location\nlayer: political"),
    })
    with tmp:
        _, out, _ = _judge(world)
        if "CA501" not in out:
            problems.append(f"near-miss 的 depends_on 漏判层级方向（该报 CA501）：\n{out.strip()}")
    # 契约认证的字段名拼法：不只是「不报 CA106」，边必须**真的建出来**（悬空才看得见）
    # 注意不能走 `_card(extra)`：它自带 `canon_refs: []`，而字段名拼法的查找是
    # 「文档序里第一个对应的键」，先出现的空列表会赢。这里替换掉那一行。
    tmp, world = _temp_world("canonlint-attested-", {
        "a-node": _card("a-node").replace("canon_refs: []", "canon-ref:\n  - ghost-x"),
        "b-node": _card("b-node")})
    with tmp:
        _, out, _ = _judge(world)
        if "CA401" not in out:
            problems.append(f"`canon-ref:` 字段名认下了，边却没建（漏掉 CA401）：\n{out.strip()}")
    # CA103：文案说「须为 YYYY-MM-DD」，那 ISO 基本格式与周历格式就不能放行
    for bad in ('"20261015"', '"2026-W42-6"', '"2026-02-30"', '"2026-1-5"'):
        tmp, world = _temp_world("canonlint-date-", {"a-node": _card("a-node")})
        with tmp:
            card = world / "entries" / "a-node.md"
            card.write_text(card.read_text(encoding="utf-8").replace(
                "date: 2026-01-01", f"date: {bad}"), encoding="utf-8")
            _, out, _ = _judge(world)
            if "CA103" not in out:
                problems.append(f"date={bad} 应当报 CA103（契约 pattern 是 ^\\d{{4}}-\\d{{2}}-\\d{{2}}$）")
    # CA103 反面：YAML 原生日期与规范字符串都合法
    for good in ("date: 2026-01-01", "date: '2026-01-01'"):
        tmp, world = _temp_world("canonlint-dateok-", {"a-node": _card("a-node")})
        with tmp:
            card = world / "entries" / "a-node.md"
            card.write_text(card.read_text(encoding="utf-8").replace(
                "date: 2026-01-01", good), encoding="utf-8")
            _, out, _ = _judge(world)
            if "CA103" in out:
                problems.append(f"{good} 不该报 CA103：{out.strip()}")
    return problems


def check_econ_figures_are_shape_checked() -> list[str]:
    """econ 扩展包的 CA601 必须有**意图断言**（评审：`figures` 非映射 / `unit` 非字符串两条守卫没锁）。

    `tests/world-econ` 只覆盖了「缺 unit」与「value 非数字」，把 `.git` 之外的两条分支删掉
    照样全绿。这里直接构造那两种形态。
    """
    problems = []
    cases = [
        ("figures 不是映射", "figures: 12\n", "figures 必须是映射"),
        ("unit 不是字符串", "figures:\n  grain:\n    value: 100\n    unit: 123\n",
         "必须是非空字符串"),
        ("unit 是 bool", "figures:\n  grain:\n    value: 100\n    unit: true\n",
         "必须是非空字符串"),
        ("unit 是空串", "figures:\n  grain:\n    value: 100\n    unit: \"\"\n",
         "必须是非空字符串"),
        ("value 是 nan", "figures:\n  grain:\n    value: .nan\n    unit: 石\n",
         "不是有限数字"),
        ("value 是 inf", "figures:\n  grain:\n    value: .inf\n    unit: 石\n",
         "不是有限数字"),
        ("value 为负", "figures:\n  grain:\n    value: -5\n    unit: 石\n",
         "不能为负"),
        ("零人口有军队", "figures:\n  population:\n    value: 0\n    unit: 人\n"
                    "  military_size:\n    value: 100000\n    unit: 人\n",
         "零人口不可能供养军队"),
    ]
    for label, extra, want in cases:
        tmp, world = _temp_world("canonlint-econ-", {"a-node": _card("a-node", extra)})
        with tmp:
            _, out, _ = _judge(world, "--pack", "econ")
            rule = "CA602" if want == "零人口不可能供养军队" else "CA601"
            if rule not in out or want not in out:
                problems.append(f"{label}：应当报 {rule}（含「{want}」）\n{out.strip()}")
    # 反面：合法 figures 一条都不许报
    tmp, world = _temp_world("canonlint-econ-ok-", {
        "a-node": _card("a-node", "figures:\n  grain:\n    value: 100\n    unit: 石/亩\n")})
    with tmp:
        _, out, _ = _judge(world, "--pack", "econ")
        if "CA601" in out:
            problems.append(f"合法的 figures 不该报 CA601：{out.strip()}")
    return problems


def check_non_world_directory_is_a_usage_error() -> list[str]:
    """指错目录要直说「这不是世界」，而不是把每篇文档都当坏条目（评审：752 条假错误）。"""
    problems = []
    tmp = tempfile.TemporaryDirectory(prefix="canonlint-notworld-")
    with tmp:
        root = Path(tmp.name)
        (root / "docs").mkdir()
        (root / "docs" / "说明.md").write_text("# 说明\n\n没有 frontmatter。\n",
                                                encoding="utf-8")
        (root / "README.md").write_text("# 这是仓库说明\n", encoding="utf-8")
        code, out, err = _judge(root)
        if code != 2:
            problems.append(f"不是世界的目录应当给用法错误（exit 2），实际 exit {code}")
        if "CA1" in out:
            problems.append("它还是把文档当条目审了（应当直接说指错目录）")
        if "不像一个世界" not in err:
            problems.append(f"stderr 没说清为什么（实际：{err.strip()!r}）")
    # 反面：根目录里真有一篇条目卡的扁平世界照旧能审。
    # （手工铺：`_temp_world` 会先建出 `entries/`，拿它测扁平世界测的不是扁平。）
    tmp2 = tempfile.TemporaryDirectory(prefix="canonlint-flat-")
    with tmp2:
        flat = Path(tmp2.name)
        (flat / "solo.md").write_text(_card("solo"), encoding="utf-8")
        code, out, _ = _judge(flat)
        if code != 0:
            problems.append(f"扁平世界（根目录直接放条目）反而被拒了：exit {code}")
    return problems


def check_root_cards_survive_an_entries_dir() -> list[str]:
    """有 `entries/` 时，根目录级的卡片照样要进审计（评审 blocker：整批静默蒸发）。

    判据用「这张卡有没有留下痕迹」，不用退出码——一张卡被丢掉时退出码仍是 0，
    所以让它带一条必然的发现（悬空引用），蒸发才看得见。
    """
    problems = []
    tmp = tempfile.TemporaryDirectory(prefix="canonlint-rootcard-")
    with tmp:
        root = Path(tmp.name)
        (root / "entries").mkdir()
        (root / "entries" / "resident.md").write_text(_card("resident"), encoding="utf-8")
        # 根目录级的卡片，带一条悬空引用：它收没被收进来，由这条 CA401 证明
        (root / "gray-harbor.md").write_text(
            _card("gray-harbor", "canon_refs: [ghost-nowhere]\n"), encoding="utf-8")
        # 散文文档不是卡片，不许被当成坏条目
        (root / "README.md").write_text("# 这是世界说明\n\n没有 frontmatter。\n",
                                        encoding="utf-8")
        code, out, _ = _judge(root)
        if "gray-harbor.md" not in out:
            problems.append(
                f"有 entries/ 时根目录的卡片整个消失了（退出码 {code}）：{out.strip()!r}")
        if "ghost-nowhere" not in out:
            problems.append("根目录卡片上的悬空引用没被报出来")
        if "README.md" in out:
            problems.append(f"根目录的散文文档被当成条目审了：{out.strip()!r}")
    # 坏掉的根级卡片必须被看见——不能拿「解析成功」当收不收的判据
    tmp2 = tempfile.TemporaryDirectory(prefix="canonlint-rootcardbad-")
    with tmp2:
        root = Path(tmp2.name)
        (root / "entries").mkdir()
        (root / "entries" / "resident.md").write_text(_card("resident"), encoding="utf-8")
        (root / "broken.md").write_text("---\ntitle: 没有 id\n---\n\n正文\n", encoding="utf-8")
        code, out, _ = _judge(root)
        if "broken.md" not in out:
            problems.append(f"frontmatter 坏的根级卡片被静默跳过了：{out.strip()!r}")
        if code == 0:
            problems.append("根级坏卡片在，退出码不该是 0")
    return problems


def check_shadowed_entries_still_get_their_refs_checked() -> list[str]:
    """id 重复时，被遮蔽的那一份自己的引用也要检查（它只是没进索引，不是没写错）。

    以前只查索引里的条目，于是「世界上摆着一条指向不存在条目的边」可以一直没人报；
    CA105 的文案甚至把这当成既定事实写出来了（「其引用不被检查」）。这里钉住：
    遮蔽者会被 **CA114** 报出来（重复 id 的专用编号；CA105 只管 id 语法），
    被遮蔽者那条悬空引用照样报 CA401。
    """
    problems = []
    tmp, world = _temp_world("canonlint-shadow-", {
        "first": _card("dup-id"),
        "second": _card("dup-id", "canon_refs:\n  - ghost-nowhere\n"),
    })
    with tmp:
        code, out, err = _judge(world)
        if code != 1:
            problems.append(f"重复 id + 悬空引用应当报错（exit 1），实际 exit {code}")
        rules = sorted({line.split("]")[0][1:] for line in out.splitlines()
                        if line.startswith("[CA")})
        if "CA114" not in rules:
            problems.append(f"重复 id 没报 CA114（实际报出 {rules}）")
        if "CA401" not in rules:
            problems.append(f"被遮蔽条目里的悬空引用没报 CA401（实际报出 {rules}）")
        if "ghost-nowhere" not in out:
            problems.append("报告里没点名那条悬空引用指向谁")
    return problems


def check_bad_id_syntax_reports_ca105() -> list[str]:
    """`id: Bad_ID` 必须报 CA105——这条以前**没有锁**（评审 N3）。

    老锁只断言过「输出里有 CA105」，而 CA105 当时还兼着「id 重复」的意思，两条卡撞 id
    就能让它通过；把语法守卫改成 `if False` 之后五套照样全绿。现在重复 id 归 CA114，
    这条断言才真的钉在语法上。
    """
    problems = []
    tmp, world = _temp_world("canonlint-bad-id-", {"solo": _card("Bad_ID")})
    with tmp:
        _, out, _ = _judge(world)
        if "CA105" not in out:
            problems.append(f"非法的 id 语法没报 CA105：\n{out.strip()}")
        if "Bad_ID" not in out:
            problems.append("CA105 的文案没点名那个非法 id")
    # 反面：合法 id 一条都不许报
    tmp, world = _temp_world("canonlint-good-id-", {"solo": _card("good-id-2")})
    with tmp:
        _, out, _ = _judge(world)
        if "CA105" in out:
            problems.append(f"合法的 id 不该报 CA105：\n{out.strip()}")
    return problems


def check_supersede_pairs_are_not_duplicates() -> list[str]:
    """降级承接对（archived + 承接者）正文相似是**要求的**，CA201 不能报（评审 F9）。

    承接条目按定义要接着旧条目写，两份正文天然高度相似。这条豁免以前不存在，
    于是每一对正常的降级都会在 `--strict` 下把世界判红。
    """
    problems = []
    tmp, world = _temp_world("canonlint-supersede-", {
        "old-node": _card("old-node", "superseded_by: new-node\n", status="archived"),
        "new-node": _card("new-node", "canon_refs:\n  - old-node\n"),
    })
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"承接对把 traceback 写到了 stderr：\n{err}")
        if "CA201" in out:
            problems.append("降级承接对被判成疑似重复（CA201 应当豁免）：\n" + out)
        # 对照组：没有承接关系的两份相同正文必须照报
        tmp2, world2 = _temp_world("canonlint-dup-", {
            "a-node": _card("a-node"), "b-node": _card("b-node")})
        with tmp2:
            code2, out2, err2 = _judge(world2)
            if err2:
                problems.append(f"对照组把 traceback 写到了 stderr：\n{err2}")
            if "CA201" not in out2:
                problems.append("没有承接关系的两份相同正文漏报了 CA201：\n" + out2)
    return problems


def check_dup_threshold_range_is_usage_error() -> list[str]:
    """`--dup-threshold` 越界必须是用法错误（退出码 2），不能静默换行为（评审 F12）。

    `--dup-threshold 2.5` 以前让 CA201 永不触发——一条规则被一个参数悄悄关掉，
    而退出码仍是 0。
    """
    problems = []
    tmp, world = _temp_world("canonlint-threshold-", {
        "a-node": _card("a-node"), "b-node": _card("b-node")})
    with tmp:
        for bad in ("2.5", "0", "-1"):
            code, out, err = _judge(world, "--dup-threshold", bad)
            if code != 2:
                problems.append(f"--dup-threshold {bad} 应返回 2（用法错误），实际 {code}")
            if "dup-threshold" not in err:
                problems.append(f"--dup-threshold {bad} 的 stderr 没说清问题：{err!r}")
        for good in ("0.85", "1.0"):
            code, out, err = _judge(world, "--dup-threshold", good)
            if code != 0 or "CA201" not in out:
                problems.append(f"--dup-threshold {good} 是合法值，应当正常判定"
                                f"（rc={code}）：\n{out}")
    return problems


def check_impact_never_lists_the_subject() -> list[str]:
    """`--impact x` 只列别的东西；落在环里时也不把自己列进下游（评审 F6）。"""
    problems = []
    dep = ("relations:\n  - type: depends_on\n    target: {other}\n"
           "    kind: resource\n    critical: true\n")
    tmp, ring = _temp_world("canonlint-impact-ring-", {
        "x-node": _card("x-node", dep.format(other="y-node")),
        "y-node": _card("y-node", dep.format(other="x-node")),
    })
    with tmp:
        code, out, err = _judge(ring, "--impact", "x-node", "--json")
        if err:
            problems.append(f"--impact 把 traceback 写到了 stderr：\n{err}")
        else:
            for r in json.loads(out)["reports"]:
                if r["subject"] in r["downstream"]:
                    problems.append(f"主体 {r['subject']} 出现在自己的下游里：{r['downstream']}")
        # 链上：x ← y ← z
        tmp2, chain = _temp_world("canonlint-impact-chain-", {
            "x-node": _card("x-node"),
            "y-node": _card("y-node", dep.format(other="x-node")),
            "z-node": _card("z-node", dep.format(other="y-node")),
        })
        with tmp2:
            code, out, err = _judge(chain, "--impact", "x-node", "--json")
            if err:
                problems.append(f"--impact 链上把 traceback 写到了 stderr：\n{err}")
            else:
                got = json.loads(out)["reports"][0]["downstream"]
                if sorted(got) != ["y-node", "z-node"]:
                    problems.append(f"链上的下游闭包应为 ['y-node', 'z-node']，实际 {got}")
    return problems


def check_advisory_rules_do_not_gate_drafts() -> list[str]:
    """draft 提到了承重墙关键词，在 `--strict` 下也必须能提交（评审 F8）。

    CA301 是「请考虑声明」的提示；`--strict` 把 warning 当失败，于是以前任何写到
    「政治/经济」的草稿都无法提交——审计器替作者做了决定（§5.3 明说不替）。定档
    （trial/canon）之后同一句话必须照报。
    """
    problems = []
    kw = "本条目涉及政治与经济结构。" + "正文" * 100
    tmp, draft = _temp_world("canonlint-ca301-draft-", {
        "a-node": _card("a-node", status="draft", body=kw)})
    with tmp:
        code, out, err = _judge(draft, "--strict")
        if err:
            problems.append(f"--strict 把 traceback 写到了 stderr：\n{err}")
        if code != 0:
            problems.append(f"draft 提到关键词时 --strict 应放行，实际退出码 {code}：\n{out}")
        if "CA301" in out:
            problems.append("CA301 不该对 draft 报（draft 还没到做决定的时候）：\n" + out)
    tmp2, canon = _temp_world("canonlint-ca301-canon-", {
        "a-node": _card("a-node", status="canon", body=kw)})
    with tmp2:
        code, out, err = _judge(canon, "--strict")
        if "CA301" not in out:
            problems.append("定档条目提到关键词却漏报了 CA301：\n" + out)
        if code != 1:
            problems.append(f"定档条目 + --strict 应返回 1，实际 {code}")
    # #38：军事/财政同义词也要触发 CA301（以前靠漏词逃逸）。
    for word in ("军事", "财政", "赋税", "军饷", "俸禄"):
        body = f"本条目涉及{word}收支结构。" + "正文" * 100
        tmp3, world = _temp_world(f"canonlint-ca301-{word}-", {
            "a-node": _card("a-node", status="canon", body=body)})
        with tmp3:
            _, out, _ = _judge(world)
            if "CA301" not in out or word not in out:
                problems.append(f"关键词「{word}」应触发 CA301：\n{out}")
    # 已声明 load_bearing 的卡不再提示
    tmp4, world = _temp_world("canonlint-ca301-declared-", {
        "a-node": _card("a-node", (
            "load_bearing: true\nlayer: military\n"
            "depends_on:\n  - id: b-node\n    kind: resource\n    critical: true\n"
        ), load_bearing=True, status="canon", body="本条目涉及军饷。" + "正文" * 100).replace(
            "type: location", "type: faction"),
        "b-node": _card("b-node", "load_bearing: true\nlayer: resource\n",
                        load_bearing=True, body="资源节点" + "正文" * 100),
    })
    with tmp4:
        _, out, _ = _judge(world)
        if "CA301" in out:
            problems.append(f"已声明 load_bearing 的卡不该被 CA301 提示：\n{out}")
    return problems


def check_mutual_exchange_is_not_a_perpetual_motion() -> list[str]:
    """「互相交换」和「互相供养」必须能分开写：交换不报 CA502，供养照报。

    CA502 的判词是「物质族成环 = 永动机」：a 靠 b、b 靠 a 的物质供给，这个环里没有
    外部底座。但两个真实条目互相交换（分工、互市、贸易）是**常见的真实结构**，以前
    没有任何合法写法——写成两条 depends_on 就被判永动机，于是要么改模型要么关规则
    （评审里用户的原话：「物质依赖是什么」）。新增 exchanges_with 之后：交换是流通
    关系，不进 CA502 的子图；真的要表达「谁断了谁都塌」仍然写 depends_on，照报。
    """
    problems = []
    # 对照组：互相供养（两条 depends_on）——环里没有外部底座，CA502 必须报
    mutual = {
        "a-node": _card("a-node", "layer: economy\ndepends_on:\n  - {id: b-node, kind: production, critical: true}\n"),
        "b-node": _card("b-node", "layer: economy\ndepends_on:\n  - {id: a-node, kind: production, critical: true}\n"),
    }
    tmp, world = _temp_world("canonlint-mutual-dep-", mutual)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"互相供能把 traceback 写到了 stderr：\n{err}")
        if "CA502" not in out:
            problems.append("互相供养（两条 depends_on）漏报了 CA502：\n" + out)
    # 实验组：互相交换（exchanges_with）+ 各自有外部底座——不报 CA502，整份通过
    exchange = {
        "base-node": _card("base-node", "layer: resource\n"),
        "a-node": _card("a-node", "layer: economy\nexchanges_with:\n  - {id: b-node, what: 粮食}\ndepends_on:\n  - {id: base-node, kind: resource, critical: true}\n"),
        "b-node": _card("b-node", "layer: economy\nexchanges_with:\n  - {id: a-node, what: 布匹}\ndepends_on:\n  - {id: base-node, kind: resource, critical: true}\n"),
    }
    tmp2, world2 = _temp_world("canonlint-mutual-exchange-", exchange)
    with tmp2:
        code2, out2, err2 = _judge(world2)
        if err2:
            problems.append(f"互相交换把 traceback 写到了 stderr：\n{err2}")
        if "CA502" in out2:
            problems.append("互相交换被判成永动机（交换是流通关系，不是承重）：\n" + out2)
        if code2 != 0:
            problems.append(f"互相交换 + 各自有底座应通过，实际退出码 {code2}：\n{out2}")
    # 悬空的交换对象要报（新接线的关系名不能对引用检查隐形）
    dangling = {"a-node": _card("a-node", "exchanges_with:\n  - ghost-node\n")}
    tmp3, world3 = _temp_world("canonlint-exchange-dangling-", dangling)
    with tmp3:
        code3, out3, err3 = _judge(world3)
        if err3:
            problems.append(f"悬空 exchanges_with 把 traceback 写到了 stderr：\n{err3}")
        if "CA401" not in out3:
            problems.append("exchanges_with 指向不存在的 id 却没报 CA401：\n" + out3)
    return problems


def _rules(out: str) -> set[str]:
    """输出里出现过的规则号（用于比较两种写法的判定集合）。"""
    return set(re.findall(r"\[(CA\d+)\]", out))


def check_legitimacy_is_its_own_relation_not_a_material_kind() -> list[str]:
    """「名分依据」必须是一个关系名，不再是 `depends_on` 的 kind 值（拆分 `depends_on`）。

    以前一个词装两种意思：`depends_on` + `kind: legitimacy` 表示「我的说法以它为依据」，
    而 CA501/CA502/CA503 的门禁是 `kind not in 物质族: continue`——于是「算不算承重」
    由副标签决定，`legitimacy` 还和物资挤在同一张类别表里。拆开之后门禁看**关系名**：
    `derives_legitimacy_from` 不进任何承重图，`depends_on` 只有物资 kind 才算。
    （CA503「承重墙要有物质来源」两种写法都照报：名分不是物资来源。）
    """
    problems = []
    # 实验组：新关系名——承重墙从名分来源取得正当性，不构成物质依赖
    new_form = {
        "church-node": _card("church-node", "layer: ideology\n"),
        "a-node": _card("a-node", "layer: political\nderives_legitimacy_from:\n  - church-node\n",
                        load_bearing=True),
    }
    tmp, world = _temp_world("canonlint-legit-relation-", new_form)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"derives_legitimacy_from 把 traceback 写到了 stderr：\n{err}")
        carried = _rules(out) & {"CA501", "CA502"}
        if carried:
            problems.append(
                "名分依据被判成了承重依赖（它不该进 CA501/CA502 的图）：\n" + out)
        if "CA110" in out:
            problems.append("契约认得的规范名被当成拼写近失报了 CA110：\n" + out)
    # 旧写法：kind: legitimacy——同一句话，判定集合必须完全一致（迁移不改结论）
    old_form = {
        "church-node": _card("church-node", "layer: ideology\n"),
        "a-node": _card(
            "a-node",
            "layer: political\ndepends_on:\n  - {id: church-node, kind: legitimacy, critical: true}\n",
            load_bearing=True),
    }
    tmp2, world2 = _temp_world("canonlint-legit-kind-", old_form)
    with tmp2:
        code2, out2, err2 = _judge(world2)
        if err2:
            problems.append(f"旧写法 kind: legitimacy 把 traceback 写到了 stderr：\n{err2}")
        carried2 = _rules(out2) & {"CA501", "CA502"}
        if carried2:
            problems.append("旧写法 kind: legitimacy 被判成了承重依赖：\n" + out2)
        if code != code2 or _rules(out) != (_rules(out2) - {"CA111"}):
            problems.append(
                "两种写法（关系名 / 旧的 kind 值）判定不一致——迁移必须不改结论：\n"
                f"新关系名 rc={code} {sorted(_rules(out))}\n"
                f"旧 kind   rc={code2} {sorted(_rules(out2))}")
        if "CA111" not in out2:
            problems.append("旧写法没有提示作者迁移（CA111 必须报，废弃不许静默）：\n" + out2)
    # 物质路径不受影响：真的靠物资活着仍然要判
    material = {
        "mine-node": _card("mine-node", "layer: resource\n"),
        "b-node": _card("b-node", "layer: economy\ndepends_on:\n  - {id: mine-node, kind: resource, critical: true}\n"),
    }
    tmp3, world3 = _temp_world("canonlint-legit-material-", material)
    with tmp3:
        code3, out3, err3 = _judge(world3)
        if err3:
            problems.append(f"物质依赖把 traceback 写到了 stderr：\n{err3}")
        if code3 != 0:
            problems.append(f"正常的物质依赖不该报错，实际退出码 {code3}：\n{out3}")
    return problems


def check_legitimacy_edge_checks_existence_only() -> list[str]:
    """名分来源只查**存在性**：悬空要报，对象退休了不报（与 canon_refs 不同）。

    名分是「说法以它为依据」，不是「靠它活着」——来源条目归档不等于这个说法失效，
    所以状态不参与判定。这条同时钉住新接线没有被顺手接进 CA402/CA405。
    """
    problems = []
    dangling = {
        "a-node": _card("a-node", "derives_legitimacy_from:\n  - ghost-node\n"),
    }
    tmp, world = _temp_world("canonlint-legit-dangling-", dangling)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"悬空名分来源把 traceback 写到了 stderr：\n{err}")
        if "CA401" not in out:
            problems.append("名分来源指向不存在的 id 却没报 CA401：\n" + out)
    retired = {
        "old-doctrine": _card("old-doctrine", status="archived"),
        "a-node": _card("a-node", "derives_legitimacy_from:\n  - old-doctrine\n"),
    }
    tmp2, world2 = _temp_world("canonlint-legit-archived-", retired)
    with tmp2:
        code2, out2, err2 = _judge(world2)
        if err2:
            problems.append(f"名分来源退休把 traceback 写到了 stderr：\n{err2}")
        if _rules(out2) & {"CA402", "CA405"}:
            problems.append(
                "名分来源归档被判成引用失效（名分只查存在性，不看状态）：\n" + out2)
    return problems


def check_experimental_kinds_are_still_exempt() -> list[str]:
    """`x-` 实验 kind 继续豁免 CA501/CA502，但不豁免 CA503 的「物质来源」义务。

    三个演示世界里有四条承重边用 `x-faith-engineering` / `x-will-binding` /
    `x-faith` / `x-magic-logistics` 当 kind。门禁从「看 kind」改成「看关系名」之后，
    它们仍然写成 `depends_on`，只是 kind 落不到物资类别上——层级方向（CA501）与物质
    成环（CA502）照旧不判；而 CA503「承重墙要有一条物质族 critical 依赖」本来就是
    在问「你的物质来源在哪」，只写实验 kind 就是没写，报出来是对的（拆分前后一致）。
    """
    problems = []
    case = {
        "target-node": _card("target-node", "layer: production\n"),
        "a-node": _card("a-node",
                        "layer: military\ndepends_on:\n  - {id: target-node, kind: x-will-binding, critical: true}\n",
                        load_bearing=True),
    }
    tmp, world = _temp_world("canonlint-x-kind-", case)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"x- 实验 kind 把 traceback 写到了 stderr：\n{err}")
        carried = _rules(out) & {"CA501", "CA502"}
        if carried:
            problems.append(
                f"x- 实验 kind 被当成物质依赖判了 {sorted(carried)}（契约自由档要求豁免）：\n" + out)
        if "CA108" not in out:
            problems.append("x- 实验 kind 没有被记成实验值（CA108 info）：\n" + out)
        # 边仍然存在：不许因为 kind 不是物资就当作者没声明依赖
        if "CA302" in out:
            problems.append("x- 实验 kind 的边被当成了「没声明依赖」：\n" + out)
        # 但 CA503 不能被一起豁免掉：docstring 说「只写实验 kind 就是没写物质来源」，
        # 以前这条只断言了豁免，没断言义务还在——把 CA503 也 skip 掉照样绿（评审 low）。
        if "CA503" not in out:
            problems.append(
                "x- 实验 kind 不该豁免 CA503（承重墙仍要有一条物质族 critical 依赖）：\n" + out)
    return problems


def check_historical_event_cards_stay_silent() -> list[str]:
    """D9 硬要求：没有 when/event_kind 的史料事件卡，一条 CA7xx 都不许响。

    示例世界里那 27 张 type: event 卡（起源、改编、文献）不是流水事件；
    协议 1.1 的世界在 1.2 下必须仍然全绿。
    """
    problems = []
    # _card 固定 type: location；史料事件卡拿它的模板换个 type
    tmp, world = _temp_world("canonlint-hist-event-", {
        "old-lore": _card("old-lore", "").replace("type: location", "type: event"),
    })
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"史料事件卡把 traceback 写到了 stderr：\n{err}")
        if re.search(r"\[CA70[1-6]\]", out):
            problems.append(f"史料事件卡（无 when/event_kind）触发了流水规则：\n{out}")
        if code != 0:
            problems.append(f"纯史料事件卡的世界应当 exit 0，实际 {code}：\n{out}")
    return problems


def check_ledger_fail_open_without_when_sort() -> list[str]:
    """缺 when_sort = 全部时序/账平规则 fail-open（D2：不给就不参与时序判定）。

    一个 depends_on 指向「更晚」事件、客体没有来源的完整事件，只要没给
    when_sort，CA701/CA703 都必须静默——排不了序就猜一个顺序，比不判更坏。
    """
    problems = []
    cards = {
        "ghostless-item": _card("ghostless-item", ""),
        "ev-no-sort": _card("ev-no-sort", (
            "when: 某年\nevent_kind: transfer\n"
            "by:\n  - somebody\nto:\n  - somebody\nobject:\n  - ghostless-item\n"
            "depends_on:\n  - {id: ev-later, kind: resource, critical: false}\n"
        )).replace("type: location", "type: event"),
        "ev-later": _card("ev-later", (
            "when: 另一年\nevent_kind: create\nwhen_sort: 99\n"
            "object:\n  - ghostless-item\n"
        )).replace("type: location", "type: event"),
        "somebody": _card("somebody", ""),
    }
    tmp, world = _temp_world("canonlint-nosort-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"无 when_sort 的世界把 traceback 写到了 stderr：\n{err}")
        if re.search(r"\[CA70[1345]\]", out):
            problems.append(f"缺 when_sort 时 CA701/CA703/CA704/CA705 必须静默：\n{out}")
    return problems


def check_equal_sort_boundaries() -> list[str]:
    """when_sort 相等：CA701 用 ≤（并列合法），CA705 用严格 <（同刻不算死后）。"""
    problems = []
    cards = {
        "person-a": _card("person-a", ""),
        "thing-x": _card("thing-x", ""),
        "ev-a": _card("ev-a", (
            "when: 同年\nevent_kind: death\nwhen_sort: 5\nobject:\n  - person-a\n"
        )).replace("type: location", "type: event"),
        "ev-b": _card("ev-b", (
            "when: 同年\nevent_kind: move\nwhen_sort: 5\n"
            "by:\n  - person-a\nobject:\n  - thing-x\nto:\n  - person-a\n"
            "depends_on:\n  - {id: ev-a, kind: resource, critical: false}\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-eqsort-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"等值 when_sort 把 traceback 写到了 stderr：\n{err}")
        if "CA701" in out:
            problems.append(f"when_sort 相等不该报 CA701（规则是 ≤）：\n{out}")
        if "CA705" in out:
            problems.append(f"同刻死亡不算「死人做活事」（规则是严格更早）：\n{out}")
    return problems


def check_leg_shape_is_ca109_not_double_ca702() -> list[str]:
    """腿写坏形状报 CA109；这条腿算「声明过」，不叠 CA702。

    两种坏法都要锁（评审 I2）：`by: notalist`（不是列表）与 `by: [42]`
    （是列表但元素全坏）——后者过滤后 legs[leg] 为空，曾被当成「作者给了
    空列表」再叠一条 CA702，同一句话报两遍，且文案与事实不符。
    """
    problems = []
    cards = {
        "thing-x": _card("thing-x", ""),
        "keep-y": _card("keep-y", ""),
        # move 的必填腿是 object + to（都给了，不触发 CA702）；
        # by 不是必填腿，写坏形状只该报 CA109
        "ev-bad-shape": _card("ev-bad-shape", (
            "when: 某年\nevent_kind: move\nwhen_sort: 1\n"
            "by: notalist\nobject:\n  - thing-x\nto:\n  - keep-y\n"
        )).replace("type: location", "type: event"),
        # transfer 的 by 是必填腿：元素全坏的列表 = 声明过但取不出 id，
        # 只许报 CA109，不许再叠「是空列表」的 CA702
        "ev-bad-items": _card("ev-bad-items", (
            "when: 某年\nevent_kind: transfer\nwhen_sort: 2\n"
            "by:\n  - 42\nto:\n  - keep-y\nobject:\n  - thing-x\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legshape-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"坏形状腿把 traceback 写到了 stderr：\n{err}")
        if "CA109" not in out:
            problems.append(f"坏形状腿没报 CA109（形状坏掉不许静默）：\n{out}")
        if "CA702" in out:
            problems.append(f"坏形状腿又叠了一条 CA702（同一句话报两遍）：\n{out}")
    return problems


def check_when_sort_nan_is_a_shape_error() -> list[str]:
    """`when_sort: .nan` 不是「合法排序键」：报 CA109，按没有排序键 fail-open。

    YAML 的 `.nan` 是 float，过了 isinstance 检查就进了流水；而 NaN 的一切
    比较都是 False，CA701/CA705 对它整体静默——作者给了排序键，却拿到比
    「不给」更彻底的豁免，与 D2「写坏就 fail-open」相反（评审 I1）。
    """
    problems = []
    cards = {
        "thing-x": _card("thing-x", ""),
        "ev-nan": _card("ev-nan", (
            "when: 某年\nevent_kind: create\nwhen_sort: .nan\n"
            "object:\n  - thing-x\n"
        )).replace("type: location", "type: event"),
        "ev-dep": _card("ev-dep", (
            "when: 另一年\nevent_kind: destroy\nwhen_sort: 1\n"
            "object:\n  - thing-x\n"
            "depends_on:\n  - {id: ev-nan, kind: resource, critical: false}\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-nan-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"NaN when_sort 把 traceback 写到了 stderr：\n{err}")
        if "CA109" not in out:
            problems.append(f"when_sort: .nan 没报 CA109（写坏的排序键不许静默进流水）：\n{out}")
        if "CA701" in out:
            problems.append(f"NaN 参与的时序比较不该有结论（fail-open）：\n{out}")
    return problems


def check_multi_recipient_transfer_fails_open_on_ca704() -> list[str]:
    """多值受方 = 归属未定序：CA704 对最终那笔 `to` 列表里任一受方的断言都放行。

    `to: [bob, carol]` 时派生状态的报告取第一个（bob），但 carol 卡上断言
    owns 不该吃「最终持有者是 bob」的 error——她是受方之一，不是矛盾
    （评审反馈：多值腿静默取第一个会造成假 CA704）。列表外的第三者断言照报；
    更早一笔的受方（已被转手）不放行。
    """
    problems = []
    cards = {
        "anna": _card("anna", ""),
        "bob": _card("bob", "owns:\n  - gem-x\n"),
        "carol": _card("carol", "owns:\n  - gem-x\n"),
        "dave": _card("dave", "owns:\n  - gem-x\n"),  # 不在受方列表里，CA704 照报
        "gem-x": _card("gem-x", ""),
        "ev-split": _card("ev-split", (
            "when: 某年\nevent_kind: transfer\nwhen_sort: 1\n"
            "by:\n  - anna\nto:\n  - bob\n  - carol\nobject:\n  - gem-x\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-multito-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"多值受方把 traceback 写到了 stderr：\n{err}")
        for good in ("bob", "carol"):
            if any("[CA704]" in ln and f"{good}.md" in ln for ln in out.splitlines()):
                problems.append(f"受方 {good} 的断言不该吃 CA704（多值受方未定序）：\n{out}")
        if not any("[CA704]" in ln and "dave.md" in ln for ln in out.splitlines()):
            problems.append(f"列表外的 dave 断言 owns 必须照报 CA704：\n{out}")
    # 转手历史不放行：bob 拿到又转给 carol，bob 的断言与最终持有者矛盾，照报
    cards2 = {
        "bob": _card("bob", "owns:\n  - gem-y\n"),
        "carol": _card("carol", ""),
        "gem-y": _card("gem-y", ""),
        "ev-1": _card("ev-1", (
            "when: 元年\nevent_kind: transfer\nwhen_sort: 1\n"
            "by:\n  - carol\nto:\n  - bob\nobject:\n  - gem-y\n"
        )).replace("type: location", "type: event"),
        "ev-2": _card("ev-2", (
            "when: 二年\nevent_kind: transfer\nwhen_sort: 2\n"
            "by:\n  - bob\nto:\n  - carol\nobject:\n  - gem-y\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-multito2-", cards2)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"转手历史世界把 traceback 写到了 stderr：\n{err}")
        if not any("[CA704]" in ln and "bob.md" in ln for ln in out.splitlines()):
            problems.append(f"bob 已把 gem-y 转给 carol，断言必须照报 CA704：\n{out}")
    return problems


def check_conflicting_owns_assertions_fire_ca707() -> list[str]:
    """同一客体被多张卡断言 owns = 结论互搏，报 CA707（warning，评审 I3 拍板）。

    以前完全隐形（derive_state 按 id 序取第一个、不判）；有流水时其中一张卡
    还会吃上 CA704，而根因（断言互搏）没人报。CA707 是 warning：
    默认模式不拦，--strict 拦。
    """
    problems = []
    cards = {
        "h1": _card("h1", "owns:\n  - gem-x\n"),
        "h2": _card("h2", "owns:\n  - gem-x\n"),
        "gem-x": _card("gem-x", ""),
    }
    tmp, world = _temp_world("canonlint-ownsclash-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"断言互搏把 traceback 写到了 stderr：\n{err}")
        if "[CA707]" not in out:
            problems.append(f"两张卡断言 owns 同一客体却没报 CA707：\n{out}")
        if code != 0:
            problems.append(f"CA707 是 warning，默认模式不该拦（exit {code}）")
        code_s, out_s, _ = _judge(world, "--strict")
        if code_s != 1:
            problems.append(f"--strict 下 CA707 应当算失败（exit 1），实际 {code_s}")
    # 反面：单一断言不响
    tmp, world = _temp_world("canonlint-ownsok-", {
        "h1": _card("h1", "owns:\n  - gem-x\n"), "gem-x": _card("gem-x", "")})
    with tmp:
        code, out, err = _judge(world)
        if "CA707" in out:
            problems.append(f"单一 owns 断言不该报 CA707：\n{out}")
    return problems


def check_object_existence_window_fires_ca708() -> list[str]:
    """CA708：客体的事件必须落在它自己的存在窗口（create/birth 开、death/destroy 合）里。

    destroy 之后被 transfer、create 之前被 move，都是「不存在的东西在动弹」
    （评审反馈①，CA701 的姊妹规则；CA705 管 by 腿，CA708 管 object 腿）。
    端点事件自身豁免；缺 when_sort 照旧 fail-open。
    """
    problems = []
    cards = {
        "sword-x": _card("sword-x", ""),
        "alice": _card("alice", ""),
        "bob": _card("bob", ""),
        "ev-forge": _card("ev-forge", (
            "when: 元年\nevent_kind: create\nwhen_sort: 1\nobject:\n  - sword-x\n"
        )).replace("type: location", "type: event"),
        "ev-melt": _card("ev-melt", (
            "when: 末年\nevent_kind: destroy\nwhen_sort: 9\nobject:\n  - sword-x\n"
        )).replace("type: location", "type: event"),
        # 窗口内：不响
        "ev-mid": _card("ev-mid", (
            "when: 五年\nevent_kind: transfer\nwhen_sort: 5\n"
            "by:\n  - alice\nto:\n  - bob\nobject:\n  - sword-x\n"
        )).replace("type: location", "type: event"),
        # 造成之前：响
        "ev-early": _card("ev-early", (
            "when: 零年\nevent_kind: move\nwhen_sort: 0\n"
            "object:\n  - sword-x\nto:\n  - alice\n"
        )).replace("type: location", "type: event"),
        # 毁灭之后：响
        "ev-late": _card("ev-late", (
            "when: 十年\nevent_kind: transfer\nwhen_sort: 10\n"
            "by:\n  - alice\nto:\n  - bob\nobject:\n  - sword-x\n"
        )).replace("type: location", "type: event"),
        # 缺 when_sort：fail-open，不响
        "ev-nosort": _card("ev-nosort", (
            "when: 某年\nevent_kind: move\nobject:\n  - sword-x\nto:\n  - bob\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-window-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"存在窗口把 traceback 写到了 stderr：\n{err}")
        for bad in ("ev-early", "ev-late"):
            if not any("[CA708]" in ln and f"{bad}.md" in ln for ln in out.splitlines()):
                problems.append(f"{bad} 落在窗口外却没报 CA708：\n{out}")
        for good in ("ev-forge", "ev-melt", "ev-mid", "ev-nosort"):
            if any("[CA708]" in ln and f"{good}.md" in ln for ln in out.splitlines()):
                problems.append(f"{good} 不该报 CA708（端点豁免/窗口内/fail-open）：\n{out}")
    return problems


def check_move_from_leg_is_checked() -> list[str]:
    """move 的可选 `from` 腿（契约 0.4）：悬空 id 报 CA401，与 by/to/object 同罪。"""
    problems = []
    cards = {
        "keep-y": _card("keep-y", ""),
        "thing-x": _card("thing-x", ""),
        "ev-dangling": _card("ev-dangling", (
            "when: 某年\nevent_kind: move\nwhen_sort: 1\n"
            "from:\n  - ghost-place\nobject:\n  - thing-x\nto:\n  - keep-y\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-movefrom-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"from 腿把 traceback 写到了 stderr：\n{err}")
        if not any("[CA401]" in ln and "ghost-place" in ln for ln in out.splitlines()):
            problems.append(f"from 腿的悬空引用没报 CA401：\n{out}")
    return problems


def check_custody_assertions_reconcile_with_ledger() -> list[str]:
    """custody_of 断言与 custody 流水对账（CA709 error）+ 保管断言互搏（CA710 warning）。

    owns 有三件套（CA703/704/707），保管权以前是孤儿（评审反馈③）；
    契约 0.4 补 `custody_of` 断言字段后，keeper 线与 owner 线对称。
    多值受方与 CA704 同口径：最终那笔 to 列表里任一受方的断言放行。
    """
    problems = []
    # 对账打架：断言 keeper-a，流水把保管给了 keeper-b
    cards = {
        "keeper-a": _card("keeper-a", "custody_of:\n  - gem-x\n"),
        "keeper-b": _card("keeper-b", ""),
        "owner-o": _card("owner-o", ""),
        "gem-x": _card("gem-x", ""),
        "ev-handover": _card("ev-handover", (
            "when: 某年\nevent_kind: custody\nwhen_sort: 1\n"
            "by:\n  - owner-o\nto:\n  - keeper-b\nobject:\n  - gem-x\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-custody-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"custody 对账把 traceback 写到了 stderr：\n{err}")
        if not any("[CA709]" in ln and "keeper-a.md" in ln for ln in out.splitlines()):
            problems.append(f"断言与保管流水打架没报 CA709：\n{out}")
    # 互搏：两张卡都 custody_of 同一客体（无流水也报）
    cards2 = {
        "keeper-a": _card("keeper-a", "custody_of:\n  - gem-x\n"),
        "keeper-b": _card("keeper-b", "custody_of:\n  - gem-x\n"),
        "gem-x": _card("gem-x", ""),
    }
    tmp, world = _temp_world("canonlint-custodyclash-", cards2)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"保管互搏把 traceback 写到了 stderr：\n{err}")
        if "[CA710]" not in out:
            problems.append(f"两张卡 custody_of 同一客体却没报 CA710：\n{out}")
        if code != 0:
            problems.append(f"CA710 是 warning，默认模式不该拦（exit {code}）")
    # 反面：断言 = 流水推出的保管人，两条都不响；悬空/坏形状也有归属
    cards3 = {
        "keeper-b": _card("keeper-b", "custody_of:\n  - gem-x\n"),
        "owner-o": _card("owner-o", ""),
        "gem-x": _card("gem-x", ""),
        "ev-handover": _card("ev-handover", (
            "when: 某年\nevent_kind: custody\nwhen_sort: 1\n"
            "by:\n  - owner-o\nto:\n  - keeper-b\nobject:\n  - gem-x\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-custodyok-", cards3)
    with tmp:
        code, out, err = _judge(world)
        if "CA709" in out or "CA710" in out:
            problems.append(f"断言与流水一致时不该报 CA709/CA710：\n{out}")
    tmp, world = _temp_world("canonlint-custodybad-", {
        "keeper-a": _card("keeper-a", "custody_of:\n  - ghost-gem\n"),
        "keeper-b": _card("keeper-b", "custody_of: notalist\n"),
    })
    with tmp:
        code, out, err = _judge(world)
        if "CA401" not in out or "ghost-gem" not in out:
            problems.append(f"custody_of 悬空引用没报 CA401：\n{out}")
        if "CA109" not in out:
            problems.append(f"custody_of 写坏形状没报 CA109：\n{out}")
    return problems


def check_trajectory_break_fires_ca711() -> list[str]:
    """CA711 轨迹断裂：move 的 from 对不上链上当前位置（warning）。

    口径（评审两轮拍板）：只走存在窗口内的 move（窗外归 CA708，姊妹规则不双报）；
    当前位置是单值才校验 from（列表成员即放行）；上一笔 to 多值 → 当前位置
    「未定」→ 跳过校验，直到下一笔单值 to 重新锚定；缺 from / 缺 when_sort 不查。
    """
    problems = []

    def ev(id, sort, legs):
        return _card(id, f"when: 第{sort}年\nevent_kind: move\nwhen_sort: {sort}\n{legs}"
                     ).replace("type: location", "type: event")

    def broken_lines(out):
        return [ln for ln in out.splitlines() if "[CA711]" in ln]

    # 1. 正常链条 A→B→C：不响
    cards = {
        "wagon": _card("wagon", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "object:\n  - wagon\nfrom:\n  - pa\nto:\n  - pb\n"),
        "ev-2": ev("ev-2", 2, "object:\n  - wagon\nfrom:\n  - pb\nto:\n  - pc\n"),
    }
    tmp, world = _temp_world("canonlint-traj-ok-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"正常轨迹把 traceback 写到了 stderr：\n{err}")
        if broken_lines(out):
            problems.append(f"A→B→C 的正常链条不该报 CA711：\n{out}")

    # 2. 断裂：A→B 之后又「从 C 出发」→ 响
    cards["ev-2"] = ev("ev-2", 2, "object:\n  - wagon\nfrom:\n  - pc\nto:\n  - pa\n")
    tmp, world = _temp_world("canonlint-traj-bad-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"断裂轨迹把 traceback 写到了 stderr：\n{err}")
        hits = broken_lines(out)
        if not any("ev-2.md" in ln for ln in hits):
            problems.append(f"from=pc 对不上落点 pb 却没报 CA711：\n{out}")
        if any("ev-1.md" in ln for ln in hits):
            problems.append(f"第一笔 move 是链条起点，不该被查：\n{out}")

    # 3. 上游多值 to → 位置「未定」→ 下一笔 from 不查；再下一笔单值 to 重新锚定后照查
    cards3 = {
        "wagon": _card("wagon", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "object:\n  - wagon\nto:\n  - pa\n  - pb\n"),  # 多值 → 未定
        "ev-2": ev("ev-2", 2, "object:\n  - wagon\nfrom:\n  - pc\nto:\n  - pc\n"),  # 不查
        "ev-3": ev("ev-3", 3, "object:\n  - wagon\nfrom:\n  - pa\nto:\n  - pb\n"),  # 上笔落 pc，响
    }
    tmp, world = _temp_world("canonlint-traj-undet-", cards3)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"未定位置把 traceback 写到了 stderr：\n{err}")
        hits = broken_lines(out)
        if any("ev-2.md" in ln for ln in hits):
            problems.append(f"上一笔 to 多值 = 位置未定，ev-2 不该被查：\n{out}")
        if not any("ev-3.md" in ln for ln in hits):
            problems.append(f"重新锚定后 from 对不上必须报（ev-3）：\n{out}")

    # 4. from 多值：当前位置在列表里就放行（多值 = 没定，不替人裁）
    cards4 = {
        "wagon": _card("wagon", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "object:\n  - wagon\nto:\n  - pb\n"),
        "ev-2": ev("ev-2", 2, "object:\n  - wagon\nfrom:\n  - pa\n  - pb\nto:\n  - pc\n"),
    }
    tmp, world = _temp_world("canonlint-traj-multifrom-", cards4)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"多值 from 把 traceback 写到了 stderr：\n{err}")
        if broken_lines(out):
            problems.append(f"当前位置 pb 在 from 列表里，不该报 CA711：\n{out}")

    # 5. 与 CA708 的分工：窗口外的 move 归 CA708，CA711 不重复报
    cards5 = {
        "wagon": _card("wagon", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "object:\n  - wagon\nto:\n  - pb\n"),
        "ev-death": _card("ev-death", "when: 第2年\nevent_kind: destroy\nwhen_sort: 2\n"
                          "object:\n  - wagon\n").replace("type: location", "type: event"),
        "ev-3": ev("ev-3", 3, "object:\n  - wagon\nfrom:\n  - pc\nto:\n  - pa\n"),
    }
    tmp, world = _temp_world("canonlint-traj-window-", cards5)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"窗口外轨迹把 traceback 写到了 stderr：\n{err}")
        if not any("[CA708]" in ln and "ev-3.md" in ln for ln in out.splitlines()):
            problems.append(f"窗口外的 move 该由 CA708 报：\n{out}")
        if broken_lines(out):
            problems.append(f"窗口外的 move 不该再叠 CA711（姊妹规则不双报）：\n{out}")
    return problems


def check_transfer_from_must_match_previous_to() -> list[str]:
    """CA713 转让起点断裂：transfer/grant 的 from 对不上链上上一笔的落点（warning）。

    与 CA711 同款口径：只查完整事件（缺 when_sort 不进流水）；上一笔 to 多值 →
    起点「未定」跳过校验，直到下一笔单值 to 重新锚定；from 多值 = 没定，起点在
    列表里就放行；不写 from 就不查（fail-open）；同刻转让不排序、不互为「上一笔」。
    """
    problems = []

    def ev(eid, sort, legs):
        return _card(eid, f"when: 第{sort}年\nevent_kind: transfer\nwhen_sort: {sort}\n{legs}"
                     ).replace("type: location", "type: event")

    def broken_lines(out):
        return [ln for ln in out.splitlines() if "[CA713]" in ln]

    # 1. 正常链条 A→B→C：不响
    cards = {
        "sword": _card("sword", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "by:\n  - pa\nobject:\n  - sword\nto:\n  - pb\n"),
        "ev-2": ev("ev-2", 2, "by:\n  - pb\nobject:\n  - sword\nfrom:\n  - pb\nto:\n  - pc\n"),
    }
    tmp, world = _temp_world("canonlint-from-ok-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"正常转让链把 traceback 写到了 stderr：\n{err}")
        if broken_lines(out):
            problems.append(f"A→B→C 的正常转让链不该报 CA713：\n{out}")

    # 2. 断裂：上一笔落到 pb，本笔却「从 pc 交出」→ 响在 ev-2，不响第一笔
    cards["ev-2"] = ev("ev-2", 2, "by:\n  - pc\nobject:\n  - sword\nfrom:\n  - pc\nto:\n  - pa\n")
    tmp, world = _temp_world("canonlint-from-bad-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"断裂转让把 traceback 写到了 stderr：\n{err}")
        hits = broken_lines(out)
        if not any("ev-2.md" in ln for ln in hits):
            problems.append(f"from=pc 对不上落点 pb 却没报 CA713：\n{out}")
        if any("ev-1.md" in ln for ln in hits):
            problems.append(f"第一笔转让是链条起点，不该被查：\n{out}")

    # 3. 上一笔 to 多值 → 起点未定 → 跳过；下一笔单值 to 重新锚定后照查
    cards3 = {
        "sword": _card("sword", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "by:\n  - pa\nobject:\n  - sword\nto:\n  - pa\n  - pb\n"),
        "ev-2": ev("ev-2", 2, "by:\n  - pc\nobject:\n  - sword\nfrom:\n  - pc\nto:\n  - pc\n"),
        "ev-3": ev("ev-3", 3, "by:\n  - pa\nobject:\n  - sword\nfrom:\n  - pa\nto:\n  - pb\n"),
    }
    tmp, world = _temp_world("canonlint-from-undet-", cards3)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"未定起点把 traceback 写到了 stderr：\n{err}")
        hits = broken_lines(out)
        if any("ev-2.md" in ln for ln in hits):
            problems.append(f"上一笔 to 多值 = 起点未定，ev-2 不该被查：\n{out}")
        if not any("ev-3.md" in ln for ln in hits):
            problems.append(f"重新锚定后 from 对不上必须报（ev-3）：\n{out}")

    # 4. from 多值：起点在列表里就放行（多值 = 没定，不替人裁）
    cards4 = {
        "sword": _card("sword", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "by:\n  - pa\nobject:\n  - sword\nto:\n  - pb\n"),
        "ev-2": ev("ev-2", 2, "by:\n  - pa\nobject:\n  - sword\nfrom:\n  - pa\n  - pb\nto:\n  - pc\n"),
    }
    tmp, world = _temp_world("canonlint-from-multi-", cards4)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"多值 from 把 traceback 写到了 stderr：\n{err}")
        if broken_lines(out):
            problems.append(f"上一笔落点 pb 在 from 列表里，不该报 CA713：\n{out}")

    # 5. 同刻两笔转让不互为「上一笔」：同刻多值 → 未定，后续不查
    cards5 = {
        "ring": _card("ring", ""),
        "pa": _card("pa", ""), "pb": _card("pb", ""), "pc": _card("pc", ""),
        "ev-1": ev("ev-1", 1, "by:\n  - pa\nobject:\n  - ring\nto:\n  - pb\n"),
        "ev-2": ev("ev-2", 1, "by:\n  - pa\nobject:\n  - ring\nto:\n  - pc\n"),
        "ev-3": ev("ev-3", 2, "by:\n  - pb\nobject:\n  - ring\nfrom:\n  - pb\nto:\n  - pa\n"),
    }
    tmp, world = _temp_world("canonlint-from-instant-", cards5)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"同刻转让把 traceback 写到了 stderr：\n{err}")
        if broken_lines(out):
            problems.append(f"同刻多笔 = 起点未定，ev-3 不该被查：\n{out}")
    return problems


def check_join_leave_are_vocabulary_kinds() -> list[str]:
    """join/leave 转正（协议 1.6）：进 event_kind 词表，腿表参与 CA702。

    人写 by 腿（与 CA705 同一条腿，白拿「死人不能入伙」），组织写
    to（join）/ from（leave）。不为「组织同意」单独立腿（v0 只记事实侧）。
    """
    problems = []
    cards = {
        "jon": _card("jon", ""),
        "watch": _card("watch", ""),
        "ev-join": _card("ev-join", (
            "when: 某年\nevent_kind: join\nwhen_sort: 1\n"
            "by:\n  - jon\nto:\n  - watch\n"
        )).replace("type: location", "type: event"),
        # leave 缺 from 腿 → CA702
        "ev-leave-bad": _card("ev-leave-bad", (
            "when: 另一年\nevent_kind: leave\nwhen_sort: 2\n"
            "by:\n  - jon\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-joinleave-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"join/leave 把 traceback 写到了 stderr：\n{err}")
        if "CA102" in out:
            problems.append(f"join/leave 已是词表值，不该报 CA102：\n{out}")
        if not any("[CA702]" in ln and "ev-leave-bad.md" in ln for ln in out.splitlines()):
            problems.append(f"leave 缺 from 腿没报 CA702：\n{out}")
    return problems


def check_member_of_reconciles_with_ledger() -> list[str]:
    """member_of 断言 vs 流水（CA712 error）：断言在，但该人流水里对那个组织
    的最后一个动作是 leave。

    member_of 多值合法（一个人可以同时在多个组织），所以只有对账、
    没有互搏规则。断言与最终归属一致、或该组织没有流水，都不响。
    """
    problems = []
    # 打架：dan 断言 member_of watch，流水里他后来 leave 了
    cards = {
        "dan": _card("dan", "member_of:\n  - watch\n").replace(
            "type: location", "type: character"),
        "watch": _card("watch", "").replace("type: location", "type: faction"),
        "ev-join": _card("ev-join", (
            "when: 元年\nevent_kind: join\nwhen_sort: 1\nby:\n  - dan\nto:\n  - watch\n"
        )).replace("type: location", "type: event"),
        "ev-leave": _card("ev-leave", (
            "when: 二年\nevent_kind: leave\nwhen_sort: 2\nby:\n  - dan\nfrom:\n  - watch\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-member-bad-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"member_of 对账把 traceback 写到了 stderr：\n{err}")
        if not any("[CA712]" in ln and "dan.md" in ln for ln in out.splitlines()):
            problems.append(f"断言 member_of 但流水里已 leave，没报 CA712：\n{out}")
    # 一致：断言 = 最终归属（join 之后无 leave）→ 不响
    cards2 = {
        "jon": _card("jon", "member_of:\n  - watch\n").replace(
            "type: location", "type: character"),
        "watch": _card("watch", "").replace("type: location", "type: faction"),
        "ev-join": _card("ev-join", (
            "when: 元年\nevent_kind: join\nwhen_sort: 1\nby:\n  - jon\nto:\n  - watch\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-member-ok-", cards2)
    with tmp:
        code, out, err = _judge(world)
        if "CA712" in out:
            problems.append(f"断言与流水一致时不该报 CA712：\n{out}")
    # 断言的组织没有流水：断言即全部历史，不响（D3 同款豁免）
    tmp, world = _temp_world("canonlint-member-noflow-", {
        "jon": _card("jon", "member_of:\n  - watch\n").replace(
            "type: location", "type: character"),
        "watch": _card("watch", "").replace("type: location", "type: faction")})
    with tmp:
        _, out, _ = _judge(world)
        if "CA712" in out:
            problems.append(f"无流水的 member_of 断言不该报 CA712：\n{out}")
    # 悬空与坏形状：CA401 / CA109（与 custody_of 同口径）
    tmp, world = _temp_world("canonlint-member-shape-", {
        "jon": _card("jon", "member_of:\n  - ghost-org\n").replace(
            "type: location", "type: character"),
        "dan": _card("dan", "member_of: notalist\n").replace(
            "type: location", "type: character")})
    with tmp:
        _, out, _ = _judge(world)
        if "CA401" not in out or "ghost-org" not in out:
            problems.append(f"member_of 悬空引用没报 CA401：\n{out}")
        if "CA109" not in out:
            problems.append(f"member_of 写坏形状没报 CA109：\n{out}")
    return problems


def check_transform_closes_and_opens_windows() -> list[str]:
    """transform（协议 1.7）：旧身份死、新身份生——存在窗口在转化处交接。

    object = 旧 id（关窗），result = 新 id 列表（开窗，多值 = 一生多）。
    旧 id 之后被用 / 新 id 之前被用都报 CA708；transform 事件自身是边界，不报。
    缺 result 腿报 CA702。新 id 不自动继承旧 id 的持有者与位置（v0 不猜）。
    """
    problems = []

    def ev(id, kind, sort, legs):
        return _card(id, f"when: 第{sort}年\nevent_kind: {kind}\nwhen_sort: {sort}\n{legs}"
                     ).replace("type: location", "type: event")

    cards = {
        "old-sword": _card("old-sword", ""),
        "new-sword": _card("new-sword", ""),
        "keep-x": _card("keep-x", ""),
        "ev-create": ev("ev-create", "create", 1, "object:\n  - old-sword\n"),
        "ev-transform": ev("ev-transform", "transform", 5,
                           "object:\n  - old-sword\nresult:\n  - new-sword\n"),
        # 旧 id 在关窗之后被移动 → CA708
        "ev-late": ev("ev-late", "move", 7, "object:\n  - old-sword\nto:\n  - keep-x\n"),
        # 新 id 在开窗之前被移动 → CA708
        "ev-early": ev("ev-early", "move", 3, "object:\n  - new-sword\nto:\n  - keep-x\n"),
        # 新 id 在开窗之后被移动 → 不响
        "ev-after": ev("ev-after", "move", 6, "object:\n  - new-sword\nto:\n  - keep-x\n"),
        # 缺 result 腿 → CA702
        "ev-bad": ev("ev-bad", "transform", 8, "object:\n  - old-sword\n"),
    }
    tmp, world = _temp_world("canonlint-transform-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"transform 世界把 traceback 写到了 stderr：\n{err}")
        if "CA102" in out:
            problems.append(f"transform 已是词表值，不该报 CA102：\n{out}")
        for bad, why in (("ev-late", "旧 id 在 transform 之后被移动"),
                         ("ev-early", "新 id 在 transform 之前被移动")):
            if not any("[CA708]" in ln and f"{bad}.md" in ln for ln in out.splitlines()):
                problems.append(f"{why} 却没报 CA708：\n{out}")
        for good, why in (("ev-transform", "transform 事件自身即边界"),
                          ("ev-after", "新 id 在开窗之后")):
            if any("[CA708]" in ln and f"{good}.md" in ln for ln in out.splitlines()):
                problems.append(f"{good}（{why}）不该报 CA708：\n{out}")
        if not any("[CA702]" in ln and "ev-bad.md" in ln for ln in out.splitlines()):
            problems.append(f"transform 缺 result 腿没报 CA702：\n{out}")
    # 不自动继承：旧 id 有 owns 断言，transform 后新 id 的持有者是「无」而不是旧主
    cards2 = {
        "anna": _card("anna", "owns:\n  - old-sword\n"),
        "old-sword": _card("old-sword", ""),
        "new-sword": _card("new-sword", ""),
        "ev-transform": ev("ev-transform", "transform", 5,
                           "object:\n  - old-sword\nresult:\n  - new-sword\n"),
    }
    tmp, world = _temp_world("canonlint-transform-own-", cards2)
    with tmp:
        p = subprocess.run([PY, str(TOOL), "ledger", str(world)],
                           cwd=ROOT, capture_output=True, text=True)
        for ln in p.stdout.splitlines():
            if ln.startswith("new-sword:") and "（无）" not in ln:
                problems.append(f"新 id 自动继承了旧 id 的持有者（v0 裁决是不猜）：\n{p.stdout}")
    return problems


def check_modify_preserves_identity_and_state() -> list[str]:
    """modify（协议 1.9）：同 id 变化，不动窗口、持有、保管或位置。"""
    problems = []

    def ev(eid: str, kind: str, sort: float | None, legs: str) -> str:
        sort_line = f"when_sort: {sort}\n" if sort is not None else ""
        return _card(
            eid, f"when: 第{sort}年\nevent_kind: {kind}\n{sort_line}{legs}"
        ).replace("type: location", "type: event")

    def findings(world: Path) -> list[dict]:
        _code, out, err = _judge(world, "--json")
        if err:
            problems.append(f"modify 世界把 traceback 写到了 stderr：\n{err}")
        try:
            return json.loads(out)["findings"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            problems.append(f"modify 世界的 JSON 审计输出不可读：{exc}\n{out}")
            return []

    def hit(items: list[dict], rule: str, entry: str) -> bool:
        return any(f["rule"] == rule and Path(f["entry"]).name == f"{entry}.md"
                   for f in items)

    def rules_for(items: list[dict], entry: str) -> set[str]:
        return {f["rule"] for f in items if f["entry"] == f"entries/{entry}.md"}

    cards = {
        "relic": _card("relic", ""),
        "owner": _card("owner", "owns:\n  - relic\n"),
        "keeper": _card("keeper", "custody_of:\n  - relic\n"),
        "old-place": _card("old-place", ""),
        "ev-create": ev("ev-create", "create", 1, "object:\n  - relic\n"),
        "ev-custody": ev("ev-custody", "custody", 2,
                         "by:\n  - owner\nto:\n  - keeper\nobject:\n  - relic\n"),
        "ev-move": ev("ev-move", "move", 2,
                      "object:\n  - relic\nto:\n  - old-place\n"),
        "ev-modify": ev("ev-modify", "modify", 3, "object:\n  - relic\n"),
        "ev-unsorted": ev("ev-unsorted", "modify", None, "object:\n  - relic\n"),
    }
    tmp, world = _temp_world("canonlint-modify-ok-", cards)
    with tmp:
        items = findings(world)
        for rule in ("CA102", "CA702", "CA708"):
            for entry in ("ev-modify", "ev-unsorted"):
                if hit(items, rule, entry):
                    problems.append(f"合法 {entry} 不该报 {rule}：{items}")
        code, out, err = run_case(["ledger", str(world)])
        expected = ("relic: 持有者 owner（来自 `owner`）【流水结论】"
                    " | 保管 keeper【流水结论】 | 位置 old-place【流水结论】")
        if code != 0 or err or expected not in out:
            problems.append(f"modify 改变了既有派生状态：\n{out}{err}")
        if "4 笔完整事件" not in out:
            problems.append(f"缺 when_sort 的 modify 混进了有序流水：\n{out}")

    cards = {
        "relic": _card("relic", ""),
        "person": _card("person", ""),
        "ev-early": ev("ev-early", "modify", 0, "object:\n  - relic\n"),
        "ev-death": ev("ev-death", "death", 1, "object:\n  - person\n"),
        "ev-same": ev("ev-same", "modify", 1,
                      "by:\n  - person\nobject:\n  - relic\n"),
        "ev-late-actor": ev("ev-late-actor", "modify", 2,
                            "by:\n  - person\nobject:\n  - relic\n"),
        "ev-create": ev("ev-create", "create", 3, "object:\n  - relic\n"),
        "ev-destroy": ev("ev-destroy", "destroy", 4, "object:\n  - relic\n"),
        "ev-after": ev("ev-after", "modify", 5, "object:\n  - relic\n"),
        "ev-missing": ev("ev-missing", "modify", 6, ""),
        "ev-shape": ev("ev-shape", "modify", 7, "object: relic\n"),
        "ev-ghost": ev("ev-ghost", "modify", 8, "object:\n  - ghost\n"),
    }
    tmp, world = _temp_world("canonlint-modify-bad-", cards)
    with tmp:
        items = findings(world)
        for entry in ("ev-early", "ev-after"):
            if not hit(items, "CA708", entry):
                problems.append(f"{entry} 落在存在窗口外却没报 CA708：{items}")
        if hit(items, "CA705", "ev-same"):
            problems.append(f"与 death 同刻的 modify 不该报 CA705：{items}")
        if not hit(items, "CA705", "ev-late-actor"):
            problems.append(f"严格晚于 death 的 modify 没报 CA705：{items}")
        for entry, expected_rules in (("ev-missing", {"CA702"}),
                                      ("ev-shape", {"CA109"}),
                                      ("ev-ghost", {"CA401"})):
            actual_rules = rules_for(items, entry)
            if actual_rules != expected_rules:
                problems.append(
                    f"{entry} 应只报 {sorted(expected_rules)}，实际 {sorted(actual_rules)}")

    cards = {
        "old-relic": _card("old-relic", ""),
        "new-relic": _card("new-relic", ""),
        "keep": _card("keep", ""),
        "ev-modify-result": ev(
            "ev-modify-result", "modify", 3,
            "object:\n  - old-relic\nresult:\n  - new-relic\n"),
        "ev-move-old": ev("ev-move-old", "move", 4,
                          "object:\n  - old-relic\nto:\n  - keep\n"),
        "ev-move-new": ev("ev-move-new", "move", 4,
                          "object:\n  - new-relic\nto:\n  - keep\n"),
        "ev-create-new": ev("ev-create-new", "create", 5,
                            "object:\n  - new-relic\n"),
    }
    tmp, world = _temp_world("canonlint-modify-result-", cards)
    with tmp:
        items = findings(world)
        if not hit(items, "CA708", "ev-move-new"):
            problems.append(f"modify 的 result 被误当成开窗边界：{items}")
        if hit(items, "CA708", "ev-modify-result"):
            problems.append(f"modify 自身不该成为存在窗口边界：{items}")
        if hit(items, "CA708", "ev-move-old"):
            problems.append(f"modify 被误当成旧 id 的关窗边界：{items}")

    tmp, world = _temp_world("canonlint-modify-cli-", {"relic": _card("relic", "")})
    with tmp:
        p = subprocess.run(
            [PY, str(TOOL), "event", "modify", "局部改建",
             "--root", str(world), "--id", "ev-cli",
             "--when", "元年", "--when-sort", "1", "--object", "relic"],
            cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            problems.append(f"event modify 应能建卡，实际 exit={p.returncode}：{p.stderr or p.stdout}")
        if not (world / "entries" / "events" / "ev-cli.md").is_file():
            problems.append("event modify 没有写出 entries/events/ev-cli.md")
        items = findings(world)
        for rule in ("CA102", "CA702", "CA708"):
            if hit(items, rule, "ev-cli"):
                problems.append(f"CLI 建出的合法 modify 不该报 {rule}：{items}")
    return problems


def check_ledger_bad_world_fires_every_rule() -> list[str]:
    """变异验证的骨架：world-ledger-bad 必须真的把 CA7xx 每条至少踩一次。

    快照只证明「没变」，这条证明「守卫在生效」——某条规则被改哑（比如把
    error 降级、把比较方向写反成 >=），这里就变红。
    """
    problems = []
    code, out, err = _judge(HERE / "world-ledger-bad")
    if err:
        problems.append(f"world-ledger-bad 把 traceback 写到了 stderr：\n{err}")
    for rule in ("CA701", "CA702", "CA703", "CA704", "CA705", "CA706", "CA708",
                 "CA709", "CA710", "CA712", "CA713", "CA714", "CA102",
                 "CA401"):
        if f"[{rule}]" not in out:
            problems.append(f"world-ledger-bad 没有触发 {rule}（触发矩阵失效）：\n{out}")
    if code != 1:
        problems.append(f"world-ledger-bad 有 error 应当 exit 1，实际 {code}")
    return problems


def check_ledger_command_is_readonly_report() -> list[str]:
    """ledger 子命令与 --impact 同一条纪律：报告级输出永不进退出码、永不写盘。

    在一个有 error 的世界上跑 ledger 也必须 exit 0；目录树的逐字节哈希
    前后一致（「跑一下 ledger 就算改好了」是这条纪律要防的误解）。
    """
    problems = []
    world = HERE / "world-ledger-bad"
    before = {p.relative_to(world): p.read_bytes()
              for p in sorted(world.rglob("*")) if p.is_file()}
    p = subprocess.run([PY, str(TOOL), "ledger", str(world)],
                       cwd=ROOT, capture_output=True, text=True)
    if p.stderr:
        problems.append(f"ledger 子命令把 traceback 写到了 stderr：\n{p.stderr}")
    if p.returncode != 0:
        problems.append(f"ledger 在有 error 的世界上也必须 exit 0，实际 {p.returncode}")
    if "派生状态" not in p.stdout:
        problems.append(f"ledger 输出里看不到派生状态：\n{p.stdout}")
    after = {p.relative_to(world): p.read_bytes()
             for p in sorted(world.rglob("*")) if p.is_file()}
    if before != after:
        problems.append("ledger 子命令改动了世界目录（只读纪律被破坏）")
    return problems


def check_same_instant_id_order_is_not_history() -> list[str]:
    """协议 1.8：同刻（when_sort 相等）没有先后，改名不许翻转 CA704/CA709/CA711/CA712。

    以前流水按 (when_sort, id) 排序后，判定把它当成了时序：两笔同刻 transfer 的
    文件名一换，CA704 的 error 就在「c 是持有者」与「d 是持有者」之间翻转。
    """
    problems = []

    def ev(eid: str, kind: str, sort: float, legs: str) -> str:
        return _card(eid, f"when: 第{sort:g}年\nevent_kind: {kind}\nwhen_sort: {sort:g}\n{legs}"
                     ).replace("type: location", "type: event")

    def tie_world(ev1: str, ev2: str) -> tuple:
        cards = {
            "a": _card("a", ""), "b": _card("b", ""),
            "c": _card("c", "owns:\n  - relic\n"),
            "d": _card("d", ""), "relic": _card("relic", ""),
            ev1: ev(ev1, "transfer", 5, "by:\n  - a\nobject:\n  - relic\nto:\n  - d\n"),
            ev2: ev(ev2, "transfer", 5, "by:\n  - b\nobject:\n  - relic\nto:\n  - c\n"),
        }
        return _temp_world("canonlint-tie704-", cards)

    tie_results = []
    for names in (("ev-a", "ev-b"), ("ev-z", "ev-y")):
        tmp, world = tie_world(*names)
        with tmp:
            _, out, err = _judge(world)
            if err:
                problems.append(f"同刻转让把 traceback 写到了 stderr：\n{err}")
            lines = [ln for ln in out.splitlines() if "[CA704]" in ln]
            if not any("] warning " in ln and "未定序" in ln for ln in lines):
                problems.append(f"同刻两笔转让受方不同，应报 CA704 warning「未定序」（{'/'.join(names)}）：\n{out}")
            # 协议 1.14：未定序不再吞掉断言对账——c 的 owns 断言不同时落在
            # 两笔候选（{d}、{c}）里，交集为空，照报 error；d 没断言不报。
            if not any("] error " in ln and "c.md" in ln for ln in lines):
                problems.append(
                    f"c 的断言不在未定序候选交集里，应报 CA704 error（{'/'.join(names)}）：\n{out}")
            if any("] error " in ln and "d.md" in ln for ln in lines):
                problems.append(f"d 没有断言，不该报 CA704 error（{'/'.join(names)}）：\n{out}")
            tie_results.append((
                sorted(ln.split("] ", 1)[1].split(" ")[0] for ln in lines),
                sorted(ln.split("entries/", 1)[1].split(".md")[0]
                       for ln in lines if "] error " in ln)))
    if tie_results[0] != tie_results[1]:
        problems.append(
            f"同刻改名让 CA704 的判定翻转：{tie_results[0]} vs {tie_results[1]}")

    # CA711：同刻两笔 move，id 序与故事序相反也不许断裂
    def move(id: str, frm: str, to: str) -> str:
        return ev(id, "move", 5, f"object:\n  - relic\nfrom:\n  - {frm}\nto:\n  - {to}\n")

    for ids in (("mv-a", "mv-b"), ("mv-z", "mv-y")):
        cards = {
            "hall": _card("hall", ""), "gate": _card("gate", ""),
            "tower": _card("tower", ""), "relic": _card("relic", ""),
            ids[0]: move(ids[0], "hall", "gate"),
            ids[1]: move(ids[1], "gate", "tower"),
        }
        tmp, world = _temp_world("canonlint-tie711-", cards)
        with tmp:
            _, out, err = _judge(world)
            if err:
                problems.append(f"同刻移动把 traceback 写到了 stderr：\n{err}")
            if "[CA711]" in out:
                problems.append(f"同刻两笔 move 没有先后，不该报 CA711（{'/'.join(ids)}）：\n{out}")

    # CA709：同刻两笔 custody
    tie709_results = []
    for ev1, ev2 in (("cu-a", "cu-b"), ("cu-z", "cu-y")):
        cards = {
            "x": _card("x", "custody_of:\n  - relic\n"),
            "y": _card("y", ""), "relic": _card("relic", ""),
            ev1: ev(ev1, "custody", 5, "by:\n  - x\nobject:\n  - relic\nto:\n  - x\n"),
            ev2: ev(ev2, "custody", 5, "by:\n  - y\nobject:\n  - relic\nto:\n  - y\n"),
        }
        tmp, world = _temp_world("canonlint-tie709-", cards)
        with tmp:
            _, out, err = _judge(world)
            if err:
                problems.append(f"同刻保管把 traceback 写到了 stderr：\n{err}")
            lines = [ln for ln in out.splitlines() if "[CA709]" in ln]
            if not any("] warning " in ln and "未定序" in ln for ln in lines):
                problems.append(f"同刻两笔 custody 应报 CA709 未定序 warning（{ev1}/{ev2}）：\n{out}")
            if not any("] error " in ln and "x.md" in ln for ln in lines):
                problems.append(
                    f"x 的 custody_of 断言不在候选交集里，应报 CA709 error（{ev1}/{ev2}）：\n{out}")
            tie709_results.append((
                sorted(ln.split("] ", 1)[1].split(" ")[0] for ln in lines),
                sorted(ln.split("entries/", 1)[1].split(".md")[0]
                       for ln in lines if "] error " in ln)))
    if tie709_results[0] != tie709_results[1]:
        problems.append(
            f"同刻改名让 CA709 的判定翻转：{tie709_results[0]} vs {tie709_results[1]}")

    # CA712：同刻 join 与 leave 并存 → fail-open
    for ev1, ev2 in (("j-a", "l-b"), ("j-z", "l-y")):
        cards = {
            "a": _card("a", "member_of:\n  - guild\n").replace(
                "type: location", "type: character"),
            "org": _card("org", "").replace("type: location", "type: faction"),
            ev1: ev(ev1, "join", 5, "by:\n  - a\nto:\n  - org\n"),
            ev2: ev(ev2, "leave", 5, "by:\n  - a\nfrom:\n  - org\n"),
        }
        tmp, world = _temp_world("canonlint-tie712-", cards)
        with tmp:
            _, out, err = _judge(world)
            if err:
                problems.append(f"同刻 join/leave 把 traceback 写到了 stderr：\n{err}")
            if "[CA712]" in out:
                problems.append(f"同刻 join 与 leave 谁最后未定序，应 fail-open（{ev1}/{ev2}）：\n{out}")
    return problems


def check_ambiguous_final_without_assertion_is_reported() -> list[str]:
    """同刻多笔且受方/保管人不同：没有断言也要报 CA704/CA709「归属未定序」（协议 1.10）。

    #10 的实测：两笔同刻 transfer 给 alice、bob，世界里没有任何 owns 断言时，
    旧实现把 warning 发在「遍历 owns 断言」的循环里——没有断言就一条都不报，
    而派生状态照旧按 id 序挑一个持有者展示（猜的答案没有任何标记）。CA709 同病。
    修复后：未定序是流水自身的性质，与断言无关；每客体报一条，warning 不拦。
    """
    problems = []

    def ev(eid: str, kind: str, legs: str) -> str:
        return _card(eid, f"when: 元年\nevent_kind: {kind}\nwhen_sort: 5\n{legs}"
                     ).replace("type: location", "type: event")

    def no_ambiguity_noise(world: Path, rule: str) -> None:
        code, out, err = _judge(world)
        if err:
            problems.append(f"未定序世界把 traceback 写到了 stderr：\n{err}")
        hits = [ln for ln in out.splitlines() if f"[{rule}]" in ln]
        if len(hits) != 1:
            problems.append(
                f"{rule} 的未定序应每客体只报一条，实际 {len(hits)} 条：\n{out}")
        if hits and "未定序" not in hits[0]:
            problems.append(f"{rule} 的这一条应是「未定序」：\n{out}")
        if any("] error " in ln for ln in hits):
            problems.append(f"未定序不许按 id 序挑赢家报 error（{rule}）：\n{out}")
        if code != 0:
            problems.append(f"未定序只是 warning，默认模式不该拦（{rule}，exit {code}）")

    # CA704：世界里没有任何 owns 断言
    tmp, world = _temp_world("canonlint-ambig704-", {
        "alice": _card("alice", "").replace("type: location", "type: character"),
        "bob": _card("bob", "").replace("type: location", "type: character"),
        "relic": _card("relic", "").replace("type: location", "type: item"),
        "ev-a": ev("ev-a", "transfer",
                   "by:\n  - alice\nobject:\n  - relic\nto:\n  - alice\n"),
        "ev-b": ev("ev-b", "transfer",
                   "by:\n  - alice\nobject:\n  - relic\nto:\n  - bob\n"),
    })
    with tmp:
        no_ambiguity_noise(world, "CA704")
        code_s, _, _ = _judge(world, "--strict")
        if code_s != 1:
            problems.append(
                f"--strict 下 CA704 warning 应当算失败（exit 1），实际 {code_s}")

    # CA709：世界里没有任何 custody_of 断言
    tmp, world = _temp_world("canonlint-ambig709-", {
        "x": _card("x", "").replace("type: location", "type: character"),
        "y": _card("y", "").replace("type: location", "type: character"),
        "relic": _card("relic", "").replace("type: location", "type: item"),
        "cu-a": ev("cu-a", "custody",
                   "by:\n  - x\nobject:\n  - relic\nto:\n  - x\n"),
        "cu-b": ev("cu-b", "custody",
                   "by:\n  - y\nobject:\n  - relic\nto:\n  - y\n"),
    })
    with tmp:
        no_ambiguity_noise(world, "CA709")
    return problems


def check_ambiguous_final_still_reconciles_assertions() -> list[str]:
    """同刻未定序不能当断言对账的「一键降级器」（漏洞审计 §2.1）。

    1.10 让 CA704 在「同刻多笔、受方集合不同」时只报 warning、不挑赢家——但
    当前实现把该客体的**全部** owns 对账一起跳过：作者补一笔同刻、受方不同的
    transfer，就能把已触发的 error 降成 warning。修法：ambiguous 时仍对账
    「断言者 ∈ 全部候选受方的交集」——交集里没有断言就照报，不需要挑赢家。
    """
    problems = []

    def ev(eid: str, extra: str) -> str:
        return _card(eid, (
            "when: 元年\nevent_kind: transfer\nwhen_sort: 1\n" + extra
        )).replace("type: location", "type: event")

    # 对照：单笔流水、断言与最终持有者一致 → 不报 CA704
    cards = {
        "giver": _card("giver", ""),
        "holder": _card("holder", "owns:\n  - gem-a\n"),
        "gem-a": _card("gem-a", ""),
        "ev-a": ev("ev-a", "by:\n  - giver\nto:\n  - holder\nobject:\n  - gem-a\n"),
    }
    tmp, world = _temp_world("canonlint-amb-ctl-", cards)
    with tmp:
        _, out, _ = _judge(world)
        if any("[CA704]" in ln for ln in out.splitlines()):
            problems.append(f"单笔流水与断言一致时不该报 CA704：\n{out}")

    # 漏洞复现：补一笔同刻、受方不同的 transfer，断言对账不得消失
    cards = dict(cards)
    cards["other"] = _card("other", "")
    cards["ev-b"] = ev("ev-b", "by:\n  - giver\nto:\n  - other\nobject:\n  - gem-a\n")
    tmp, world = _temp_world("canonlint-amb-down-", cards)
    with tmp:
        _, out, _ = _judge(world)
        lines = out.splitlines()
        if not any("[CA704] warning" in ln and "未定序" in ln for ln in lines):
            problems.append(f"同刻多笔受方不同应报未定序 warning：\n{out}")
        if not any("[CA704] error" in ln and "holder.md" in ln for ln in lines):
            problems.append(
                "同刻未定序不得吞掉断言对账（holder 不在交集，须报 CA704 error）：\n" + out)

    # 交集非空：alice 同时在两笔候选里 → 放行；bob 只在一笔里 → 照报
    cards = {
        "giver": _card("giver", ""),
        "alice": _card("alice", "owns:\n  - gem-c\n"),
        "bob": _card("bob", "owns:\n  - gem-c\n"),
        "gem-c": _card("gem-c", ""),
        "ev-c1": ev("ev-c1",
                    "by:\n  - giver\nto:\n  - alice\n  - bob\nobject:\n  - gem-c\n"),
        "ev-c2": ev("ev-c2", "by:\n  - giver\nto:\n  - alice\nobject:\n  - gem-c\n"),
    }
    tmp, world = _temp_world("canonlint-amb-int-", cards)
    with tmp:
        _, out, _ = _judge(world)
        lines = out.splitlines()
        if any("[CA704] error" in ln and "alice.md" in ln for ln in lines):
            problems.append(f"alice 在全部候选的交集里，不该吃 CA704 error：\n{out}")
        if not any("[CA704] error" in ln and "bob.md" in ln for ln in lines):
            problems.append(f"bob 只在一笔候选里，不在交集，须报 CA704 error：\n{out}")
    return problems


def check_from_leg_is_legal() -> list[str]:
    """契约 0.8：`transfer`/`grant` 的 `from` 腿是「谁交出的」，与 `by` 分离。

    形状在 world.schema.json 里早已允许；这里钉语义：写了 `from` 不报 CA109/CA702，
    导出原样透出；缺 `from` 仍然合法（时序校验 fail-open，Task 3 才看它）。
    """
    problems = []

    def ev(eid: str, kind: str, legs: str) -> str:
        return _card(eid, f"when: 元年\nevent_kind: {kind}\nwhen_sort: 1\n{legs}"
                     ).replace("type: location", "type: event")

    tmp, world = _temp_world("canonlint-from-", {
        "alice": _card("alice", "").replace("type: location", "type: character"),
        "bob": _card("bob", "").replace("type: location", "type: character"),
        "sword": _card("sword", "").replace("type: location", "type: item"),
        "ev-give": ev("ev-give", "transfer",
                      "by:\n  - alice\nfrom:\n  - alice\nobject:\n  - sword\nto:\n  - bob\n"),
        "ev-grant": ev("ev-grant", "grant",
                       "by:\n  - bob\nfrom:\n  - alice\nobject:\n  - sword\nto:\n  - alice\n"),
    })
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"带 from 的转让把 traceback 写到了 stderr：\n{err}")
        if code != 0:
            problems.append(f"带 from 的转让应 exit 0，实际 {code}：\n{out}")
        bad = [ln for ln in out.splitlines() if "[CA109]" in ln or "[CA702]" in ln]
        if bad:
            problems.append(f"from 是合法腿，不该报形状/账平错误：\n" + "\n".join(bad))
        p = subprocess.run([PY, str(TOOL), "export", str(world)],
                           cwd=ROOT, capture_output=True, text=True)
        if p.stderr or p.returncode != 0:
            problems.append(f"导出带 from 的世界失败（exit={p.returncode}）：\n{p.stderr}")
        else:
            data = json.loads(p.stdout)
            evd = next((d for d in data["entries"] if d.get("id") == "ev-give"), None)
            if evd is None or evd.get("from") != ["alice"]:
                problems.append(f"事件卡的 from 没原样透出：{evd}")

    # 缺 from 仍然合法：旧世界不能被判红（fail-open）
    tmp, world = _temp_world("canonlint-from-absent-", {
        "alice": _card("alice", "").replace("type: location", "type: character"),
        "bob": _card("bob", "").replace("type: location", "type: character"),
        "sword": _card("sword", "").replace("type: location", "type: item"),
        "ev-give": ev("ev-give", "transfer",
                      "by:\n  - alice\nobject:\n  - sword\nto:\n  - bob\n"),
    })
    with tmp:
        code, out, err = _judge(world)
        if err or code != 0:
            problems.append(f"缺 from 的旧世界不该被判红（exit={code}）：\n{out}{err}")
    return problems


def check_certainty_three_states_in_export() -> list[str]:
    """契约 0.8：导出 `ledger.states[obj].certainty` 三态且取值受限。

    known：流水给出唯一结论（sword 一笔 transfer 到 bob）；
    unknown：没有这条客体的流水，只有手写结论断言（amulet 仅 owns 兜底）；
    ambiguous：同刻多笔转让受方不同（ring 同刻给 bob/carol），或断言互搏。
    """
    problems = []

    def ev(eid: str, kind: str, sort: int, legs: str) -> str:
        return _card(eid, f"when: 第{sort}年\nevent_kind: {kind}\nwhen_sort: {sort}\n{legs}"
                     ).replace("type: location", "type: event")

    tmp, world = _temp_world("canonlint-certainty-", {
        "alice": _card("alice", "owns:\n  - amulet\n"),
        "bob": _card("bob", ""), "carol": _card("carol", ""),
        "sword": _card("sword", ""), "amulet": _card("amulet", ""),
        "ring": _card("ring", ""),
        "ev-sword": ev("ev-sword", "transfer", 1,
                       "by:\n  - alice\nobject:\n  - sword\nto:\n  - bob\n"),
        "ev-ring-a": ev("ev-ring-a", "transfer", 2,
                        "by:\n  - alice\nobject:\n  - ring\nto:\n  - bob\n"),
        "ev-ring-b": ev("ev-ring-b", "transfer", 2,
                        "by:\n  - alice\nobject:\n  - ring\nto:\n  - carol\n"),
    })
    with tmp:
        p = subprocess.run([PY, str(TOOL), "export", str(world)],
                           cwd=ROOT, capture_output=True, text=True)
        if p.stderr or p.returncode != 0:
            problems.append(f"导出 certainty 世界失败（exit={p.returncode}）：\n{p.stderr}")
        else:
            states = json.loads(p.stdout)["ledger"]["states"]
            allowed = {"known", "unknown", "ambiguous"}
            for obj, st in states.items():
                if st.get("certainty") not in allowed:
                    problems.append(
                        f"{obj} 的 certainty 应是 {sorted(allowed)} 之一，实际 {st.get('certainty')!r}")
            want = {"sword": "known", "amulet": "unknown", "ring": "ambiguous"}
            for obj, expect in want.items():
                got = states.get(obj, {}).get("certainty")
                if got != expect:
                    problems.append(f"{obj} 的 certainty 应为 {expect}，实际 {got!r}")
    return problems


def check_custody_assertion_is_fallback_without_flow() -> list[str]:
    """契约 0.8：custody_of 断言是「当前结论」，没有 custody 流水时兜底成保管人。

    有流水时流水赢（断言只参与 CA709 对账）：
    - sword 只有 custody_of: [alice]，没有流水 → custodian=alice、certainty=unknown；
    - shield 断言给 alice，但有一笔 custody 流水交给 bob → custodian=bob、
      certainty=known（断言只用来跟流水对账，不覆盖流水结论）。
    """
    problems = []
    cards = {
        "alice": _card("alice", "custody_of:\n  - sword\n  - shield\n"),
        "bob": _card("bob", ""),
        "sword": _card("sword", "").replace("type: location", "type: item"),
        "shield": _card("shield", "").replace("type: location", "type: item"),
        "ev-shield": _card("ev-shield", (
            "when: 元年\nevent_kind: custody\nwhen_sort: 1\n"
            "by:\n  - carol\nobject:\n  - shield\nto:\n  - bob\n"
        )).replace("type: location", "type: event"),
        "carol": _card("carol", ""),
    }
    tmp, world = _temp_world("canonlint-custody-fallback-", cards)
    with tmp:
        p = subprocess.run([PY, str(TOOL), "export", str(world)],
                           cwd=ROOT, capture_output=True, text=True)
        if p.stderr or p.returncode != 0:
            problems.append(f"导出 custody 兜底世界失败（exit={p.returncode}）：\n{p.stderr}")
        else:
            states = json.loads(p.stdout)["ledger"]["states"]
            sword = states.get("sword", {})
            if sword.get("custodian") != "alice":
                problems.append(
                    f"无 custody 流水时 custody_of 断言应兜底保管人 alice，实际 {sword.get('custodian')!r}")
            if sword.get("certainty") != "unknown":
                problems.append(
                    f"只有断言没有流水时 certainty 应为 unknown，实际 {sword.get('certainty')!r}")
            shield = states.get("shield", {})
            if shield.get("custodian") != "bob":
                problems.append(
                    f"有 custody 流水时流水应赢：custodian 应为 bob，实际 {shield.get('custodian')!r}")
            if shield.get("certainty") != "known":
                problems.append(
                    f"有唯一 custody 流水时 certainty 应为 known，实际 {shield.get('certainty')!r}")
    return problems


def check_member_of_assertion_is_fallback_without_flow() -> list[str]:
    """契约 0.8：member_of 断言是「当前结论」，没有 join/leave 流水时兜底成在册。

    有流水时流水赢：
    - jon 只有 member_of: [order-a]，没有流水 → order-a=join；
    - arya 断言 order-b，另有一笔 join 到 order-c → order-b 兜底 join、order-c 流水 join；
    - sansa 没有断言，join/leave 流水都在 order-a → 最后离开，order-a=leave。
    """
    problems = []
    cards = {
        "order-a": _card("order-a", ""), "order-b": _card("order-b", ""),
        "order-c": _card("order-c", ""),
        "jon": _card("jon", "member_of:\n  - order-a\n").replace(
            "type: location", "type: person"),
        "arya": _card("arya", "member_of:\n  - order-b\n").replace(
            "type: location", "type: person"),
        "sansa": _card("sansa", "").replace("type: location", "type: person"),
        "ev-arya": _card("ev-arya", (
            "when: 元年\nevent_kind: join\nwhen_sort: 1\n"
            "by:\n  - arya\nto:\n  - order-c\n"
        )).replace("type: location", "type: event"),
        "ev-sansa-join": _card("ev-sansa-join", (
            "when: 元年\nevent_kind: join\nwhen_sort: 1\n"
            "by:\n  - sansa\nto:\n  - order-a\n"
        )).replace("type: location", "type: event"),
        "ev-sansa-leave": _card("ev-sansa-leave", (
            "when: 三年\nevent_kind: leave\nwhen_sort: 3\n"
            "by:\n  - sansa\nfrom:\n  - order-a\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-member-fallback-", cards)
    with tmp:
        p = subprocess.run([PY, str(TOOL), "export", str(world)],
                           cwd=ROOT, capture_output=True, text=True)
        if p.stderr or p.returncode != 0:
            problems.append(f"导出 member_of 兜底世界失败（exit={p.returncode}）：\n{p.stderr}")
        else:
            membership = json.loads(p.stdout)["ledger"]["membership"]
            want = {
                "jon": {"order-a": "join"},
                "_arya_order_b": {"order-b": "join"},
                "_arya_order_c": {"order-c": "join"},
                "sansa": {"order-a": "leave"},
            }
            got = {
                "jon": membership.get("jon", {}),
                "_arya_order_b": {"order-b": membership.get("arya", {}).get("order-b")},
                "_arya_order_c": {"order-c": membership.get("arya", {}).get("order-c")},
                "sansa": membership.get("sansa", {}),
            }
            for who, expect in want.items():
                if got[who] != expect:
                    problems.append(f"{who} 的组织归属应为 {expect}，实际 {got[who]}")
    return problems


def check_death_events_are_checked_as_actors() -> list[str]:
    """CA705 覆盖 death 事件自身：死人在更晚的另一笔 death 里不能当施动者（协议 1.8）。"""
    cards = {
        "person-a": _card("person-a", ""),
        "person-b": _card("person-b", ""),
        "ev-a": _card("ev-a", (
            "when: 元年\nevent_kind: death\nwhen_sort: 1\nobject:\n  - person-a\n"
        )).replace("type: location", "type: event"),
        "ev-b": _card("ev-b", (
            "when: 五年\nevent_kind: death\nwhen_sort: 5\nby:\n  - person-a\nobject:\n  - person-b\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-death-actor-", cards)
    problems = []
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"death 事件把 traceback 写到了 stderr：\n{err}")
        hit = [ln for ln in out.splitlines() if "[CA705]" in ln and "ev-b.md" in ln]
        if not hit:
            problems.append(f"死人在更晚的 death 事件里当 by，应报 CA705：\n{out}")
    return problems



def check_event_legs_are_window_checked() -> list[str]:
    """审计 §1.1：CA705 把 destroy 当死亡；CA708 查 by/from/to 腿，而不只是 object。"""
    problems = []

    # (a) destroy 后仍是 by 腿的施动者 → CA705；CA708 不双报
    cards = {
        "hero": _card("hero", ""),
        "keeper": _card("keeper", ""),
        "gem": _card("gem", ""),
        "ev-destroy": _card("ev-destroy", (
            "when: 元年\nevent_kind: destroy\nwhen_sort: 2\nobject:\n  - hero\n"
        )).replace("type: location", "type: event"),
        "ev-use": _card("ev-use", (
            "when: 三年\nevent_kind: transfer\nwhen_sort: 3\n"
            "by:\n  - hero\nto:\n  - keeper\nobject:\n  - gem\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legs-destroy-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"destroy 后当 by 把 traceback 写到了 stderr：\n{err}")
        if not any("[CA705]" in ln and "ev-use.md" in ln for ln in out.splitlines()):
            problems.append(f"destroy 后的人当 by 应报 CA705：\n{out}")
        if any("[CA708]" in ln and "ev-use.md" in ln for ln in out.splitlines()):
            problems.append(f"destroy 当 by 已由 CA705 负责，CA708 不该双报：\n{out}")

    # (b) join 早于 birth → CA708（by 腿，未生者做事）
    cards = {
        "order": _card("order", ""),
        "hero": _card("hero", ""),
        "ev-join": _card("ev-join", (
            "when: 元年\nevent_kind: join\nwhen_sort: 1\nby:\n  - hero\nto:\n  - order\n"
        )).replace("type: location", "type: event"),
        "ev-birth": _card("ev-birth", (
            "when: 二年\nevent_kind: birth\nwhen_sort: 2\nobject:\n  - hero\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legs-join-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"join 早于 birth 把 traceback 写到了 stderr：\n{err}")
        if not any("[CA708]" in ln and "ev-join.md" in ln for ln in out.splitlines()):
            problems.append(f"join 的 by 尚未出生应报 CA708：\n{out}")

    # (c) death 之后当 to 腿（受方也须在窗口内）→ CA708
    cards = {
        "a": _card("a", ""),
        "hero": _card("hero", ""),
        "gem": _card("gem", ""),
        "ev-death": _card("ev-death", (
            "when: 元年\nevent_kind: death\nwhen_sort: 1\nobject:\n  - a\n"
        )).replace("type: location", "type: event"),
        "ev-transfer": _card("ev-transfer", (
            "when: 二年\nevent_kind: transfer\nwhen_sort: 2\n"
            "by:\n  - hero\nto:\n  - a\nobject:\n  - gem\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legs-dead-to-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"dead to 把 traceback 写到了 stderr：\n{err}")
        if not any("[CA708]" in ln and "ev-transfer.md" in ln for ln in out.splitlines()):
            problems.append(f"死人当 to 受方应报 CA708：\n{out}")

    # (d) destroy 之后当 from 腿（起点已不存在）→ CA708
    cards = {
        "loc1": _card("loc1", ""),
        "loc2": _card("loc2", ""),
        "gem": _card("gem", ""),
        "ev-destroy": _card("ev-destroy", (
            "when: 元年\nevent_kind: destroy\nwhen_sort: 1\nobject:\n  - loc1\n"
        )).replace("type: location", "type: event"),
        "ev-move": _card("ev-move", (
            "when: 二年\nevent_kind: move\nwhen_sort: 2\n"
            "object:\n  - gem\nfrom:\n  - loc1\nto:\n  - loc2\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legs-from-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"destroyed from 把 traceback 写到了 stderr：\n{err}")
        if not any("[CA708]" in ln and "ev-move.md" in ln for ln in out.splitlines()):
            problems.append(f"被毁地点的 from 应报 CA708：\n{out}")

    # (e) #44：端点 death 事件的死后 by 也归 CA705，CA708 不得双报
    cards = {
        "killer": _card("killer", ""),
        "hero": _card("hero", ""),
        "ev-killer-death": _card("ev-killer-death", (
            "when: 元年\nevent_kind: death\nwhen_sort: 1\nobject:\n  - killer\n"
        )).replace("type: location", "type: event"),
        "ev-hero-death": _card("ev-hero-death", (
            "when: 二年\nevent_kind: death\nwhen_sort: 2\n"
            "by:\n  - killer\nobject:\n  - hero\n"
        )).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-legs-endpoint-by-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"端点事件死后 by 把 traceback 写到了 stderr：\n{err}")
        hits705 = [ln for ln in out.splitlines()
                   if "[CA705]" in ln and "ev-hero-death.md" in ln]
        hits708 = [ln for ln in out.splitlines()
                   if "[CA708]" in ln and "ev-hero-death.md" in ln]
        if len(hits705) != 1:
            problems.append(f"死人当死亡事件的 by 应恰好报一条 CA705：\n{out}")
        if hits708:
            problems.append(f"CA705 已报的死后 by，CA708 不该再报（#44）：\n{out}")
    return problems


def check_null_relation_fields_are_shape_errors() -> list[str]:
    """issue #43：显式 null 的关系字段不能被当成「没写」——CA109 报，--strict 不得全绿。"""
    problems = []
    body = "正文" * 120
    cases = {
        "depends_on: null": _card("a", "depends_on: null\nlayer: ideology\n",
                                  load_bearing=True, body=body),
        "relations: null": _card("a", "relations: null\n", body=body),
        "canon_refs: null": _card("a", "canon_refs: null\n", body=body),
        "conflicts_with: null": _card("a", "conflicts_with: null\n", body=body),
        "owns: null": _card("a", "owns: null\n", body=body),
    }
    for label, text in cases.items():
        tmp, world = _temp_world("canonlint-null-rel-", {"a": text})
        with tmp:
            code, out, err = _judge(world, "--strict")
            if err:
                problems.append(f"null 关系字段（{label}）traceback：\n{err}")
            if code != 1:
                problems.append(f"null 关系字段（{label}）应 --strict exit 1，实际 {code}：\n{out}")
            if not any("[CA109]" in ln and "a.md" in ln for ln in out.splitlines()):
                problems.append(f"null 关系字段（{label}）应报 CA109：\n{out}")
    return problems


def check_ca111_recognizes_contract_alias_spellings() -> list[str]:
    """issue #45：契约登记的字段名拼法（depends-on）也要给 CA111 迁移提示。"""
    problems = []
    body = "正文" * 120
    cards = {
        "b": _card("b", body=body),
        "a": _card("a", "depends-on:\n  - id: b\n    kind: legitimacy\n",
                   body=body),
    }
    tmp, world = _temp_world("canonlint-ca111-alias-", cards)
    with tmp:
        p = subprocess.run([PY, str(TOOL), str(world)], cwd=ROOT,
                           capture_output=True, text=True)
        out, err = p.stdout, p.stderr
        if err:
            problems.append(f"depends-on 别名 traceback：\n{err}")
        if not any("[CA111]" in ln and "a.md" in ln for ln in out.splitlines()):
            problems.append(f"depends-on 别名的迁移提示缺失：\n{out}")
    return problems


def check_canonical_relations_validate_attrs_per_relation() -> list[str]:
    """#40 F1：规范形的注解键按**关系名**校验，与旧写法同判。"""
    problems = []
    body = "正文" * 120
    cases = [
        ("named owns note", "owns:\n  - id: b\n    note: ok\n", None, True),
        ("canonical owns note", "relations:\n  - type: owns\n    target: b\n    note: ok\n", None, True),
        ("named owns what", "owns:\n  - id: b\n    what: grain\n", "CA107", True),
        ("canonical owns what", "relations:\n  - type: owns\n    target: b\n    what: grain\n", "CA107", True),
        ("named canon_refs kind", "canon_refs:\n  - id: b\n    kind: x\n", "CA109", False),
        ("canonical canon_refs kind",
         "relations:\n  - type: canon_refs\n    target: b\n    kind: x\n", "CA109", True),
        ("canonical owns x-ext",
         "relations:\n  - type: owns\n    target: b\n    x-note: ok\n", None, True),
    ]
    for label, extra, rule, tmpl in cases:
        entries = {"a": _card("a", extra, body=body, template_relations=tmpl),
                   "b": _card("b", body="另一段正文" * 40)}
        tmp, world = _temp_world("world-canonical-attrs-", entries)
        try:
            code, out, err = _judge(world, "--strict")
            if err:
                problems.append(f"{label} traceback：\n{err}")
                continue
            if rule is None:
                if code != 0:
                    problems.append(f"{label} 应 exit 0，实际 {code}：\n{out}")
            else:
                if code != 1:
                    problems.append(f"{label} 应 --strict exit 1，实际 {code}：\n{out}")
                if f"[{rule}]" not in out:
                    problems.append(f"{label} 应报 {rule}：\n{out}")
        finally:
            tmp.cleanup()
    return problems


def check_event_fields_only_on_event_cards() -> list[str]:
    """#40 F2：非事件卡上的 when / when_sort 也报 CA109（协议 1.8）。"""
    problems = []
    body = "正文" * 120
    for extra in ("when: 元年\n", "when_sort: 1\n", "when: 元年\nwhen_sort: 1\n"):
        entries = {"a": _card("a", extra, body=body)}
        tmp, world = _temp_world("world-eventfield-", entries)
        try:
            code, out, err = _judge(world, "--strict")
            if err:
                problems.append(f"{extra!r} traceback：\n{err}")
                continue
            if code != 1:
                problems.append(f"{extra!r} 应 --strict exit 1，实际 {code}：\n{out}")
            if "[CA109]" not in out or "事件字段" not in out:
                problems.append(f"{extra!r} 应报 CA109 事件字段只能出现在 event 卡上：\n{out}")
        finally:
            tmp.cleanup()
    return problems


def check_broken_yaml_does_not_fake_dangling_refs() -> list[str]:
    """#40 F3：坏 YAML 的卡不该让引用方被报成「指向不存在的 id」。"""
    problems = []
    body = "正文" * 120
    entries = {"a": _card("a", "canon_refs:\n  - old\n", body=body)}
    tmp, world = _temp_world("world-brokenref-", entries)
    try:
        (world / "entries" / "old.md").write_text(
            "---\nid: old\ntitle: 坏卡\n  bad: [unclosed\n---\n\n正文\n",
            encoding="utf-8")
        code, out, err = _judge(world, "--strict")
        if err:
            problems.append(f"坏 YAML 世界 traceback：\n{err}")
            return problems
        if code != 1 or "[CA100]" not in out:
            problems.append(f"坏卡应报 CA100 且 --strict exit 1，实际 {code}：\n{out}")
        if "[CA401]" in out:
            problems.append(f"引用方不该被报「指向不存在的 id」：\n{out}")
    finally:
        tmp.cleanup()
    return problems


def check_ca103_rejects_datetime() -> list[str]:
    """issue #46：date 只收日期，不收带时间的 datetime。"""
    problems = []
    body = "正文" * 120
    text = _card("a", body=body).replace("date: 2026-01-01",
                                         "date: 2026-01-01T08:00:00")
    tmp, world = _temp_world("canonlint-datetime-", {"a": text})
    with tmp:
        p = subprocess.run([PY, str(TOOL), str(world), "--strict"], cwd=ROOT,
                           capture_output=True, text=True)
        out, err = p.stdout, p.stderr
        if err:
            problems.append(f"datetime date traceback：\n{err}")
        if p.returncode != 1:
            problems.append(f"datetime date 应 --strict exit 1，实际 {p.returncode}：\n{out}")
        if not any("[CA103]" in ln for ln in out.splitlines()):
            problems.append(f"datetime date 应报 CA103：\n{out}")
    return problems


def check_issue38_ownership_source_and_status() -> list[str]:
    """issue #38 57/60：交出者必须是断言持有人；draft 断言不能当正史持有源。"""
    problems = []
    problems += _expect_strict_rejection(
        "canonlint-issue38-source-",
        {
            "gem": _card("gem", body=_issue38_body("gem")).replace(
                "type: location", "type: item"),
            "alice": _card("alice", body=_issue38_body("alice")).replace(
                "type: location", "type: character"),
            "bob": _card("bob", "owns:\n  - gem\n", body=_issue38_body("bob")).replace(
                "type: location", "type: character"),
            "ev-transfer": _card("ev-transfer", (
                "when: 元年\nevent_kind: transfer\nwhen_sort: 1\n"
                "by:\n  - alice\nfrom:\n  - alice\nto:\n  - bob\nobject:\n  - gem\n"
            ), body=_issue38_body("ev-transfer")).replace("type: location", "type: event"),
        },
        label="gem 由 bob 持有，第一笔 transfer 却由 alice 交出",
        rules=("CA703", "CA713", "CA714"),
        entry_any=("ev-transfer.md", "alice.md", "bob.md"),
    )
    problems += _expect_strict_rejection(
        "canonlint-issue38-draft-owns-",
        {
            "gem": _card("gem", body=_issue38_body("gem")).replace(
                "type: location", "type: item"),
            "alice": _card("alice", body=_issue38_body("alice")).replace(
                "type: location", "type: character"),
            "bob": _card("bob", "owns:\n  - gem\n", status="draft",
                         body=_issue38_body("bob")).replace(
                             "type: location", "type: character"),
            "ev-transfer": _card("ev-transfer", (
                "when: 元年\nevent_kind: transfer\nwhen_sort: 1\n"
                "by:\n  - alice\nfrom:\n  - alice\nto:\n  - bob\nobject:\n  - gem\n"
            ), body=_issue38_body("ev-transfer")).replace("type: location", "type: event"),
        },
        label="draft 卡的 owns 断言被当成正史持有源",
        rules=("CA402", "CA404", "CA703", "CA704", "CA707", "CA714"),
        entry_any=("bob.md", "gem.md", "ev-transfer.md"),
    )
    return problems


def check_issue38_material_anchor_requires_layer() -> list[str]:
    """issue #38 58/59：CA503 的物质锚点不能是无 layer 的卡片。"""
    problems = []
    for layer, source in (("economy", "eco"), ("fiscal", "fis")):
        problems += _expect_strict_rejection(
            f"canonlint-issue38-{layer}-anchor-",
            {
                source: _card(source, (
                    f"layer: {layer}\n"
                    "depends_on:\n"
                    "  - id: idea\n"
                    "    kind: resource\n"
                    "    critical: true\n"
                ), load_bearing=True, body=_issue38_body(source)).replace(
                    "type: location", "type: faction"),
                "idea": _card("idea", body=_issue38_body("idea")),
            },
            label=f"{layer} 承重墙依赖无 layer 的物质目标",
            rules=("CA501", "CA503", "CA714"),
            entry_any=(f"{source}.md", "idea.md"),
        )
    return problems


def check_issue38_endpoint_actors_exist() -> list[str]:
    """issue #38 63–65：端点事件也要查 by 施动者的存在窗口。"""
    problems = []
    problems += _expect_strict_rejection(
        "canonlint-issue38-death-actor-",
        {
            "hero": _card("hero", body=_issue38_body("hero")).replace(
                "type: location", "type: character"),
            "killer": _card("killer", body=_issue38_body("killer")).replace(
                "type: location", "type: character"),
            "ev-birth": _card("ev-birth", (
                "when: 元年\nevent_kind: birth\nwhen_sort: 2\nobject:\n  - killer\n"
            ), body=_issue38_body("ev-birth")).replace("type: location", "type: event"),
            "ev-death": _card("ev-death", (
                "when: 元年\nevent_kind: death\nwhen_sort: 1\n"
                "by:\n  - killer\nobject:\n  - hero\n"
            ), body=_issue38_body("ev-death")).replace("type: location", "type: event"),
        },
        label="killer 在出生前杀人",
        rules=("CA708", "CA714"),
        entry_any=("ev-death.md",),
    )
    problems += _expect_strict_rejection(
        "canonlint-issue38-destroy-actor-",
        {
            "old": _card("old", body=_issue38_body("old")).replace(
                "type: location", "type: item"),
            "killer": _card("killer", body=_issue38_body("killer")).replace(
                "type: location", "type: character"),
            "ev-birth": _card("ev-birth", (
                "when: 元年\nevent_kind: birth\nwhen_sort: 2\nobject:\n  - killer\n"
            ), body=_issue38_body("ev-birth")).replace("type: location", "type: event"),
            "ev-destroy": _card("ev-destroy", (
                "when: 元年\nevent_kind: destroy\nwhen_sort: 1\n"
                "by:\n  - killer\nobject:\n  - old\n"
            ), body=_issue38_body("ev-destroy")).replace("type: location", "type: event"),
        },
        label="killer 在出生前销毁物品",
        rules=("CA708", "CA714"),
        entry_any=("ev-destroy.md",),
    )
    problems += _expect_strict_rejection(
        "canonlint-issue38-transform-actor-",
        {
            "old": _card("old", body=_issue38_body("old")).replace(
                "type: location", "type: item"),
            "new": _card("new", body=_issue38_body("new")).replace(
                "type: location", "type: item"),
            "smith": _card("smith", body=_issue38_body("smith")).replace(
                "type: location", "type: character"),
            "ev-birth": _card("ev-birth", (
                "when: 元年\nevent_kind: birth\nwhen_sort: 2\nobject:\n  - smith\n"
            ), body=_issue38_body("ev-birth")).replace("type: location", "type: event"),
            "ev-transform": _card("ev-transform", (
                "when: 元年\nevent_kind: transform\nwhen_sort: 1\n"
                "by:\n  - smith\nobject:\n  - old\nresult:\n  - new\n"
            ), body=_issue38_body("ev-transform")).replace("type: location", "type: event"),
        },
        label="smith 在出生前完成转化",
        rules=("CA708", "CA714"),
        entry_any=("ev-transform.md",),
    )
    return problems


def check_issue38_membership_types() -> list[str]:
    """issue #38 61/62：member_of 的主体与目标都要有类型门禁。"""
    problems = []
    problems += _expect_strict_rejection(
        "canonlint-issue38-member-location-",
        {
            "loc": _card("loc", "member_of:\n  - org\n",
                         body=_issue38_body("loc")),
            "org": _card("org", body=_issue38_body("org")).replace(
                "type: location", "type: faction"),
        },
        label="地点是组织成员",
        rules=("CA712", "CA714"),
        entry_any=("loc.md", "org.md"),
    )
    problems += _expect_strict_rejection(
        "canonlint-issue38-member-event-",
        {
            "a": _card("a", "member_of:\n  - ev\n",
                       body=_issue38_body("a")).replace(
                           "type: location", "type: character"),
            "ev": _card("ev", (
                "when: 元年\nevent_kind: modify\nobject:\n  - a\n"
            ), body=_issue38_body("ev")).replace("type: location", "type: event"),
        },
        label="人属于一个事件",
        rules=("CA712", "CA714"),
        entry_any=("a.md", "ev.md"),
    )
    return problems


def check_layer_shape_does_not_crash() -> list[str]:
    """#41：layer 写坏只能报 CA102，不许在集合/索引访问里 traceback。"""
    problems = []
    body = "正文" * 120
    cards = {
        "src": _card("src", (
            "layer: economy\n"
            "depends_on:\n"
            "  - id: bad\n"
            "    kind: resource\n"
            "    critical: true\n"
        ), load_bearing=True, body=body).replace("type: location", "type: faction"),
        "bad": _card("bad", "layer:\n  - fiscal\n", body=body).replace(
            "type: location", "type: faction"),
    }
    tmp, world = _temp_world("canonlint-layer-shape-", cards)
    with tmp:
        checks = [
            ("registry", None, ()),
            ("registry --impact", None, ("--impact", "src")),
        ]
        for label, env, args in checks:
            code, out, err = _judge(world, *args)
            if err:
                problems.append(f"layer 坏形状（{label}）把 traceback 写到 stderr：\n{err}")
            if code != 1:
                problems.append(f"layer 坏形状（{label}）应因 CA102 exit 1，实际 {code}")
            if not any("[CA102]" in ln and "bad.md" in ln for ln in out.splitlines()):
                problems.append(f"layer 坏形状（{label}）应报 CA102：\n{out}")
    return problems


def check_x_kind_cycles_are_reported() -> list[str]:
    """#38 52–56：x- 是泄压阀，但 x- 类别成环/自环不能被 CA502 静默。"""
    problems = []
    cards = {
        "a": _card("a", (
            "load_bearing: true\nlayer: economy\n"
            "depends_on:\n  - id: b\n    kind: x-loop\n    critical: true\n"
        ), load_bearing=True, body=_issue38_body("a")).replace(
            "type: location", "type: faction"),
        "b": _card("b", (
            "load_bearing: true\nlayer: economy\n"
            "depends_on:\n  - id: a\n    kind: x-loop\n    critical: true\n"
        ), load_bearing=True, body=_issue38_body("b")).replace(
            "type: location", "type: faction"),
        "c": _card("c", (
            "load_bearing: true\nlayer: economy\n"
            "depends_on:\n  - id: c\n    kind: x-loop\n    critical: true\n"
        ), load_bearing=True, body=_issue38_body("c")).replace(
            "type: location", "type: faction"),
        "d": _card("d", (
            "load_bearing: true\nlayer: economy\n"
            "depends_on:\n  - id: e\n    kind: x-loop\n    critical: true\n"
        ), load_bearing=True, body=_issue38_body("d")).replace(
            "type: location", "type: faction"),
        "e": _card("e", "load_bearing: true\nlayer: resource\n",
                   load_bearing=True, body=_issue38_body("e")).replace(
            "type: location", "type: faction"),
    }
    tmp, world = _temp_world("canonlint-x-kind-cycle-", cards)
    with tmp:
        code, out, err = _judge(world)
        if "Traceback" in err:
            problems.append(f"x- 成环写出了 traceback：\n{err}")
        if code != 1:
            problems.append(f"x- 成环应因 CA502 exit 1，实际 {code}")
        if out.count("[CA502]") != 2:
            problems.append(
                f"x- 成环应报 2 个环（a↔b、c 自环）且不把 d→e 误报，实际：\n{out}")
    return problems


def check_ca201_catches_short_exact_duplicates() -> list[str]:
    """#38：96 字的完全重复正文不再因「低于 100 字」静默。"""
    problems = []
    body = "同一段正文" * 16  # 80 字
    cards = {
        "a-dup": _card("a-dup", status="canon", body=body),
        "b-dup": _card("b-dup", status="canon", body=body),
    }
    tmp, world = _temp_world("canonlint-ca201-short-", cards)
    with tmp:
        _, out, _ = _judge(world)
        if "[CA201]" not in out:
            problems.append(f"短正文精确重复漏报 CA201：\n{out}")
    # 反面：不同的短正文不报
    tmp2, world2 = _temp_world("canonlint-ca201-short-ok-", {
        "a-dup": _card("a-dup", status="canon", body=body),
        "b-dup": _card("b-dup", status="canon", body="另一段不同的正文" * 10),
    })
    with tmp2:
        _, out, _ = _judge(world2)
        if "[CA201]" in out:
            problems.append(f"不同的短正文误报 CA201：\n{out}")
    return problems


def check_member_chain_is_paired() -> list[str]:
    """#38 成员链：leave 之前必须有过 join，或用 member_of 说明初始成员。"""
    problems = []

    def card(eid: str, t: str, extra: str = "") -> str:
        return _card(eid, extra).replace("type: location", f"type: {t}")

    def ev(extra: str) -> str:
        return _card("ev-x", extra).replace("type: location", "type: event")

    org = card("org", "faction")
    person = card("alice", "character")
    lone = card("bob", "character")
    member_of = card("carol", "character", "member_of: [org]\n")
    base = {"org": org, "alice": person, "bob": lone, "carol": member_of}

    cases = [
        ("leave 无 join", dict(base, **{"leave-1": ev(
            "id: leave-1\ntype: event\nevent_kind: leave\nwhen: \"297 AC\"\n"
            "when_sort: 297\nby:\n  - bob\nfrom:\n  - org\n")}), "CA719", True),
        ("join 后 leave", dict(base,
            **{"join-1": ev(
                "id: join-1\ntype: event\nevent_kind: join\nwhen: \"293 AC\"\n"
                "when_sort: 293\nby:\n  - alice\nto:\n  - org\n")},
            **{"leave-1": ev(
                "id: leave-1\ntype: event\nevent_kind: leave\nwhen: \"297 AC\"\n"
                "when_sort: 297\nby:\n  - alice\nfrom:\n  - org\n")}), "CA719", False),
        ("member_of 初始成员", dict(base, **{"leave-1": ev(
            "id: leave-1\ntype: event\nevent_kind: leave\nwhen: \"297 AC\"\n"
            "when_sort: 297\nby:\n  - carol\nfrom:\n  - org\n")}), "CA719", False),
        ("同刻 join/leave 未定序", dict(base,
            **{"join-1": ev(
                "id: join-1\ntype: event\nevent_kind: join\nwhen: \"297 AC\"\n"
                "when_sort: 297\nby:\n  - bob\nto:\n  - org\n")},
            **{"leave-1": ev(
                "id: leave-1\ntype: event\nevent_kind: leave\nwhen: \"297 AC\"\n"
                "when_sort: 297\nby:\n  - bob\nfrom:\n  - org\n")}), "CA719", False),
    ]
    for label, cards, rule, want in cases:
        tmp, world = _temp_world("canonlint-ca719-", cards)
        with tmp:
            _code, out, _err = _judge(world)
            hit = f"[{rule}]" in out
            if want and not hit:
                problems.append(f"{label}：漏报 {rule}：\n{out}")
            if not want and hit:
                problems.append(f"{label}：误报 {rule}：\n{out}")
    return problems


def check_supersede_chain_is_checked() -> list[str]:
    """#38 承接链：承接者必须已定档、同类型、不成环（CA718）。"""
    problems = []

    def typed(eid: str, t: str, extra: str = "") -> str:
        return _card(eid, extra).replace("type: location", f"type: {t}")

    cases = [
        ("承接者未定档", {
            "old": typed("old", "event", "status: archived\nsuperseded_by: succ\n"),
            "succ": typed("succ", "event", "status: draft\n"),
        }, "CA718", True),
        ("承接者类型不符", {
            "old": typed("old", "event", "status: archived\nsuperseded_by: sword\n"),
            "sword": typed("sword", "item", "status: canon\n"),
        }, "CA718", True),
        ("承接链成环", {
            "a": typed("a", "event", "status: archived\nsuperseded_by: b\n"),
            "b": typed("b", "event", "status: archived\nsuperseded_by: a\n"),
        }, "CA718", True),
        ("正常承接", {
            "old": typed("old", "event", "status: archived\nsuperseded_by: succ\n"),
            "succ": typed("succ", "event", "status: canon\n"),
        }, "CA718", False),
    ]
    for label, cards, rule, want in cases:
        tmp, world = _temp_world("canonlint-ca718-", cards)
        with tmp:
            _code, out, _err = _judge(world)
            hit = f"[{rule}]" in out
            if want and not hit:
                problems.append(f"{label}：漏报 {rule}：\n{out}")
            if not want and hit:
                problems.append(f"{label}：误报 {rule}：\n{out}")
    return problems


def check_event_leg_types_are_checked() -> list[str]:
    """#38：事件腿指向的实体类型必须与事件语义相符（CA717）。"""
    problems = []

    def ev(eid: str, kind: str, legs: str) -> str:
        return _card(eid, f"when: 元年\nevent_kind: {kind}\nwhen_sort: 1\n{legs}"
                     ).replace("type: location", "type: event")

    def typed(eid: str, t: str) -> str:
        return _card(eid, "").replace("type: location", f"type: {t}")

    cases = [
        ("剑当施动者", ev("ev-x", "transfer",
                        "by:\n  - sword\nobject:\n  - stone\nto:\n  - bob\n"),
         "CA717", True),
        ("move 到人", ev("ev-x", "move", "object:\n  - alice\nto:\n  - bob\n"),
         "CA717", True),
        ("join 到人", ev("ev-x", "join", "by:\n  - alice\nto:\n  - bob\n"),
         "CA717", True),
        ("正常转让", ev("ev-x", "transfer",
                       "by:\n  - alice\nobject:\n  - stone\nto:\n  - bob\n"),
         "CA717", False),
    ]
    for label, event_card, rule, want in cases:
        cards = {
            "alice": typed("alice", "character"),
            "bob": typed("bob", "character"),
            "sword": typed("sword", "item"),
            "stone": typed("stone", "item"),
            "home": typed("home", "location"),
            "ev-x": event_card,
        }
        tmp, world = _temp_world("canonlint-ca717-", cards)
        with tmp:
            p1 = subprocess.run([PY, str(TOOL), str(world)], cwd=ROOT,
                                capture_output=True, text=True)
            hit = f"[{rule}]" in p1.stdout
            if want and not hit:
                problems.append(f"{label} 漏报 {rule}：\n{p1.stdout}")
            if not want and hit:
                problems.append(f"{label} 误报 {rule}：\n{p1.stdout}")
    return problems


def check_when_and_when_sort_must_agree() -> list[str]:
    """#38：when 是数字时，故事时间与 when_sort 方向不能相反（CA716 warning）。"""
    problems = []
    def world_for(when_a: str, when_b: str, ts_a: str = "1", ts_b: str = "2"):
        cards = {
            "obj": _card("obj", body=_issue38_body("obj")).replace(
                "type: location", "type: item"),
            "ev-a": _card("ev-a", (
                f"when: {when_a}\nevent_kind: create\nwhen_sort: {ts_a}\nobject:\n  - obj\n"
            ), body=_issue38_body("ev-a")).replace("type: location", "type: event"),
            "ev-b": _card("ev-b", (
                f"when: {when_b}\nevent_kind: destroy\nwhen_sort: {ts_b}\nobject:\n  - obj\n"
            ), body=_issue38_body("ev-b")).replace("type: location", "type: event"),
        }
        return _temp_world("canonlint-ca716-", cards)
    cases = [
        ("when 反向", "5", "2", True),
        ("when 同向", "2", "5", False),
        ("when 是文本", "元年", "二年", False),
    ]
    for label, when_a, when_b, want in cases:
        tmp, world = world_for(when_a, when_b)
        with tmp:
            p1 = subprocess.run([PY, str(TOOL), str(world)], cwd=ROOT,
                                capture_output=True, text=True)
            hit = "[CA716]" in p1.stdout
            if want and not hit:
                problems.append(f"{label} 漏报 CA716：\n{p1.stdout}")
            if not want and hit:
                problems.append(f"{label} 误报 CA716：\n{p1.stdout}")
    return problems


def check_ca703_creation_exemption_is_first_transfer_only() -> list[str]:
    """#42：create/birth 只豁免第一笔转手；之后 from 必须命中持有证据。"""
    problems = []
    cards = {
        "gem": _card("gem", body=_issue38_body("gem")).replace(
            "type: location", "type: item"),
        "alice": _card("alice", body=_issue38_body("alice")).replace(
            "type: location", "type: character"),
        "bob": _card("bob", body=_issue38_body("bob")).replace(
            "type: location", "type: character"),
        "carol": _card("carol", body=_issue38_body("carol")).replace(
            "type: location", "type: character"),
        "dave": _card("dave", body=_issue38_body("dave")).replace(
            "type: location", "type: character"),
        "ev-create": _card("ev-create", (
            "when: 元年\nevent_kind: create\nwhen_sort: 1\nobject:\n  - gem\n"
        ), body=_issue38_body("ev-create")).replace("type: location", "type: event"),
        "ev-t1": _card("ev-t1", (
            "when: 二年\nevent_kind: transfer\nwhen_sort: 2\nby:\n  - bob\n"
            "from:\n  - bob\nto:\n  - bob\n  - carol\nobject:\n  - gem\n"
        ), body=_issue38_body("ev-t1")).replace("type: location", "type: event"),
        "ev-t2": _card("ev-t2", (
            "when: 三年\nevent_kind: transfer\nwhen_sort: 3\nby:\n  - alice\n"
            "from:\n  - alice\nto:\n  - dave\nobject:\n  - gem\n"
        ), body=_issue38_body("ev-t2")).replace("type: location", "type: event"),
    }
    tmp, world = _temp_world("canonlint-ca703-first-", cards)
    with tmp:
        code, out, err = _judge(world, "--strict")
        if err:
            problems.append(f"CA703 首笔豁免把 traceback 写到了 stderr：\n{err}")
        if code != 1:
            problems.append(f"CA703 第二笔非持有人交出应 --strict exit 1，实际 {code}：\n{out}")
        if not any("[CA703]" in ln and "ev-t2.md" in ln
                   and "交出者不是持有人" in ln and "alice" in ln
                   for ln in out.splitlines()):
            problems.append(f"第二笔由 alice 交出应在 ev-t2 报 CA703：\n{out}")
        if any("[CA703]" in ln and "ev-t1.md" in ln for ln in out.splitlines()):
            problems.append(f"create 后的第一笔转手应豁免 CA703：\n{out}")
    return problems


def check_canon_card_referencing_non_canon() -> list[str]:
    """#38 状态门禁：canon 卡通过 owns 引用 draft 目标 → CA715；目标升格后不报。"""
    problems = []
    body = "正文" * 120
    canon = (_card("lord", "owns:\n  - relic\n", body=body)
             .replace("type: location", "type: faction"))
    draft = _card("relic", body=body, status="draft")
    cases = {"draft 目标": (draft, True), "canon 目标": (_card("relic", body=body), False)}
    for label, (target_card, want) in cases.items():
        if not want:
            target_card = target_card.replace("status: draft", "status: canon")
        tmp, world = _temp_world(f"world-ca715-{label}-", {"lord": canon, "relic": target_card})
        try:
            p1 = subprocess.run([PY, str(TOOL), str(world)], cwd=ROOT,
                                capture_output=True, text=True)
            hit = "[CA715]" in p1.stdout
            if want and not hit:
                problems.append(f"{label} 漏报 CA715：\n{p1.stdout}")
            if not want and hit:
                problems.append(f"{label} 误报 CA715：\n{p1.stdout}")
        finally:
            tmp.cleanup()
    return problems


def check_issue38_misc_shape_and_selfref() -> list[str]:
    """#38 元数据/自指：title 空、author 非字符串、owns 自指都要报 CA109（双后端）。"""
    problems = []
    body = "正文" * 120
    cases = {
        "title 空": (_card("a", "title: \"\"\n", body=body), "CA109", "title"),
        "author 非字符串": (_card("b", "author: 42\n", body=body), "CA109", "author"),
        "owns 自指": (_card("c", "owns:\n  - c\n", body=body), "CA109", "自己"),
    }
    for label, (card, rule, needle) in cases.items():
        tmp, world = _temp_world(f"world-misc-{label}-", {"card": card})
        try:
            p1 = subprocess.run([PY, str(TOOL), str(world), "--strict"],
                                cwd=ROOT, capture_output=True, text=True)
            lines = [ln for ln in p1.stdout.splitlines() if f"[{rule}]" in ln]
            if not lines or not any(needle in ln for ln in lines):
                problems.append(f"{label} 漏报 {rule} {needle}：\n{p1.stdout}")
        finally:
            tmp.cleanup()
    return problems


def check_ca505_ignores_event_layer() -> list[str]:
    """#38 泄压阀：`layer: fiscal` 的 event 卡不算「全库有财政」，非事件卡才算。"""
    problems = []
    body = "正文" * 120
    fleet = (_card("fleet", "layer: military\nload_bearing: true\n", body=body)
             .replace("type: location", "type: faction"))

    def run(entries: dict[str, str], label: str) -> str:
        tmp, world = _temp_world(f"world-ca505-{label}-", entries)
        try:
            p1 = subprocess.run([PY, str(TOOL), str(world)], cwd=ROOT,
                                capture_output=True, text=True)
            return p1.stdout
        finally:
            tmp.cleanup()

    fiscal_event = (_card("ev-fiscal", "layer: fiscal\nwhen: 元年\n"
                          "event_kind: modify\nwhen_sort: 1\nobject:\n  - fleet\n",
                          body=body).replace("type: location", "type: event"))
    if "[CA505]" not in run({"fleet": fleet, "ev-fiscal": fiscal_event}, "event"):
        problems.append("财政只挂在一张 event 卡上，CA505 仍应报（event 不算财政）")
    fiscal_card = _card("customs", "layer: fiscal\n", body=body)
    if "[CA505]" in run({"fleet": fleet, "customs": fiscal_card}, "card"):
        problems.append("财政挂在非事件卡上，CA505 不应报")
    return problems


def check_endpoint_events_are_unique() -> list[str]:
    """#38 端点类：CA714 拦住重复出生/重复死亡/先死后生/transform 越界。"""
    problems = []
    body = "正文" * 120

    def ev(eid: str, kind: str, when: float, legs: str = "") -> str:
        return (_card(eid, f"when: 元年\nevent_kind: {kind}\nwhen_sort: {when}\n"
                           + legs, body=body)
                .replace("type: location", "type: event"))

    def check(label: str, entries: dict[str, str], want: bool) -> None:
        tmp, world = _temp_world(f"world-endpoint-{label}-", entries)
        try:
            p1 = subprocess.run([PY, str(TOOL), str(world), "--strict"],
                                cwd=ROOT, capture_output=True, text=True)
            hit = "[CA714]" in p1.stdout
            if want and not hit:
                problems.append(f"{label} 漏报 CA714：\n{p1.stdout}")
            if not want and hit:
                problems.append(f"{label} 误报 CA714：\n{p1.stdout}")
        finally:
            tmp.cleanup()

    base = {"obj": _card("obj", "type: item\n", body=body)}
    check("重复出生",
          {**base, "b1": ev("b1", "birth", 1, "object:\n  - obj\n"),
           "b2": ev("b2", "create", 2, "object:\n  - obj\n")}, True)
    check("先死后生",
          {**base, "d1": ev("d1", "death", 1, "object:\n  - obj\n"),
           "b2": ev("b2", "birth", 2, "object:\n  - obj\n")}, True)
    check("transform result 早已出生",
          {**base, "r": _card("r", "type: item\n", body=body),
           "b1": ev("b1", "birth", 1, "object:\n  - r\n"),
           "t1": ev("t1", "transform", 3,
                    "object:\n  - obj\nresult:\n  - r\n")}, True)
    check("销毁后再 transform",
          {**base, "r": _card("r", "type: item\n", body=body),
           "d1": ev("d1", "destroy", 1, "object:\n  - obj\n"),
           "t1": ev("t1", "transform", 3,
                    "object:\n  - obj\nresult:\n  - r\n")}, True)
    check("正常端点链",
          {**base, "b1": ev("b1", "birth", 1, "object:\n  - obj\n"),
           "d1": ev("d1", "death", 2, "object:\n  - obj\n")}, False)
    return problems


def check_ledger_report_surfaces_certainty_and_ledger_rules() -> list[str]:
    """#48：`canonlint ledger` 报告必须带确定度三态、且「账本族告警」不止 CA703/704/705。"""
    problems = []
    body = "正文" * 120
    entries = {
        "gem": _card("gem", "type: item\n", body=body),
        "alice": _card("alice", "owns:\n  - gem\n", body=body),
        "bob": _card("bob", "owns:\n  - gem\n", body=body),
        "ev-1": _card("ev-1",
                      "type: event\nwhen_sort: 1\nevent_kind: transfer\n"
                      "by: [alice]\nto: [bob]\nobject: [gem]\n", body=body),
        "ev-frag": _card("ev-frag", "type: event\nwhen: 元年\n", body=body),
    }
    tmp, world = _temp_world("world-ledger-report-", entries)
    try:
        p1 = subprocess.run([PY, str(TOOL), "ledger", str(world)], cwd=ROOT,
                            capture_output=True, text=True)
        out = p1.stdout
        if p1.returncode != 0:
            problems.append(f"ledger 报告 exit {p1.returncode}\n{p1.stderr}")
        if "未定" not in out or "按 id 序" not in out:
            problems.append(f"互搏/未定序不该只印一个持有者：\n{out}")
        if "[CA707]" not in out:
            problems.append(f"「账本族告警」应有 CA707：\n{out}")
        if "[CA706]" not in out:
            problems.append(f"「账本族告警」应有 CA706：\n{out}")
        if "(账平)" in out:
            problems.append(f"有账本族告警却印了「账平」：\n{out}")
        p2 = subprocess.run([PY, str(TOOL), "export", str(world)], cwd=ROOT,
                            capture_output=True, text=True)
        try:
            cert = json.loads(p2.stdout)["ledger"]["states"]["gem"]["certainty"]
        except Exception as exc:
            problems.append(f"export 的 certainty 读不出来：{exc}\n{p2.stdout[:400]}")
            cert = None
        if cert != "ambiguous":
            problems.append(f"export certainty 应为 ambiguous，实际 {cert!r}")
        if cert == "ambiguous" and "未定" not in out:
            problems.append("ledger 报告与 export 的确定度口径不一致")
    finally:
        tmp.cleanup()
    return problems


def check_impact_sees_shadowed_cards() -> list[str]:
    """#49：被遮蔽卡（重复 id 的第二份）的出边也要进 CA504 的下游闭包。"""
    problems = []
    body = "正文" * 120
    entries = {
        "a-dup": _card("dup", "depends_on:\n  - id: subject\n    critical: false\n",
                       body=body),
        "b-dup": _card("dup",
                       "depends_on:\n  - id: subject\n    critical: false\n",
                       body="另一段正文" * 40),
        "subject": _card("subject", "status: draft\n", body=body),
    }
    tmp, world = _temp_world("world-shadow-impact-", entries)
    try:
        p1 = subprocess.run([PY, str(TOOL), str(world), "--impact", "subject"],
                            cwd=ROOT, capture_output=True, text=True)
        out = p1.stdout
        if "[CA504]" not in out or "dup" not in out:
            problems.append(f"CA504 下游闭包漏了被遮蔽卡：\n{out}")
    finally:
        tmp.cleanup()
    return problems


def check_layout_scanning_is_content_based() -> list[str]:
    """#50：扁平世界的散文不产生假错误；entries/ 子目录里的卡不被静默跳过。"""
    problems = []
    body = "正文" * 120
    # 现象 A：扁平世界 = 一张卡 + README + notes 散文
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "flat"
        world.mkdir()
        (world / "alpha.md").write_text(_card("alpha", body=body), encoding="utf-8")
        (world / "README.md").write_text("# 说明\n\n不是卡片。\n", encoding="utf-8")
        (world / "notes").mkdir()
        (world / "notes" / "changelog.md").write_text("变更记录。\n", encoding="utf-8")
        p1 = subprocess.run([PY, str(TOOL), str(world), "--strict"], cwd=ROOT,
                            capture_output=True, text=True)
        if p1.returncode != 0:
            problems.append(f"扁平世界散文被当坏条目：\n{p1.stdout}")
        if "CA100" in p1.stdout:
            problems.append(f"扁平世界散文报 CA100：\n{p1.stdout}")
        if "1 个条目" not in p1.stdout:
            problems.append(f"扁平世界条目数不对：\n{p1.stdout}")
    # 现象 B：entries/templates/ 里的卡必须进条目数并接受审计
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "sub"
        (world / "entries").mkdir(parents=True)
        (world / "entries" / "alpha.md").write_text(_card("alpha", body=body),
                                                    encoding="utf-8")
        tpl = world / "entries" / "templates"
        tpl.mkdir()
        (tpl / "ghost1.md").write_text(
            _card("ghost1", "canon_refs:\n  - missing\n", body=body),
            encoding="utf-8")
        p2 = subprocess.run([PY, str(TOOL), str(world), "--strict"], cwd=ROOT,
                            capture_output=True, text=True)
        if "2 个条目" not in p2.stdout:
            problems.append(f"entries/templates 里的卡被静默跳过（条目数）：\n{p2.stdout}")
        if "CA401" not in p2.stdout or "ghost1" not in p2.stdout:
            problems.append(f"entries/templates 里的卡没被审计：\n{p2.stdout}")
    return problems


def check_cli_write_runs_post_audit() -> list[str]:
    """#52：CLI 写卡与 HTTP 同纪律——写后审计红则不落盘。"""
    problems = []
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "w"
        world.mkdir()
        p1 = subprocess.run(
            [PY, str(TOOL), "event", "transfer", "--by", "jia", "--root", str(world)],
            cwd=ROOT, capture_output=True, text=True)
        if p1.returncode == 0:
            problems.append(f"缺腿事件仍被写入（rc=0）：{p1.stdout}")
        if "已回滚" not in p1.stderr or "CA702" not in p1.stderr:
            problems.append(f"缺腿事件没报「已回滚 + CA702」：\n{p1.stderr}")
        stray = world / "entries" / "events" / "transfer.md"
        if stray.exists():
            problems.append(f"写后审计红了却把卡留在磁盘：{stray}")
        if "已建卡" in p1.stdout:
            problems.append(f"回滚路径仍打印「已建卡」：{p1.stdout}")
        p2 = subprocess.run(
            [PY, str(TOOL), "new", "location", "灰港", "--id", "grey-harbor",
             "--root", str(world)],
            cwd=ROOT, capture_output=True, text=True)
        if p2.returncode != 0:
            problems.append(f"合法新卡被写后审计误拦：{p2.stdout}{p2.stderr}")
        card = world / "entries" / "locations" / "grey-harbor.md"
        if not card.exists():
            problems.append("合法新卡没落盘")
    return problems


def check_supersede_exemption_requires_archived() -> list[str]:
    """审计 §1.2：`superseded_by` 只有声明方 status=archived 时才豁免 CA201。"""
    body = "正文" * 120
    problems = []
    # canon 卡不能拿一行 superseded_by 关掉查重
    cards = {
        "one": _card("one", "", body=body),
        "two": _card("two", "superseded_by: one\n", body=body),
    }
    tmp, world = _temp_world("canonlint-ca201-exempt-", cards)
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"duplicate 把 traceback 写到了 stderr：\n{err}")
        if not any("[CA201]" in ln for ln in out.splitlines()):
            problems.append(f"canon 卡的 superseded_by 不得豁免 CA201：\n{out}")
    # 对照：archived 声明方 + 承接者仍豁免（降级承接对相似是要求的）
    cards = {
        "old": _card("old", "superseded_by: new\n", status="archived", body=body),
        "new": _card("new", "", body=body),
    }
    tmp, world = _temp_world("canonlint-ca201-archived-", cards)
    with tmp:
        _, out, err = _judge(world)
        if err:
            problems.append(f"archived 承接对把 traceback 写到了 stderr：\n{err}")
        if any("[CA201]" in ln for ln in out.splitlines()):
            problems.append(f"archived 承接对不该报 CA201：\n{out}")
    return problems


def check_event_fields_need_event_type() -> list[str]:
    """事件字段只许在 type: event 的卡上（协议 1.8，CA109）；否则不进流水。"""
    cards = {
        "a": _card("a", ""), "b": _card("b", ""), "relic": _card("relic", ""),
        "port": _card("port", (
            "when: 元年\nevent_kind: transfer\nwhen_sort: 1\n"
            "by:\n  - a\nobject:\n  - relic\nto:\n  - b\n"
        )),
    }
    tmp, world = _temp_world("canonlint-event-type-", cards)
    problems = []
    with tmp:
        code, out, err = _judge(world)
        if err:
            problems.append(f"非事件卡带事件字段把 traceback 写到了 stderr：\n{err}")
        if not any("[CA109]" in ln and "type: event" in ln for ln in out.splitlines()):
            problems.append(f"location 卡带事件字段应报 CA109（只许 type: event）：\n{out}")
        if "[CA702]" in out:
            problems.append(f"非事件卡不该被当成完整事件判腿（CA702）：\n{out}")
        lcode, lout, lerr = subprocess.run(
            [PY, str(TOOL), "ledger", str(world)], cwd=ROOT,
            capture_output=True, text=True).returncode, "", ""
        # 上面只取退出码会丢输出，重新跑一次拿文本
        p = subprocess.run([PY, str(TOOL), "ledger", str(world)], cwd=ROOT,
                           capture_output=True, text=True)
        if p.returncode != 0 or "0 笔完整事件" not in p.stdout:
            problems.append(f"非事件卡不该进流水，ledger 应报 0 笔完整事件：\n{p.stdout}{p.stderr}")
    return problems


def check_experimental_event_kind_via_cli() -> list[str]:
    """CLI 的 event 子命令接受 x- 实验 kind（CA102 info，以前被 choices 拦死）。"""
    cards = {"relic": _card("relic", "")}
    tmp, world = _temp_world("canonlint-xkind-cli-", cards)
    problems = []
    with tmp:
        p = subprocess.run(
            [PY, str(TOOL), "event", "x-wgp-trial", "实验账",
             "--root", str(world), "--id", "x-wgp-trial",
             "--when", "元年", "--when-sort", "1",
             "--object", "relic"],
            cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            problems.append(f"event x- 实验 kind 应是合法入口，实际 exit={p.returncode}：\n{p.stderr or p.stdout}")
        card = world / "entries" / "events" / "x-wgp-trial.md"
        if not card.exists():
            problems.append(f"实验事件卡没写出来（找 {card}）")
        _, out, err = _judge(world)
        if err:
            problems.append(f"实验事件卡把 traceback 写到了 stderr：\n{err}")
        if not any("[CA102] info" in ln and "实验值" in ln for ln in out.splitlines()):
            problems.append(f"x- 实验 kind 应记 CA102 info：\n{out}")
    return problems


def check_auto_id_when_slug_is_empty() -> list[str]:
    """id 省略 + 非 ASCII 标题：自动起名 <type>-<序号>，连续两次不撞车。"""
    sys.path.insert(0, str(ROOT))
    import canonlint
    import store
    tmp, world = _temp_world("canonlint-autoid-", {"seed": _card("seed", "")})
    problems = []
    with tmp:
        ids = []
        for _ in range(2):
            out: dict = {}
            rc = store.cmd_new(world, "location", "灰港新港", None,
                               author="t", fields={}, layer_choices=canonlint.LAYERS,
                               interactive=False, out=out)
            if rc != 0:
                problems.append(f"中文标题 + 无 id 应自动起名，实际 rc={rc}")
                break
            ids.append(out.get("id"))
            if not out.get("path") or not Path(out["path"]).exists():
                problems.append(f"自动起名没回传真实路径：{out}")
                break
        if ids != ["location-1", "location-2"]:
            problems.append(f"自动起名的序号不对：{ids}")
    return problems


def check_canonical_relations_satisfy_required_fields() -> list[str]:
    """#40 F4：规范形 relations 与旧字段二选一（协议 1.30）。"""
    problems = []

    def card(eid: str, extra: str = "") -> str:
        return _card(eid, extra)

    cases = [
        ("只写 relations 的规范形卡", {
            "a": _card("a", template_relations=False).replace(
                "ai_assisted: false",
                "relations:\n  - type: depends_on\n    target: b\n    kind: resource\n"
                "ai_assisted: false"),
            "b": card("b"),
        }, False),
        ("旧写法缺 canon_refs", {
            "a": card("a").replace("canon_refs: []\n", ""),
        }, True),
    ]
    for label, cards, want_error in cases:
        tmp, world = _temp_world("canonlint-f4-", cards)
        with tmp:
            _code, out, _err = _judge(world, "--strict")
            hit = "[CA101]" in out and "缺少必填字段 `canon_refs`" in out
            if want_error and not hit:
                problems.append(f"{label}：应报 CA101 canon_refs，实际：\n{out}")
            if not want_error and hit:
                problems.append(f"{label}：不应报 CA101 canon_refs，实际：\n{out}")
    return problems


def check_registry_loading_matrix() -> list[str]:
    """Registry 元数据与后端配置必须在任何规则执行前 fail-fast。"""
    problems = []
    try:
        from dataclasses import FrozenInstanceError
        from judges.model import Pack, Rule
        from judges.registry import Registry, RegistryError, select_packs
    except ImportError as e:
        return [f"Registry 类型应可导入：{e}"]

    def noop(meta, rel, add):
        return None

    def make_rule(rule_id="CA601", pack="p", scope="entry",
                  entry_domain="index_parseable", default_level="error",
                  levels=frozenset({"error"}), order=1):
        return Rule(id=rule_id, pack=pack, scope=scope, entry_domain=entry_domain,
                    check=noop, default_level=default_level,
                    levels=levels, order=order)

    def make_pack(name="p", fields=frozenset(), rules=None):
        if rules is None:
            rules = (make_rule(pack=name),)
        return Pack(name=name, version="1", engine="canonlint",
                    ca106_fields=fields, rules=rules)

    def expect_error(label, operation):
        try:
            operation()
        except RegistryError:
            return
        except Exception as e:
            problems.append(f"{label}：应抛 RegistryError，实际 {type(e).__name__}: {e}")
            return
        problems.append(f"{label}：应抛 RegistryError，实际被接受")

    duplicate_order = make_pack(rules=(
        make_rule(rule_id="CA601", order=1),
        make_rule(rule_id="CA602", order=1),
    ))
    expect_error("重复包内 order", lambda: Registry(
        {duplicate_order.name: duplicate_order}, (duplicate_order,)))

    first = make_pack(name="first", rules=(make_rule(pack="first"),))
    second = make_pack(name="second", rules=(make_rule(pack="second"),))
    expect_error("当前选择集重复规则 id", lambda: Registry(
        {first.name: first, second.name: second}, (first, second)))

    first_fields = make_pack(name="first-fields", fields=frozenset({"figures"}),
                             rules=(make_rule(pack="first-fields"),))
    second_fields = make_pack(name="second-fields", fields=frozenset({"figures"}),
                              rules=(make_rule(rule_id="CA602", pack="second-fields"),))
    expect_error("当前选择集重复 ca106_fields", lambda: Registry(
        {first_fields.name: first_fields, second_fields.name: second_fields},
        (first_fields, second_fields)))

    for label, rule in (
        ("非法 scope", make_rule(scope="both")),
        ("非法 entry_domain", make_rule(entry_domain="visible")),
        ("非法 level", make_rule(default_level="fatal", levels=frozenset({"fatal"}))),
        ("default_level 不在 levels", make_rule(
            default_level="warning", levels=frozenset({"error"}))),
    ):
        pack = make_pack(rules=(rule,))
        expect_error(label, lambda pack=pack: Registry({pack.name: pack}, (pack,)))

    expect_error("未知 Pack", lambda: select_packs("canonlint", ["missing"]))

    rule = make_rule()
    pack = make_pack()
    registry = Registry({pack.name: pack}, (pack,))
    for label, operation in (
        ("Rule 不可变", lambda: setattr(rule, "id", "CA999")),
        ("Pack 不可变", lambda: setattr(pack, "name", "changed")),
        ("Registry 不可变", lambda: setattr(registry, "selected", ())),
    ):
        try:
            operation()
        except FrozenInstanceError:
            pass
        except Exception as e:
            problems.append(f"{label}：应抛 FrozenInstanceError，实际 {type(e).__name__}")
        else:
            problems.append(f"{label}：字段仍可改写")
    try:
        registry.packs["other"] = pack
        problems.append("Registry.packs 的映射仍可改写")
    except TypeError:
        pass

    for rule_id in ("CA102", "CA108"):
        levels = frozenset({"error", "info"})
        dual = make_rule(rule_id=rule_id, levels=levels)
        pack = make_pack(rules=(dual,))
        actual = Registry({pack.name: pack}, (pack,)).selected[0].rules[0].levels
        if actual != levels:
            problems.append(f"{rule_id} 的 levels 应保留 {{error, info}}，实际 {actual}")

    with tempfile.TemporaryDirectory(prefix="canonlint-broken-econ-") as tmp:
        broken_tool = Path(tmp) / "canonlint.py"
        broken_tool.write_bytes(TOOL.read_bytes())
        (Path(tmp) / "econ.py").write_text(
            'raise ImportError("simulated: econ 不可用")\n', encoding="utf-8")
        p = subprocess.run(
            [PY, str(broken_tool), "tests/world-econ", "--pack", "econ"],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=os.pathsep.join((tmp, str(ROOT)))))
        expected = "error: 扩展包 econ 不可用（econ.py 应与 canonlint.py 同目录）\n"
        if p.returncode != 2 or p.stdout or p.stderr != expected:
            problems.append(f"econ 不可用应保留既有错误："
                            f"exit={p.returncode}, stdout={p.stdout!r}, stderr={p.stderr!r}")
    return problems


def check_registry_caches_econ_module_but_keeps_duplicate_selection() -> list[str]:
    """重复选择 econ 只导入一次模块，但选择列表保留两次。"""
    try:
        from unittest import mock
        import judges.registry as registry_module
        from judges.registry import select_packs
    except ImportError as e:
        return [f"Registry 加载器应可导入：{e}"]
    problems = []
    registry_module._MODULE_CACHE.clear()
    real_import = registry_module.importlib.import_module
    with mock.patch.object(registry_module.importlib, "import_module",
                           wraps=real_import) as importer:
        selected = select_packs("canonlint", ["econ", "econ"])
        select_packs("canonlint", ["econ"])
        if importer.call_count != 1:
            problems.append(f"重复选择/重复加载应只导入 econ 一次，实际 {importer.call_count} 次")
    if len(selected.selected) != 2 or selected.selected[0] is not selected.selected[1]:
        problems.append("重复显式 --pack econ 必须保留两个指向同一 Pack 的选择项")
    return problems


def check_registry_core_ca_pack() -> list[str]:
    """core-ca 的注册面：44 条规则逐条登记、遍历域与级别齐全；CA504 只进 report。"""
    problems = []
    try:
        import canonlint
        from judges.registry import RegistryError, select_packs
    except ImportError as e:
        return [f"Registry 依赖应可导入：{e}"]

    structure_rules = {
        "CA100", "CA101", "CA102", "CA103", "CA104", "CA105", "CA106", "CA107",
        "CA108", "CA109", "CA110", "CA111", "CA112", "CA114", "CA301", "CA302",
    }
    expected_rules = structure_rules | {
        "CA201", "CA401", "CA402", "CA403", "CA404", "CA405",
        "CA501", "CA502", "CA503", "CA504", "CA505",
        "CA701", "CA702", "CA703", "CA704", "CA705", "CA706",
        "CA707", "CA708", "CA709", "CA710", "CA711", "CA712", "CA713",
        "CA714", "CA715", "CA716", "CA717", "CA718", "CA719",
    }
    world_rules = {
        "CA114", "CA201", "CA403", "CA405", "CA502", "CA504", "CA505",
        "CA701", "CA703", "CA704", "CA705", "CA707", "CA708", "CA709",
        "CA710", "CA711", "CA712", "CA713", "CA714", "CA715", "CA716", "CA717",
        "CA718", "CA719",
        "CA718",
    }
    index_rules = {"CA501", "CA503"}
    try:
        core = select_packs("canonlint", ["core-ca"]).selected[0]
    except RegistryError as e:
        problems.append(f"core-ca 应能显式加载：{e}")
        return problems
    actual = {rule.id: rule for rule in core.rules}
    if set(actual) != expected_rules:
        problems.append(f"core-ca 逐规则注册不完整：缺 {sorted(expected_rules - set(actual))}，"
                        f"多 {sorted(set(actual) - expected_rules)}")
    for rule_id in sorted(expected_rules & set(actual)):
        rule = actual[rule_id]
        want_scope = "world" if rule_id in world_rules else "entry"
        if rule.scope != want_scope:
            problems.append(f"{rule_id} 的 scope 应为 {want_scope}，实际 {rule.scope}")
        want_domain = "index_parseable" if rule_id in index_rules else "all_entries"
        if want_scope == "entry" and rule.entry_domain != want_domain:
            problems.append(f"{rule_id} 必须遍历 {want_domain}，实际 {rule.entry_domain}")
    for rule_id in ("CA102", "CA108"):
        if rule_id in actual and actual[rule_id].levels != frozenset({"error", "info"}):
            problems.append(f"{rule_id} 必须登记 error/info 两种实际级别")
    for rule_id in ("CA704", "CA709"):
        if rule_id in actual and actual[rule_id].levels != frozenset({"error", "warning"}):
            problems.append(f"{rule_id} 必须登记 error/warning 两种实际级别")

    # CA504 是 report 级：进入 reports，绝不混进 Finding（快照另钉 CLI 形状）
    packs, extra_known = canonlint._load_packs([])
    assert packs is not None
    _e, _i, findings, reports = canonlint.run(
        HERE / "world-arrakis", 0.85, ["sandworm-cycle"],
        extra_known=extra_known, packs=packs)
    if any(f.rule == "CA504" for f in findings):
        problems.append("CA504 只能进入 report，不得混入 Finding")
    if len(reports) != 1 or not reports[0]["downstream"]:
        problems.append(f"CA504 应给出 sandworm-cycle 的下游闭包：{reports!r}")

    # 重复显式 --pack econ：同一 Pack 执行两次，CA601/602 原样翻倍
    def econ_findings(names):
        packs, extra_known = canonlint._load_packs(names)
        assert packs is not None, "econ Pack 应可用"
        return [(f.rule, f.level, f.entry, f.message)
                for f in canonlint.run(HERE / "world-econ", 0.85, [],
                                       extra_known=extra_known, packs=packs)[2]
                if f.rule in ("CA601", "CA602")]

    single = econ_findings(["econ"])
    doubled = econ_findings(["econ", "econ"])
    if not single:
        problems.append("world-econ 在 --pack econ 下应发出 CA601/602")
    elif doubled != single * 2:
        problems.append("重复 --pack econ 的 CA601/602 应原样执行两次")
    return problems


def check_registry_econ_skips_shadowed_entries() -> list[str]:
    """econ 只查 index_parseable：首条入索引，重复 id 的后者不得发 CA601。"""
    first_figures = (
        "figures:\n"
        "  population: {value: 1000, unit: 人}\n"
        "  military_size: {value: 100, unit: 人}\n"
    )
    tmp, world = _temp_world("canonlint-registry-shadow-", {
        "first": _card("dup-id", first_figures),
        "second": _card("dup-id", "figures: 7\n"),
    })
    problems = []
    with tmp:
        p = subprocess.run([PY, str(TOOL), str(world), "--pack", "econ"], cwd=ROOT,
                           capture_output=True, text=True)
        if "[CA601]" in p.stdout or "entries/second.md: figures" in p.stdout:
            problems.append(f"被遮蔽条目不应发 CA601/602：\n{p.stdout}")
        if "[CA602]" not in p.stdout or "entries/first.md" not in p.stdout:
            problems.append(f"入索引条目仍应执行 econ：\n{p.stdout}")
    return problems


def check_registry_schedule_rejects_unscheduled_rules() -> list[str]:
    """登记进 pack 的规则必须真的被日程调度（#13）。

    这一条防的是「规则注册了、元数据齐全，但执行器忘了接」——死规则看起来存在，
    实际永远不跑。verify_schedule 在每次 registry 执行末尾对账；这里直接喂一个
    「已登记但未调度」的假 pack，确认它真的会红。
    """
    from judges.model import Pack, Rule
    from judges.registry import RegistryError, verify_schedule

    def noop(*args, **kwargs):
        return None

    rule = Rule(id="CA999", pack="probe", scope="entry", entry_domain="all_entries",
                check=noop, default_level="error", levels=frozenset({"error"}), order=999)
    pack = Pack(name="probe", version="0.0", engine="canonlint",
                ca106_fields=frozenset(), rules=(rule,))
    try:
        verify_schedule(pack, set(), site="probe")
    except RegistryError as exc:
        if "CA999" not in str(exc) or "从未被调度" not in str(exc):
            return [f"对账报错没有点名 CA999 / 原因不对：{exc}"]
    else:
        return ["登记了却从未被调度的规则没有触发 RegistryError"]
    verify_schedule(pack, {"CA999"}, site="probe")  # 对账通过时不抛
    return []


def main() -> int:
    update = "--update" in sys.argv[1:]
    failures: list[str] = []
    checked = 0
    crash_output = ""

    for name, args in CASES:
        code, out, err = run_case(args)
        if update:
            dump_snapshot(name, code, out)
            print(f"WROTE {name} (exit={code})")
        if err:
            failures.append(f"{name}: stderr 非空（疑似 traceback 逃逸）\n{err}")
            continue
        want = load_snapshot(name)
        if want is None:
            failures.append(f"{name}: 缺少快照（先跑一次 --update）")
            continue
        if (code, out) == want:
            checked += 1
            print(f"PASS {name} ({last_line(want[1])})")
        else:
            failures.append(f"{name}: 输出或退出码与快照不一致"
                            f"（期望 exit={want[0]}，实际 exit={code}）\n"
                            + diff(want[1], out))
        if name == "world-crash":
            crash_output = out

    # 意图断言：快照证明「没变」，这里证明「守卫真的在生效」
    for what, rule, entry in CRASH_INTENT:
        hit = any(ln.startswith(f"[{rule}]") and entry in ln
                  for ln in crash_output.splitlines())
        if hit:
            checked += 1
            print(f"PASS 崩溃守卫：{what}")
        else:
            failures.append(f"崩溃守卫失效：{what}"
                            f"（world-crash 输出里没有 [{rule}] {entry}）")

    extras = [
        ("不可提交的形态（悬空软链 / 名为 *.md 的目录）", check_undeclarable_shapes),
        ("--json 契约（键名与类型）", check_json_schema),
        ("CA504 影响报告是只读的（不改变退出码）", check_impact_is_advisory),
        ("--help 能看到 init/new/link", check_help_discoverable),
        ("缺 pyyaml 时干净退出（提示 + 退出码 2）", check_missing_dependency_is_clean),
        ("降级承接对不算重复（CA201 豁免）", check_supersede_pairs_are_not_duplicates),
        ("登记了却未调度的规则会被日程对账抓住（#13）",
         check_registry_schedule_rejects_unscheduled_rules),
    ("被遮蔽条目的引用照样检查", check_shadowed_entries_still_get_their_refs_checked),
    ("非法 id 语法报 CA105（重复 id 已拆成 CA114）", check_bad_id_syntax_reports_ca105),
    ("--strict 只改退出码，不改判定", check_strict_only_changes_the_exit_code),
    ("--dup-threshold 的边界与效果", check_dup_threshold_is_a_bounded_knob),
    ("--impact 的报告说得实话（悬空/环/两跳/退出码）", check_impact_reports_are_well_formed),
    ("指错目录给用法错误，而不是硬审", check_non_world_directory_is_a_usage_error),
    ("有 entries/ 时根目录的卡片不蒸发", check_root_cards_survive_an_entries_dir),
    ("每一种关系的悬空引用都报 CA401", check_every_relation_reference_is_checked),
    ("拼错一个字符的关系名按规范名判定（自定义名仍 fail-open）",
     check_near_miss_names_are_judged_under_the_canonical_name),
    ("econ 的 figures 形状（非映射 / unit 非字符串）都报 CA601", check_econ_figures_are_shape_checked),
        ("--dup-threshold 越界是用法错误（不退化成静默关规则）", check_dup_threshold_range_is_usage_error),
        ("--impact 从不把主体列进自己的下游", check_impact_never_lists_the_subject),
        ("提示性规则不阻断 draft（CA301 只对定档条目报）", check_advisory_rules_do_not_gate_drafts),
        ("互相交换不是永动机（exchanges_with 不进 CA502，互相供养照报）", check_mutual_exchange_is_not_a_perpetual_motion),
        ("名分依据是关系名不是物资类别（拆分 depends_on 后判定不变）", check_legitimacy_is_its_own_relation_not_a_material_kind),
        ("名分来源只查存在性（悬空报 CA401，归档不报 CA402/CA405）", check_legitimacy_edge_checks_existence_only),
        ("x- 实验 kind 继续豁免 CA501/CA502（门禁改看关系名也不许收走）", check_experimental_kinds_are_still_exempt),
        ("史料事件卡（无 when/event_kind）一条 CA7xx 都不响（D9）", check_historical_event_cards_stay_silent),
        ("缺 when_sort 时时序/账平规则 fail-open", check_ledger_fail_open_without_when_sort),
        ("when_sort 相等：CA701 合法、CA705 不算死后", check_equal_sort_boundaries),
        ("腿形状写坏报 CA109、不叠 CA702", check_leg_shape_is_ca109_not_double_ca702),
        ("when_sort 写 .nan 报 CA109 并 fail-open", check_when_sort_nan_is_a_shape_error),
        ("多值受方归属未定序：受方断言不吃 CA704、外人照报", check_multi_recipient_transfer_fails_open_on_ca704),
        ("同一客体多卡 owns 断言互搏报 CA707（warning）", check_conflicting_owns_assertions_fire_ca707),
        ("客体事件落在存在窗口外报 CA708（端点豁免、fail-open）", check_object_existence_window_fires_ca708),
        ("move 的 from 腿悬空引用报 CA401", check_move_from_leg_is_checked),
        ("custody_of 断言对账 CA709 + 保管互搏 CA710", check_custody_assertions_reconcile_with_ledger),
        ("轨迹断裂报 CA711（未定/多值放行、与 CA708 不双报）", check_trajectory_break_fires_ca711),
        ("转让起点断裂报 CA713（from 对不上上一笔落点）", check_transfer_from_must_match_previous_to),
        ("join/leave 进词表、腿表参与 CA702", check_join_leave_are_vocabulary_kinds),
        ("member_of 断言与流水对账（CA712）+ 悬空/坏形状", check_member_of_reconciles_with_ledger),
        ("transform 窗口交接：旧关新开、自身豁免、不自动继承", check_transform_closes_and_opens_windows),
        ("modify 同 id 变化：不动窗口/状态，复用通用规则与 CLI",
         check_modify_preserves_identity_and_state),
        ("world-ledger-bad 把六条流水规则每条至少踩一次", check_ledger_bad_world_fires_every_rule),
        ("带 from 的 transfer/grant 合法且原样导出（契约 0.8）", check_from_leg_is_legal),
        ("派生状态导出 certainty 三态（known/unknown/ambiguous）", check_certainty_three_states_in_export),
        ("custody_of 断言无流水时兜底保管人（有流水流水赢）", check_custody_assertion_is_fallback_without_flow),
        ("member_of 断言无流水时兜底在册（有流水流水赢）", check_member_of_assertion_is_fallback_without_flow),
        ("ledger 子命令是只读报告（不改退出码、不写盘）", check_ledger_command_is_readonly_report),
        ("同刻事件不按 id 定序（CA704/709/711/712 改名不翻转）", check_same_instant_id_order_is_not_history),
        ("同刻未定序与断言无关（无 owns/custody_of 也报 CA704/CA709）",
         check_ambiguous_final_without_assertion_is_reported),
        ("同刻未定序不再吞掉断言对账（不在全候选交集里照报 CA704 error）",
         check_ambiguous_final_still_reconciles_assertions),
        ("death 事件自身也查 CA705（死人不当施动者）", check_death_events_are_checked_as_actors),
        ("事件腿都在存在窗口内：CA705 收 destroy、CA708 查 by/from/to（审计 §1.1）",
         check_event_legs_are_window_checked),
        ("issue #38：交出者须是持有人、draft 断言不当正史来源",
         check_issue38_ownership_source_and_status),
        ("issue #38：CA503 的物质锚点须有可比较 layer",
         check_issue38_material_anchor_requires_layer),
        ("issue #38：端点事件的 by 施动者也须已出生",
         check_issue38_endpoint_actors_exist),
        ("issue #38：member_of 的主体/目标类型门禁",
         check_issue38_membership_types),
        ("issue #41：layer 写坏只报 CA102，不 traceback",
         check_layer_shape_does_not_crash),
        ("issue #43：显式 null 关系字段报 CA109，不被当成缺省",
         check_null_relation_fields_are_shape_errors),
        ("issue #45：CA111 认契约登记的历史拼法（depends-on）",
         check_ca111_recognizes_contract_alias_spellings),
        ("issue #46：CA103 拒收 datetime（只收日期）",
         check_ca103_rejects_datetime),
        ("issue #42：CA703 的 create/birth 豁免只限第一笔转手",
         check_ca703_creation_exemption_is_first_transfer_only),
        ("issue #40 F1：规范形注解键按关系名校验（与旧写法同判）",
         check_canonical_relations_validate_attrs_per_relation),
        ("issue #40 F2：非事件卡上的 when / when_sort 报 CA109",
         check_event_fields_only_on_event_cards),
        ("issue #40 F3：坏 YAML 不制造假悬空引用",
         check_broken_yaml_does_not_fake_dangling_refs),
        ("issue #48：ledger 报告带确定度与账本族全族告警",
         check_ledger_report_surfaces_certainty_and_ledger_rules),
        ("issue #49：CA504 下游闭包看见被遮蔽卡的出边",
         check_impact_sees_shadowed_cards),
        ("issue #50：扁平散文不误报、entries 子目录卡不被跳过",
         check_layout_scanning_is_content_based),
        ("issue #52：CLI 写卡写后自检，红则回滚", check_cli_write_runs_post_audit),
        ("issue #38 端点类：CA714 重复/顺序端点事件", check_endpoint_events_are_unique),
        ("issue #38 元数据/自指：title/author 类型与关系自指", check_issue38_misc_shape_and_selfref),
        ("issue #38 状态门禁：canon 卡引用非 canon 目标报 CA715", check_canon_card_referencing_non_canon),
        ("issue #38 x- 实验类别成环也要报 CA502", check_x_kind_cycles_are_reported),
        ("issue #38 when 与 when_sort 反向报 CA716", check_when_and_when_sort_must_agree),
        ("issue #38 短正文精确重复也报 CA201", check_ca201_catches_short_exact_duplicates),
        ("issue #38 事件腿类型与事件语义对不上报 CA717", check_event_leg_types_are_checked),
        ("issue #38 承接链要落在定档且同类的条目上（CA718）", check_supersede_chain_is_checked),
        ("issue #38 成员链 join/leave 必须配对（CA719）", check_member_chain_is_paired),
        ("issue #40 F4：规范形 relations 与旧字段二选一（协议 1.30）", check_canonical_relations_satisfy_required_fields),
        ("issue #38 泄压阀：CA505 不认 event 卡的 layer", check_ca505_ignores_event_layer),
        ("CA201 豁免只认 archived 声明方（审计 §1.2）", check_supersede_exemption_requires_archived),
        ("事件字段只许在 type: event（CA109 + 不进流水）", check_event_fields_need_event_type),
        ("CLI 的 event 子命令接受 x- 实验 kind", check_experimental_event_kind_via_cli),
        ("id 省略 + 中文标题自动起名 <type>-<序号>", check_auto_id_when_slug_is_empty),
        ("Registry 加载失败矩阵与不可变元数据", check_registry_loading_matrix),
        ("econ 模块只加载一次且重复选择保留两次",
         check_registry_caches_econ_module_but_keeps_duplicate_selection),
        ("core-ca 注册面：44 条规则登记齐全、CA504 只进 report、econ 重复执行两次",
         check_registry_core_ca_pack),
        ("econ 只遍历 index_parseable（不审被遮蔽条目）",
         check_registry_econ_skips_shadowed_entries),
    ]
    for label, check in extras:
        problems = check()
        if problems:
            failures.extend(problems)
        else:
            checked += 1
            print(f"PASS {label}")

    total = len(CASES) + len(CRASH_INTENT) + len(extras)
    print(f"\n{total} 项检查 | "
          f"{'全部通过' if not failures else f'{len(failures)} 个失败'}")
    for f in failures:
        print(f"\nFAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
