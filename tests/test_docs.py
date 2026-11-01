#!/usr/bin/env python3
"""文档一致性检查：文档里的数字、编号、路径、命令和检查名都必须与代码一致。

为什么要有这一套：文档是给「第二个人和他的 AI」的上下文。文档撒谎，AI 必然跟着错，
而且错得很快——它会把不存在的规则、不存在的文件、不存在的命令当成事实照做。
这里检查的是**事实**，不是文风：数字对不对、编号在不在、文件在不在、命令跑不跑得起来。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import canonlint  # noqa: E402
import store  # noqa: E402

DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    "docs/协作流程.md",
    "docs/README.md",
    "PROTOCOL.md",
    "PROTOCOL-ECON.md",
    "项目文书.md",
    "classlint/README.md",
    "classlint/PROTOCOL.md",
    "classlint/ROADMAP.md",
    "classlint/开发计划.md",
    "classlint/项目文书.md",
    "classlint/tests/world-arrakis/README.md",
    "classlint/tests/world-westeros/README.md",
)

CORE_SRC = (ROOT / "canonlint.py", ROOT / "serve.py",
            *sorted((ROOT / "store").glob("*.py")))
ECON_SRC = (ROOT / "econ.py",)
CL_SRC = (ROOT / "classlint/classlint.py",)
WORKFLOW = ROOT / ".github/workflows/canonlint.yml"

DOCUMENT_CATEGORIES = {"权威契约", "使用参考", "设计路线", "评审过程", "案例与对外", "授权与治理"}
DOCUMENT_STATUSES = {"现行", "草案", "历史", "模板", "案例", "授权"}

CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
            "七": 7, "八": 8, "九": 9, "十": 10}

# 仓库主的本地代理规矩：明确不入库（.gitignore），也不算项目文档。
# 必须在这里排除，否则「本地工作区（文件在）」与「干净克隆（文件不在）」
# 不可能同时判绿——总索引也会被迫登记一个版本库里不存在的目标。
LOCAL_ONLY_DOCS = {"AGENTS.md"}


def project_document_paths() -> set[str]:
    paths = set(ROOT.glob("*.md"))
    paths.add(ROOT / "LICENSE")
    for pattern in ("docs/**/*.md", "store/*.md", "classlint/*.md",
                    "classlint/tests/*/README.md"):
        paths.update(ROOT.glob(pattern))
    discovered = {p.relative_to(ROOT).as_posix() for p in paths if p.is_file()}
    return discovered - LOCAL_ONLY_DOCS


DOCUMENT_INDEX_HEADER = "| 文档 | 分类 | 状态 | 摘要 | 权威与更新触发 |"
DOCUMENT_INDEX_SEPARATOR = "|---|---|---|---|---|"


def parse_document_index_text(text: str, index: Path) -> list[tuple[str, str, str]]:
    lines = text.splitlines()
    assert lines.count(DOCUMENT_INDEX_HEADER) == 1, \
        f"{index} 必须有且只有一行全量文档表头"
    start = lines.index(DOCUMENT_INDEX_HEADER)
    assert start + 1 < len(lines) and lines[start + 1] == DOCUMENT_INDEX_SEPARATOR, \
        f"{index}:{start + 2} 缺少五列分隔行"
    pattern = re.compile(
        r"\| (\[[^]]+\]\([^)]+\)) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|")
    rows: list[tuple[str, str, str]] = []
    for offset in range(start + 2, len(lines)):
        line = lines[offset]
        if not line.strip() or not line.startswith("|"):
            break
        match = pattern.fullmatch(line)
        assert match, f"{index}:{offset + 1} 不是合法的五列文档登记行"
        link = re.fullmatch(r"\[([^]]+)\]\(([^)]+)\)", match.group(1))
        assert link, f"{index}:{offset + 1} 第一列不是 Markdown 链接"
        target = (index.parent / link.group(2)).resolve()
        try:
            rel = target.relative_to(ROOT).as_posix()
        except ValueError:
            raise AssertionError(f"索引指向仓库外：{link.group(2)}")
        rows.append((rel, match.group(2).strip(), match.group(3).strip()))
    assert rows, f"{index} 的全量文档表没有登记行"
    return rows


def document_index_rows() -> list[tuple[str, str, str]]:
    index = ROOT / "docs/README.md"
    return parse_document_index_text(index.read_text(encoding="utf-8"), index)


def check_document_index_covers_all():
    rows = document_index_rows()
    assert rows, "docs/README.md 没有可解析的五列文档登记行"
    paths = [path for path, _category, _status in rows]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    assert not duplicates, f"文档在总索引里重复登记：{duplicates}"
    for path, category, status in rows:
        assert (ROOT / path).is_file(), f"索引目标不存在：{path}"
        assert category in DOCUMENT_CATEGORIES, f"{path} 的分类非法：{category}"
        assert status in DOCUMENT_STATUSES, f"{path} 的状态非法：{status}"
    discovered = project_document_paths()
    indexed = set(paths)
    missing = sorted(discovered - indexed)
    extra = sorted(indexed - discovered)
    assert not missing, f"项目文档未登记到 docs/README.md：{missing}"
    assert not extra, f"总索引登记了发现范围之外的文档：{extra}"

    header = "| 文档 | 分类 | 状态 | 摘要 | 权威与更新触发 |"
    separator = "|---|---|---|---|---|"
    row = "| [README.md](../README.md) | 使用参考 | 现行 | 项目入口 | 实测变化时同步 |"
    valid = f"{header}\n{separator}\n{row}\n"
    assert len(parse_document_index_text(valid, ROOT / "docs/README.md")) == 1
    malformed = {
        "缺少表头": f"{row}\n",
        "六列表头": ("| 文档 | 分类 | 状态 | 摘要 | 权威 | 额外 |\n"
                   "|---|---|---|---|---|---|\n" + row + "\n"),
        "六列重复行": valid + row[:-2] + " | 额外 |\n",
    }
    for label, text in malformed.items():
        try:
            parse_document_index_text(text, ROOT / "docs/README.md")
        except AssertionError:
            pass
        else:
            raise AssertionError(f"坏表格被静默接受：{label}")


def doc(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def rule_ids_in_code(prefix: str, paths) -> set[str]:
    """代码里真的会发射的规则编号（只看字符串字面量）。"""
    found: set[str] = set()
    for path in paths:
        for num in re.findall(rf'"{prefix}(\d{{3}})"', path.read_text(encoding="utf-8")):
            found.add(f"{prefix}{num}")
    return found


def rule_table_ids(text: str, prefix: str) -> list[str]:
    """Markdown 规则表第一列里的编号（`| CA100 | error | …`）。"""
    return re.findall(rf"^\| ({prefix}\d{{3}}) \|", text, re.M)


def list_len(path: Path, name: str, func: str | None = None) -> int:
    """数源码里某个列表字面量有几项——不执行它，只读它的形状。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node: ast.AST = tree
    if func is not None:
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == func)
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Assign, ast.AnnAssign)):
            targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return len(sub.value.elts)  # type: ignore[attr-defined]
    where = f"{path.name}:{func}" if func else path.name
    raise AssertionError(f"{where} 里找不到列表 {name}")


def classlint_fixtures() -> list[str]:
    return sorted(p.name for p in (ROOT / "classlint/tests").iterdir()
                  if p.is_dir() and (p / "codex").is_dir())


def check_rule_ids_match_code():
    """规则编号是文档与代码之间最容易漂移的东西：两边必须是同一个集合。"""
    for name, prefix, src in (("PROTOCOL.md", "CA", CORE_SRC),
                              ("PROTOCOL-ECON.md", "CA", ECON_SRC),
                              ("classlint/PROTOCOL.md", "CL", CL_SRC),
                              ("classlint/PROTOCOL.md", "PE", CL_SRC)):
        rows = rule_table_ids(doc(name), prefix)
        code = rule_ids_in_code(prefix, src)
        dupes = sorted({r for r in rows if rows.count(r) > 1})
        assert not dupes, f"{name} 的 {prefix} 规则表有重复行：{dupes}"
        missing = sorted(code - set(rows))
        extra = sorted(set(rows) - code)
        assert not missing, f"{name} 的 {prefix} 规则表少了代码会发射的编号：{missing}"
        assert not extra, f"{name} 的 {prefix} 规则表有代码里不存在的编号：{extra}"

    summary = doc("docs/判定规则总表.md")
    for prefix, sources in (("CA", (*CORE_SRC, *ECON_SRC)), ("CL", CL_SRC), ("PE", CL_SRC)):
        rows = rule_table_ids(summary, prefix)
        code = rule_ids_in_code(prefix, sources)
        assert len(rows) == len(set(rows)), f"判定规则总表的 {prefix} 编号有重复"
        missing = sorted(code - set(rows))
        extra = sorted(set(rows) - code)
        assert not missing, f"判定规则总表少了代码会发射的 {prefix} 编号：{missing}"
        assert not extra, f"判定规则总表有代码里不存在的 {prefix} 编号：{extra}"


def check_rule_counts_match_code():
    core = len(rule_ids_in_code("CA", CORE_SRC))
    cl = len(rule_ids_in_code("CL", CL_SRC))
    pe = len(rule_ids_in_code("PE", CL_SRC))

    readme = doc("README.md")
    for pattern in (r"(\d+) 条 CA 规则", r"§6\.3，(\d+) 条"):
        got = {int(x) for x in re.findall(pattern, readme)}
        assert got == {core}, f"README.md 的「{pattern}」写成 {sorted(got)}，代码里是 {core}"
    assert {int(x) for x in re.findall(r"(\d+) 条 CL", readme)} == {cl}, "README.md 的 CL 条数不对"
    assert {int(x) for x in re.findall(r"(\d+) 条 PE", readme)} == {pe}, "README.md 的 PE 条数不对"

    contributing = doc("CONTRIBUTING.md")
    got = {int(x) for x in re.findall(r"那是 (\d+) 条规则的清单", contributing)}
    assert got == {core}, f"CONTRIBUTING.md 的规则条数写成 {sorted(got)}，代码里是 {core}"


def check_layer_dictionary_matches_code():
    layers = canonlint.LAYERS
    order = " → ".join(layers)
    for name in ("PROTOCOL.md", "项目文书.md"):
        assert order in doc(name), f"{name} 里的层级顺序与 canonlint.LAYERS 不一致"

    m = re.search(r"层级字典（协议常量，(.)层", doc("PROTOCOL.md"))
    assert m and CN_DIGIT.get(m.group(1)) == len(layers), \
        f"PROTOCOL.md §5.2 的层数不是 {len(layers)}"
    m = re.search(r"geo=0 … ideology=(\d+)", doc("PROTOCOL.md"))
    assert m and int(m.group(1)) == len(layers) - 1, \
        f"PROTOCOL.md 的 ideology 序号不是 {len(layers) - 1}"
    m = re.search(r"(.)层字典（协议常量）", doc("项目文书.md"))
    assert m and CN_DIGIT.get(m.group(1)) == len(layers), "项目文书.md 的层数不对"


def test_suite_files() -> list[str]:
    """tests/ 里真实存在的套件：run_tests.py + 每个 test_*.py。"""
    return ["run_tests.py"] + sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))


def check_test_counts_match_docs():
    run_file = ROOT / "tests/run_tests.py"
    cases = list_len(run_file, "CASES")
    # 套数不写死：磁盘上有什么就以什么为准——新加一套，README / CONTRIBUTING / CI / 这里
    # 四处都必须跟着变，否则这一项红。
    order = ["run_tests.py", "test_schema.py", "test_store.py", "test_serve.py", "test_docs.py"]
    on_disk = test_suite_files()
    assert sorted(order) == sorted(on_disk), (
        f"tests/ 里的套件与这份清单不一致：磁盘 {on_disk}，清单 {order}"
        "（新加一套要同时更新 README.md / CONTRIBUTING.md / CI 工作流和这里）")
    totals = {
        "run_tests.py": (cases + list_len(run_file, "CRASH_INTENT")
                         + list_len(run_file, "extras", func="main")),
        "test_schema.py": list_len(ROOT / "tests/test_schema.py", "checks", func="main"),
        "test_store.py": list_len(ROOT / "tests/test_store.py", "CHECKS"),
        "test_serve.py": list_len(ROOT / "tests/test_serve.py", "CHECKS"),
        "test_docs.py": list_len(ROOT / "tests/test_docs.py", "CHECKS"),
    }
    ran = ci_scripts("canonlint")
    for name in order:  # 每一套都得在 CI 里真的跑，不能只在文档里写着
        assert f"tests/{name}" in ran, \
            f"CI 的 canonlint job 没有跑 tests/{name}（实际跑的是 {ran}）"
    expected = tuple(totals[key] for key in order)
    fixtures = len(classlint_fixtures())

    readme = doc("README.md")
    m = re.search(r"(.)套（" + r" \+ ".join([r"(\d+)"] * len(order)) + r" 项检查）", readme)
    assert m, "README.md 里找不到 tests/ 各套检查的项数"
    assert CN_DIGIT.get(m.group(1)) == len(order), \
        f"README.md 写成「{m.group(1)}套」，而 tests/ 里是 {len(order)} 套"
    assert tuple(int(x) for x in m.groups()[1:]) == expected, \
        f"README.md 的项数 {m.groups()[1:]} 与实测 {expected} 不符"
    assert {int(x) for x in re.findall(r"（(\d+) 个夹具世界）", readme)} == {fixtures}, \
        f"README.md 的 classlint 夹具数不是 {fixtures}"

    contributing = doc("CONTRIBUTING.md")
    m = re.search(r"# (\d+) 个世界夹具 \+ (\d+) 项检查", contributing)
    assert m, "CONTRIBUTING.md 里找不到夹具与检查项数"
    assert (int(m.group(1)), int(m.group(2))) == (cases, totals["run_tests.py"]), \
        f"CONTRIBUTING.md 写成 {(m.groups())}，实测是 {(cases, totals['run_tests.py'])}"
    assert {int(x) for x in re.findall(r"（(\d+) 个夹具）", contributing)} == {fixtures}, \
        f"CONTRIBUTING.md 的 classlint 夹具数不是 {fixtures}"
    assert {int(x) for x in re.findall(r"（(\d+) 个夹具", doc("classlint/README.md"))} == {fixtures}, \
        f"classlint/README.md 的夹具数不是 {fixtures}"


def check_pe_claims_match_code():
    pe = rule_ids_in_code("PE", CL_SRC)
    implemented = {f"PE{i:03d}" for i in range(1, 6)} | {"PE009"}
    assert pe == implemented, f"classlint 已实现的 PE 规则不是 PE001–PE005 + PE009：{sorted(pe)}"
    for name in ("classlint/PROTOCOL.md", "classlint/README.md", "README.md", "CONTRIBUTING.md"):
        assert "PE001–PE005" in doc(name), f"{name} 没写明已实现的是 PE001–PE005"
    assert "PE006–PE008" in doc("classlint/PROTOCOL.md"), \
        "classlint/PROTOCOL.md 应写明 PE006–PE008 还没实现（属流量层）"
    assert "PE009" in doc("classlint/PROTOCOL.md"), \
        "classlint/PROTOCOL.md 应写明 PE009（债务必须收得回来）已实现"


def check_doc_paths_exist():
    """文档提到一个文件，那个文件就得真的在——否则 AI 会照着去读一个不存在的东西。

    豁免表里的每一项都必须写明「为什么它不在仓库里」，而由 init 生成的那两个还要
    反过来验证代码里真的会生成它们（豁免不是随手放过）。
    """
    skip = {
        "CONSTITUTION.md": "由 canonlint init 在世界仓库里生成，本仓库不该有",
        "classlint.yaml": "由 classlint init 在世界仓库里生成，本仓库不该有",
        "codex/entities.yaml": "世界仓库的实体别名表（classlint mentions 已实现），本仓库不该有",
        "AGENTS.md": "仓库主本地代理规矩，明确不入库（.gitignore）；仅在本地存在，索引与发现范围都排除",
        "01_Requirements.md": "classlint 早期规划里的文档名，从未进仓库",
        "02_Architecture.md": "classlint 早期规划里的文档名，从未进仓库",
        "03_Plan.md": "classlint 早期规划里的文档名，从未进仓库",
    }
    # 世界仓库内部的相对路径（`codex/debtor.md` 这类）永远不以本仓库根为基准，
    # 夹具世界也不该被要求出现在仓库根——这类引用直接放过。除此之外一律要能找到。
    world_relative = ("codex/", "entries/", "canon/", "sandbox/", "archive/")
    pattern = re.compile(r"`([A-Za-z0-9_./\-]+\.(?:py|md|json|yml|yaml|txt))`")
    # 文档之间的互相指向主要靠 markdown 链接，所以链接目标也要一起查
    link_pattern = re.compile(r"\]\(([^)\s]+\.(?:py|md|json|yml|yaml|txt))\)")
    missing = []
    for name in DOCS:
        here = (ROOT / name).parent
        text = doc(name)
        for target in sorted(set(pattern.findall(text)) | set(link_pattern.findall(text))):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            rel = target.lstrip("/")  # 文档里写成 `/world.schema.json` 指的是仓库根那个文件
            if rel in skip:
                continue
            if rel.startswith(world_relative) and not (ROOT / rel).exists():
                continue
            if any((base / rel).exists() for base in (here, ROOT)):
                continue
            missing.append(f"{name} → {target}")
    assert not missing, "文档引用了不存在的文件：" + "；".join(missing)

    # 豁免不是放过：那两个「由 init 生成」的名字必须真的出现在生成它们的代码里
    assert "CONSTITUTION.md" in (ROOT / "store/write.py").read_text(encoding="utf-8"), \
        "CONSTITUTION.md 的豁免失效：store/write.py 里已经没有它了"
    assert "classlint.yaml" in (ROOT / "classlint/classlint.py").read_text(encoding="utf-8"), \
        "classlint.yaml 的豁免失效：classlint.py 里已经没有它了"


def check_doc_commands_exist():
    """文档里的 `python3 xxx.py` 必须指向存在的脚本——复制粘贴就该跑得起来。"""
    pattern = re.compile(r"python3 ([A-Za-z0-9_/.\-]+\.py)")
    missing = []
    for name in DOCS:
        here = (ROOT / name).parent
        for cmd in sorted(set(pattern.findall(doc(name)))):
            if any((base / cmd).exists() for base in (here, ROOT)):
                continue
            missing.append(f"{name} → python3 {cmd}")
    assert not missing, "文档里的命令指向不存在的脚本：" + "；".join(missing)


def check_code_identifiers_exist():
    """反引号里的代码名（常量、字段、函数）必须在代码里存在。

    只查两类不会与散文混淆的写法：全大写常量（`FIELD_TABLE`）与小写含下划线的名字
    （`superseded_by` / `check_chain`）。散文词、外来格式字段在豁免表里写清理由。
    """
    code = "".join(p.read_text(encoding="utf-8")
                   for p in (*CORE_SRC, *ECON_SRC, *CL_SRC, WORKFLOW,
                             *sorted((ROOT / "tests").glob("*.py")),
                             *sorted((ROOT / "classlint" / "tests").glob("*.py"))))
    known = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    skip = {
        "extensions": "SillyTavern 角色卡规范里的字段名，不是我们的代码名（PR#5 才接线）",
        "quantity": "项目文书里的想法，代码里没有这个概念",
        "institution": "classlint 文档里的反例条目 type，不是枚举值",
        "affinity": "classlint 规划中的个人关系类型，尚未实现",
        "allegiance": "classlint 规划中的个人关系类型，尚未实现",
        "bond": "classlint 规划中的个人关系类型，尚未实现",
        "history": "classlint 规划中的个人关系类型，尚未实现",
        "kin": "classlint 规划中的个人关系类型，尚未实现",
    }
    missing = []
    for name in DOCS:
        text = doc(name)
        tokens = set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", text))
        tokens |= set(re.findall(r"`([a-z][a-z0-9]*_[a-z0-9_]+)`", text))
        for tok in sorted(tokens):
            if tok in skip or tok in known:
                continue
            missing.append(f"{name} → `{tok}`")
    assert not missing, "文档里的代码名在代码里找不到（改名了？）：" + "；".join(missing)


def check_stale_claims_are_gone():
    """已经被证伪的旧说法不得复现——它们正是这份文档要修掉的东西。"""
    stale = ("规则表 22 条", "22 条 CA", "五套测试世界", "七层字典", "七层链",
             "七层，刻意最小", "Sprint 0 基础层", "ideology=6",
             # 可写接口落地后过期：只读是默认值，不再是「全部」
             "只读界面 v0.1", "写入表单与治理界面是下一步",
             "只读**：`POST` / `PUT` / `DELETE` / `PATCH`")
    hits = [f"{name}: 「{s}」" for name in DOCS for s in stale if s in doc(name)]
    assert not hits, "文档里还留着已被证伪的旧说法：" + "；".join(hits)


def ci_check_names() -> set[str]:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    names = set()
    for job, spec in wf["jobs"].items():
        for version in spec["strategy"]["matrix"]["python-version"]:
            names.add(f"{job} ({version})")
    return names


def ci_scripts(job: str) -> list[str]:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    out: list[str] = []
    for step in wf["jobs"][job]["steps"]:
        out += re.findall(r"python3 ([A-Za-z0-9_/.\-]+\.py)", step.get("run", ""))
    return out


def check_ci_check_names_match_docs():
    """分支保护按名字要求检查，所以文档写的名字必须就是 CI 产出的名字。"""
    names = ci_check_names()
    for name in ("CONTRIBUTING.md", "docs/协作流程.md"):
        found = {f"{job} ({version})"
                 for job, version in re.findall(r"`(canonlint|classlint) \((\d+\.\d+)\)`",
                                                doc(name))}
        assert found == names, \
            f"{name} 里的检查名 {sorted(found)} 与 CI 的 {sorted(names)} 不一致"


def check_ci_steps_match_contributing():
    """CONTRIBUTING 说某个检查跑哪几个脚本，CI 就得跑哪几个——不能只是「写了」。"""
    rows = re.findall(r"^\| `(canonlint|classlint) \([\d.]+\)`[^|]*\|([^|]+)\|\s*$",
                      doc("CONTRIBUTING.md"), re.M)
    listed = {job: re.findall(r"`([A-Za-z0-9_/.\-]+\.py)`", cell) for job, cell in rows}
    assert set(listed) == set(ci_check_names() and {"canonlint", "classlint"}), \
        f"CONTRIBUTING.md 的检查名表解析失败：{sorted(listed)}"
    for job in ("canonlint", "classlint"):
        assert listed[job] == ci_scripts(job), \
            f"CONTRIBUTING.md 里 {job} 跑的脚本是 {listed[job]}，CI 跑的是 {ci_scripts(job)}"


def check_ci_covers_every_test_script():
    """每个测试脚本都必须真的在某条 CI 命令里跑。

    为什么：`check_ci_check_names_match_docs` / `check_ci_steps_match_contributing`
    都是拿 CI 的 job 表去比文档——**把 classlint 整个 job 连同它在
    CONTRIBUTING 里的那一行一起删掉，这两条依然全绿**（评审 2026-10-19 实测）。
    这里反过来钉：清单从**文件系统**数出来，CI 必须一条不少地跑。
    """
    scripts = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
    scripts.append("classlint/tests/run_tests.py")
    workflow = (ROOT / ".github/workflows/canonlint.yml").read_text(encoding="utf-8")
    runs = "\n".join(re.findall(r"^\s*run:\s*(.+)$", workflow, re.M))
    missing = [s for s in scripts if s not in runs]
    assert not missing, (
        f"这些测试脚本没有任何一条 CI 命令在跑：{missing}。"
        f"CI 的 run: 行是：{runs}")
    contributing = doc("CONTRIBUTING.md")
    for s in scripts:
        assert s in contributing, f"CONTRIBUTING.md 没有说 {s} 该怎么跑"
    return []


def check_hook_has_no_strict():
    """init 装的钩子不带 --strict，文档也是这么写的（工具与文档不能各说一套）。"""
    hook_lines = [ln for ln in (ROOT / "store/write.py").read_text(encoding="utf-8").splitlines()
                  if "show-toplevel" in ln]
    assert hook_lines, "store/write.py 里找不到写钩子正文的那一行"
    for line in hook_lines:
        assert "--strict" not in line, "init 装的钩子带了 --strict，但文档说不带"
    flow = doc("docs/协作流程.md")
    assert "不带 `--strict`" in flow, "docs/协作流程.md 应写明 init 装的钩子不带 --strict"


def check_version_strings_match_code():
    """版本号只有一个来源（canonlint.py 的 PROTOCOL_VERSION）：文档里写的必须跟它一样。"""
    want = canonlint.PROTOCOL_VERSION
    found = []
    for name in DOCS:
        for value in re.findall(r'PROTOCOL_VERSION\s*=\s*"([^"]+)"', doc(name)):
            found.append((name, value))
    assert found, "文档里一处 PROTOCOL_VERSION 都没写（PROTOCOL.md 至少该说明版本号从哪来）"
    bad = [f"{name} 写的是 {value}" for name, value in found if value != want]
    assert not bad, f"协议版本号对不上代码（代码是 {want}）：{bad}"


CHECKS = (
    ("规则编号在文档与代码之间双向一致", check_rule_ids_match_code),
    ("文档里的规则条数与代码一致", check_rule_counts_match_code),
    ("层级字典（名字、顺序、序号、层数）与代码一致", check_layer_dictionary_matches_code),
    ("测试项数 / 夹具数与实测一致", check_test_counts_match_docs),
    ("PE 规则的「已实现」与「规划」说得对", check_pe_claims_match_code),
    ("文档提到的文件都存在", check_doc_paths_exist),
    ("文档提到的 python3 脚本都存在", check_doc_commands_exist),
    ("文档提到的代码名在代码里存在", check_code_identifiers_exist),
    ("被证伪的旧说法不再出现", check_stale_claims_are_gone),
    ("CI 检查名与文档双向一致", check_ci_check_names_match_docs),
    ("CI 跑的脚本与 CONTRIBUTING 写的一致", check_ci_steps_match_contributing),
    ("每个测试脚本都有 CI 在跑", check_ci_covers_every_test_script),
    ("init 的钩子不含 --strict（与文档一致）", check_hook_has_no_strict),
    ("文档里的协议版本号与代码一致", check_version_strings_match_code),
    ("全部项目文档都在总索引里分类且可追踪", check_document_index_covers_all),
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
