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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAPS = HERE / "snapshots"
TOOL = ROOT / "canonlint.py"
PY = sys.executable

# (快照名, 命令行参数)。退出码与标准输出一起被快照钉死。
CASES: list[tuple[str, list[str]]] = [
    ("world-clean", ["tests/world-clean"]),
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
]

# 崩溃守卫的意图断言：(说明, 规则编号, 必须出现在同一条发现里的条目路径)
# 这四条在 PR#0.1 之前都会以 traceback 收场（整个审计崩掉，一条发现都不出）。
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
    for f in data["findings"]:
        if set(f) != {"rule", "level", "entry", "message"}:
            return [f"--json 发现项的键应为 rule/level/entry/message，实际 {sorted(f)}"]
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
