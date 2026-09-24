#!/usr/bin/env python3
"""classlint fixture 测试：tests/<世界>/ 每个目录是一个世界仓库，EXPECTED 钉死期望判定。

用法: python3 tests/run_tests.py   （在 classlint/ 目录内或任意位置均可）
退出码: 0=全部符合期望 1=有偏差
"""
import sys
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
    "clean": [],
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
    extra = set(EXPECTED) - set(worlds)
    for name in sorted(extra):
        print(f"FAIL {name}: EXPECTED 登记了期望但夹具目录不存在")
        failures += 1
    print(f"\n{len(worlds)} 个夹具世界 | {'全部通过' if not failures else f'{failures} 个失败'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
