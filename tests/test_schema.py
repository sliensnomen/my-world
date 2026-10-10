#!/usr/bin/env python3
"""契约测试：world.schema.json 必须同时做到两件事 ——

  1. **接受真实语料**（六个世界 + classlint 的好夹具，一个都不能冤枉）；
  2. **拒绝故意写坏的样本**，并且指出坏在哪个字段上。

外加一条防漂移：契约里的词表必须和 canonlint.py / classlint.py / econ.py 的常量
逐字一致。协作者改了代码忘了改契约，CI 就该红——这是这个仓库第一次有能力
自己发现「散文说的和代码做的不一样」。

用法：
  python3 tests/test_schema.py             # 校验
  python3 tests/test_schema.py --verbose   # 额外打印每个合规条目的路径
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
import canonlint  # noqa: E402
import econ  # noqa: E402
import json_schema_subset as js  # noqa: E402

SCHEMA_PATH = ROOT / "world.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_classlint():
    # 必须先在 sys.modules 里登记：classlint.py 用了 @dataclass，而 dataclasses
    # 会回头查 sys.modules[cls.__module__]（按文件路径加载时它默认不在里面）。
    spec = importlib.util.spec_from_file_location(
        "classlint_impl", ROOT / "classlint" / "classlint.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["classlint_impl"] = module
    spec.loader.exec_module(module)
    return module


CLASSLINT = _load_classlint()

# 好语料：这些目录里每一个条目都必须通过契约。少一个、多一个都要有人来解释。
GOOD_CORPUS_DIRS = [
    "tests/world-clean/entries",
    "tests/world-arrakis/entries",
    "tests/world-westeros/entries",
    "tests/world-middle-earth/entries",
    "classlint/tests/clean",
    "classlint/tests/feudal-rent",
    "classlint/tests/merchant-capital",
    "classlint/tests/pe001-ok",
    "classlint/tests/pe002-ok",
    "classlint/tests/pe003-ok",
    "classlint/tests/world-arrakis",
    "classlint/tests/world-westeros",
]
EXPECTED_GOOD_ENTRIES = 115  # 条目数变了就要显式改这个数字，不能悄悄漂
# 55 = 四个 WGP 世界的条目（clean 3 + arrakis 22 + westeros 16 + middle-earth 14）
# 60 = classlint 八个好夹具（clean 5 + feudal-rent 4 + merchant-capital 4
#      + pe001-ok 3 + pe002-ok 3 + pe003-ok 3 + world-arrakis 22 + world-westeros 16）

# 故意写坏的样本：(路径, 期望出现的报错路径前缀之一)
BAD_SAMPLES = [
    ("tests/world-bad/entries/bad-fields.md", ["$.secret_level"]),
    ("tests/world-bad/entries/type-errors.md",
     ["$.canon_refs", "$.load_bearing", "$.ai_assisted"]),
    ("classlint/tests/structure-bad/codex/bad-field.md", ["$.secret_level"]),
    ("classlint/tests/structure-bad/codex/bad-rel.md",
     ["$.controls", "$.depends_on[0].critical", "$.extracts[0]"]),
    ("tests/world-crash/entries/list-type.md", ["$.type"]),
    ("tests/world-crash/entries/list-stance.md", ["$.conflicts_with[0].stance"]),
]

FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)


def read_frontmatter(path: Path):
    """读 frontmatter；读不出 mapping 就返回 None（那是 CA100 的活儿，不是契约的）。"""
    text = path.read_text(encoding="utf-8-sig")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def normalize(value):
    """YAML 把 `date: 2026-10-02` 解成 datetime.date，而契约的规范形是 ISO 字符串。

    这是 YAML 的隐式类型细节，不是我们契约的一部分，所以校验前归一化。
    （canonlint 的 CA103 反过来要求真的拿到 date 对象——这是规则的活儿。）
    """
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def with_pack(pack_name: str):
    """把扩展包的 KNOWN_FIELDS 合并进契约的 properties —— 这就是「存储扩展」的缝。"""
    packed = dict(SCHEMA)
    props = dict(SCHEMA["properties"])
    props.update(SCHEMA["x-packs"][pack_name]["fields"])
    packed["properties"] = props
    return packed


# ---- 各项检查 -------------------------------------------------------------

def check_validator_understands_schema(problems):
    try:
        js.check_schema_supported(SCHEMA)
    except js.UnsupportedKeyword as exc:
        problems.append(f"契约用到了校验器不认识的关键字：{exc}")


def check_validator_is_fail_loud(problems):
    broken = {"type": "object", "properties": {"a": {"type": "string", "minLenght": 3}}}
    try:
        js.validate({"a": "x"}, broken)
        problems.append("校验器对拼错的关键字 minLenght 没有报错——它就不算 fail-loud")
    except js.UnsupportedKeyword:
        pass


def check_vocabulary_matches_code(problems):
    sv = SCHEMA["x-strict-vocabulary"]
    # 第四列 = 该词表是无序集合（比较前排序）；LAYERS 与 REQUIRED_FIELDS 的顺序有意义
    pairs = [
        ("x-strict-vocabulary.type", sv["type"], canonlint.VALID_TYPES, True),
        ("x-strict-vocabulary.status", sv["status"], canonlint.VALID_STATUS, True),
        ("x-strict-vocabulary.layer", sv["layer"], canonlint.LAYERS, False),
        ("x-strict-vocabulary.depends_on.kind", sv["depends_on.kind"],
         canonlint.KIND_INITIAL_SET, True),
        ("x-strict-required", SCHEMA["x-strict-required"],
         canonlint.REQUIRED_FIELDS, False),
        ("x-packs.econ.fields", sorted(SCHEMA["x-packs"]["econ"]["fields"]),
         econ.KNOWN_FIELDS, True),
        # 契约的核心必填 = classlint 的 REQUIRED_FIELDS（canonlint 的十项是严格档，
        # 住在 x-strict-required 里，因为它要求的是「严格模式下该填什么」）
        ("required", SCHEMA["required"], CLASSLINT.REQUIRED_FIELDS, True),
    ]
    for label, in_schema, in_code, as_set in pairs:
        a = sorted(in_schema) if as_set else list(in_schema)
        b = sorted(in_code) if as_set else list(in_code)
        if a != b:
            problems.append(f"{label}: 契约写 {a}，代码写 {b}")


def check_relation_aliases_match_classlint(problems):
    aliases = SCHEMA["x-relation-source"]["aliases"]
    for rel, attrs in CLASSLINT.RELATIONS.items():
        got = aliases.get(rel)
        if got is None:
            problems.append(f"classlint 有 {rel}，契约的 x-relation-source.aliases 里没有")
        elif sorted(got["attrs"]) != sorted(attrs):
            problems.append(f"{rel}: 契约允许 {sorted(got['attrs'])}，"
                            f"classlint 允许 {sorted(attrs)}")
    canonical = SCHEMA["$defs"]["relation"]
    if canonical.get("required") != ["type", "target"]:
        problems.append(f"规范形 relations 的必填键应为 ['type','target']，"
                        f"实为 {canonical.get('required')}")


def check_good_corpus_conforms(problems, verbose):
    total = 0
    for rel_dir in GOOD_CORPUS_DIRS:
        directory = ROOT / rel_dir
        if not directory.is_dir():
            problems.append(f"好语料目录不存在：{rel_dir}")
            continue
        for path in sorted(directory.rglob("*.md")):
            if path.name == "README.md":
                continue  # 目录说明不是条目
            rel = path.relative_to(ROOT)
            meta = read_frontmatter(path)
            if meta is None:
                problems.append(f"{rel}: 读不出 frontmatter（它被当成好语料）")
                continue
            total += 1
            for msg in js.validate(normalize(meta), SCHEMA):
                problems.append(f"{rel}: {msg}")
            if verbose:
                print(f"  ok  {rel}")
    if total != EXPECTED_GOOD_ENTRIES:
        problems.append(f"好语料条目数从 {EXPECTED_GOOD_ENTRIES} 变成 {total}"
                        "（确认后改 EXPECTED_GOOD_ENTRIES）")


def check_bad_samples_are_rejected(problems):
    for rel, prefixes in BAD_SAMPLES:
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"坏样本不存在：{rel}")
            continue
        meta = read_frontmatter(path)
        if meta is None:
            problems.append(f"{rel}: 读不出 frontmatter")
            continue
        msgs = js.validate(normalize(meta), SCHEMA)
        if not msgs:
            problems.append(f"{rel}: 应当被判红，却通过了契约")
            continue
        paths = {m.split(":", 1)[0] for m in msgs}
        if not any(any(p.startswith(prefix) for prefix in prefixes) for p in paths):
            problems.append(f"{rel}: 判红了但没指出预期的字段 {prefixes}，"
                            f"实际报错在 {sorted(paths)}")


def check_econ_pack_seam(problems):
    directory = ROOT / "tests" / "world-econ" / "entries"
    files = sorted(directory.rglob("*.md"))
    with_figures = []
    for path in files:
        meta = read_frontmatter(path)
        if meta and "figures" in meta:
            with_figures.append(path)
    if len(with_figures) != 5:
        problems.append(f"world-econ 里带 figures 的条目数从 5 变成 {len(with_figures)}")
    for path in files:
        rel = path.relative_to(ROOT)
        meta = normalize(read_frontmatter(path) or {})
        msgs = js.validate(meta, SCHEMA)
        has_figures = "figures" in meta
        if has_figures and not any("figures" in m for m in msgs):
            problems.append(f"{rel}: 不带 econ 包时 figures 应当被当成未定义字段，"
                            f"实际报错为 {msgs}")
        if not has_figures and msgs:
            problems.append(f"{rel}: 不带 econ 包也不该报错，实际 {msgs}")
        for msg in js.validate(meta, with_pack("econ")):
            problems.append(f"{rel}: 带上 econ 包仍不合契约 —— {msg}")


def check_extension_hatch(problems):
    good = {"id": "grey-harbor", "title": "灰港", "type": "地点",
            "x-st-entry": {"position": 1, "order": 100},
            "x-wgp-note": "随便写"}
    msgs = js.validate(good, SCHEMA)
    if msgs:
        problems.append(f"x- 前缀扩展字段被拒：{msgs}")

    dotted = dict(good)
    dotted["x-st-entry"] = {"position": 1, "order": 100, "vectorized": False}
    if js.validate(dotted, SCHEMA):
        problems.append("x- 命名空间对象内部不该被契约管")

    unknown = {"id": "a", "title": "b", "type": "c", "secret_level": 3}
    if not js.validate(unknown, SCHEMA):
        problems.append("未知顶层字段 secret_level 没被拒（CA106 会拒它）")


def check_canonical_relations(problems):
    entry = {"id": "grey-harbor", "title": "灰港", "type": "地点",
             "relations": [{"type": "depends_on", "target": "grain-belt",
                            "kind": "economy", "critical": True},
                           {"type": "controls", "target": "gh-customs",
                            "note": "关税"},
                           {"type": "矛盾", "target": "gh-fleet"}]}
    msgs = js.validate(entry, SCHEMA)
    if msgs:
        problems.append(f"规范形 relations 被拒：{msgs}")

    bad = dict(entry)
    bad["relations"] = [{"type": "depends_on"}]  # 缺 target
    if not js.validate(bad, SCHEMA):
        problems.append("规范形 relations 缺 target 没被拒")

    refs = dict(entry)
    refs["canon_refs"] = [{"id": "grain-belt"}]  # canonlint: 只允许字符串（CA109）
    if not js.validate(refs, SCHEMA):
        problems.append("canon_refs 里放对象没被拒（canonlint 报 CA109）")

    bare = dict(entry)
    bare["conflicts_with"] = ["gh-fleet", {"id": "gh-customs", "stance": "official"}]
    if js.validate(bare, SCHEMA):
        problems.append("conflicts_with 的简式/对象式被拒（两者都合法）")

    illegal_id = {"id": "灰港", "title": "x", "type": "y"}
    if not js.validate(illegal_id, SCHEMA):
        problems.append("非法 id 没被拒（canonlint 的 CA105 会拒它）")


def check_checks_are_discriminating(problems):
    """证明这些检查有鉴别力：把某条约束拿掉，被它拦住的坏样本就应当通过。

    一个永远判红的测试和没有测试是一回事。这里用「反向」断言把鉴别力钉死：
    去掉 additionalProperties 之后，只带未定义字段的坏条目必须变合法。
    """
    loose = {k: v for k, v in SCHEMA.items() if k != "additionalProperties"}
    meta = read_frontmatter(ROOT / "classlint/tests/structure-bad/codex/bad-field.md")
    if meta is None:
        problems.append("鉴别力测试的样本读不出来：structure-bad/bad-field.md")
        return
    if js.validate(normalize(meta), loose):
        problems.append("拿掉 additionalProperties 后 bad-field.md 仍被判红——"
                        "说明拦住它的不是那条约束，鉴别力测试自身失效")
    strict = js.validate(normalize(meta), SCHEMA)
    if not strict:
        problems.append("带上 additionalProperties 时 bad-field.md 却通过了")


def main() -> int:
    verbose = "--verbose" in sys.argv
    checks = [
        ("校验器看得懂契约", check_validator_understands_schema),
        ("校验器 fail-loud（拼错的关键字会报错）", check_validator_is_fail_loud),
        ("契约词表与代码常量逐字一致", check_vocabulary_matches_code),
        ("关系别名与 classlint 的七种关系一致", check_relation_aliases_match_classlint),
        ("好语料全部合规", lambda p: check_good_corpus_conforms(p, verbose)),
        ("坏样本全部判红且指出字段", check_bad_samples_are_rejected),
        ("扩展包的缝（econ 的 figures）", check_econ_pack_seam),
        ("x- 扩展位可用、未知字段被拒", check_extension_hatch),
        ("规范形 relations 与旧式简式", check_canonical_relations),
        ("检查有鉴别力（拿掉约束坏样本就通过）", check_checks_are_discriminating),
    ]
    problems: list[str] = []
    for label, check in checks:
        out: list[str] = []
        try:
            check(out)
        except js.UnsupportedKeyword as exc:
            # 契约长过了校验器 —— 这是一条结论，不是崩溃，要报成 FAIL 而不是 traceback
            out.append(f"契约长过了校验器：{exc}")
        if out:
            for msg in out:
                problems.append(f"[{label}] {msg}")
        else:
            print(f"PASS {label}")

    if problems:
        for msg in problems:
            print(f"FAIL {msg}")
    print(f"\n{len(checks)} 项检查 | "
          f"{'全部通过' if not problems else f'{len(problems)} 个失败'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
