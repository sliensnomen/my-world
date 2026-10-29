# classlint 正文别名识别 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `codex/entities.yaml` 真正用于正文别名识别，并在 `check --json` 输出确定性的 `mentions`，同时修复已知文档漂移。

**Architecture:** 在现有 `classlint/classlint.py` 增加注册表加载与正文匹配两个辅助函数，只在 `cmd_check` 的 JSON 阶段接线。`run_checks()`、CL/PE 判定、文本输出和 graph 完全不变；配置错误复用 `ConfigError` 和退出码 2。

**Tech Stack:** Python 3 标准库、PyYAML、JSON、Markdown、仓库现有脚本式断言测试（不引 pytest）。

**Spec:** `docs/superpowers/specs/2026-10-29-classlint-entity-mentions-design.md`

## Global Constraints

- 只扫描正文，不归一 frontmatter 关系目标，不改写原文，不改变 CL/PE、文本输出或 graph。
- `mentions` 元素固定为 `{entity, alias, count}`；最长别名优先、非重叠、区分大小写、按首次出现排序。
- 缺少 `entities.yaml` 或空注册表输出 `mentions: []`；坏注册表走 `ConfigError` 和退出码 2。
- 不引入新依赖、NLP、AI、字符偏移、mentions 子命令或新 CL 规则。
- 新测试必须先看到红再实现；使用真实临时世界，不修改既有夹具。
- 作品层草案只修契约号；汇报只修协议号，设计理念不代写。
- 保留主工作区已有修改，不执行 `git add` / `git commit` / merge / push。

## Review Focus

1. **长短别名与英文部分词**：灰港/灰港城不得重复计数，harbor 不得命中 harbor-master 或 harbormaster；Task 1 Step 2 的精确 mentions 列表锁住。
2. **旧世界缺文件、空注册表和无匹配正文**：必须输出空列表而不是配置错误；Task 1 Step 2 的 baseline/空表分支锁住。
3. **未知 id、重复别名、空别名、非字符串、坏形状和坏 YAML**：必须全部返回 2 且指出 entities.yaml；Task 1 Step 2 的错误矩阵锁住。
4. **别名副作用越界**：findings、frontmatter 关系、文本输出和 graph 不得改变；Task 1 Step 2 的前后对比锁住。
5. **输出稳定性**：同一 `(entity, alias)` 合并计数，按首次出现排序；Task 1 Step 2 用手工推导的字面期望值锁住。

---

### Task 1: 注册表加载、正文匹配与 JSON 接线

**Files:**
- Modify: `classlint/classlint.py`（`re` 导入、两个辅助函数、`cmd_check` JSON）
- Test: `classlint/tests/run_tests.py`（临时世界辅助函数与两项意图检查）

**Interfaces:**
- Consumes: 现有 `ConfigError`、`ID_RE`、`Entry.body`、`cmd_check()` 的 entries/index。
- Produces: `load_entity_aliases(root: Path, index: dict[str, Entry]) -> dict[str, str]`、`body_mentions(body: str, aliases: dict[str, str]) -> list[dict]`，以及每个 JSON entry 的 `mentions`。

- [x] **Step 1: 建立绿色基线**

Run: `python3 classlint/tests/run_tests.py`

Expected: `18 个夹具世界 | 全部通过`。

- [x] **Step 2: 写入真实行为红测试**

在 `classlint/tests/run_tests.py` 的 `check_legitimacy_forms_are_indistinguishable()` 前加入：

```python
def _mentions_world(td: str, body: str, registry: str | None = None) -> Path:
    world = Path(td) / "w"
    (world / "codex").mkdir(parents=True)
    (world / "classlint.yaml").write_text(
        "name: mentions\nclasslint: \"0.1\"\nrules: {}\n", encoding="utf-8")
    (world / "codex" / "gray-harbor.md").write_text(
        "---\nid: gray-harbor\ntitle: 灰港\ntype: faction\n"
        f"extracts: [tenant]\n---\n{body}\n", encoding="utf-8")
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
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            classlint.cmd_check(world, False, [])
        expect("mentions" not in text.getvalue() and "灰港" not in text.getvalue(),
               f"文本输出被正文提及改变：{text.getvalue()}")
        graph = io.StringIO()
        with contextlib.redirect_stdout(graph):
            classlint.cmd_graph(world, "json")
        graph_data = json.loads(graph.getvalue())
        expect(set(graph_data) == {"nodes", "edges"},
               f"graph 形状被别名改变：{graph_data.keys()}")
    with tempfile.TemporaryDirectory() as td:
        world = _mentions_world(td, "没有注册别名。", "entities: {}\n")
        code, data = _check_json(world)
        expect(code == 0 and all(e["mentions"] == [] for e in data["entries"]),
               "空注册表应输出空 mentions")
    if not failures:
        print("PASS 正文别名进入 check --json（计数/边界/兼容/不改变判定）")
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
```

文件顶部导入 `json`，并在 `main()` 的 legitimacy 检查后追加：

```python
    failures += check_entity_mentions_in_json()
    failures += check_entity_registry_errors_are_config_errors()
```

- [x] **Step 3: 运行并确认红在功能缺失**

Run: `python3 classlint/tests/run_tests.py`

Expected: 新检查 FAIL，JSON entry 没有 `mentions` 键；既有 18 个世界和其他意图断言仍通过。

- [x] **Step 4: 实现两个辅助函数**

在 `classlint/classlint.py` 顶部加入 `import re`，在 `load_config()` 前加入：

```python
def load_entity_aliases(root: Path, index: dict[str, Entry]) -> dict[str, str]:
    path = root / "codex" / "entities.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path} 解析失败: {exc}")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 顶层必须是映射")
    entities = data.get("entities", {})
    if entities is None:
        entities = {}
    if not isinstance(entities, dict):
        raise ConfigError(f"{path} 的 entities 必须是映射")
    aliases: dict[str, str] = {}
    for stable_id, record in entities.items():
        if not isinstance(stable_id, str) or not ID_RE.match(stable_id):
            raise ConfigError(f"{path} 的稳定 id 非法: {stable_id!r}")
        if stable_id not in index:
            raise ConfigError(f"{path} 的稳定 id `{stable_id}` 没有对应条目卡")
        if not isinstance(record, dict):
            raise ConfigError(f"{path} 的 `{stable_id}` 记录必须是映射")
        raw = record.get("aliases", [])
        if not isinstance(raw, list):
            raise ConfigError(f"{path} 的 `{stable_id}.aliases` 必须是列表")
        for alias in raw:
            if not isinstance(alias, str) or not alias.strip():
                raise ConfigError(f"{path} 的 `{stable_id}.aliases` 含空或非字符串别名: {alias!r}")
            if alias in aliases:
                raise ConfigError(f"{path} 的别名 `{alias}` 重复注册")
            aliases[alias] = stable_id
    return aliases


def body_mentions(body: str, aliases: dict[str, str]) -> list[dict]:
    if not aliases or not body:
        return []

    def ascii_word(char: str) -> bool:
        return char.isascii() and (char.isalnum() or char == "_")

    parts = []
    for alias in sorted(aliases, key=lambda value: (-len(value), value)):
        left = r"(?<![A-Za-z0-9_-])" if ascii_word(alias[0]) else ""
        right = r"(?![A-Za-z0-9_-])" if ascii_word(alias[-1]) else ""
        parts.append(left + re.escape(alias) + right)
    pattern = re.compile("|".join(parts))
    counts: dict[tuple[str, str], int] = {}
    first: dict[tuple[str, str], int] = {}
    for match in pattern.finditer(body):
        alias = match.group(0)
        key = (aliases[alias], alias)
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, match.start())
    ordered = sorted(counts, key=lambda key: (first[key], key[0], key[1]))
    return [{"entity": entity, "alias": alias, "count": counts[(entity, alias)]}
            for entity, alias in ordered]
```

- [x] **Step 5: 只在 cmd_check 的 JSON 阶段接线**

在 `cmd_check` 现有的 `entries, index, findings, disabled = run_checks(root)` 后、同一 `try` 内加入：

```python
        aliases = load_entity_aliases(root, index)
```

JSON entry 改为：

```python
                {"id": e.id, "path": e.rel, "meta": dict(e.meta),
                 "body_chars": len(e.body.strip()),
                 "mentions": body_mentions(e.body, aliases)}
```

初始化模板中的“别名解析待实现”改为“正文提及见 check --json 的 mentions”。

- [x] **Step 6: 跑到 classlint 全绿**

Run: `python3 classlint/tests/run_tests.py`

Expected: `18 个夹具世界 | 全部通过`，两个新意图检查均 PASS。

### Task 2: 文档漂移与规格状态同步

**Files:**
- Modify: `classlint/README.md`
- Modify: `classlint/PROTOCOL.md`
- Modify: `docs/superpowers/specs/2026-10-24-works-layer-design.md`
- Modify: `叙境社汇报_演讲提纲_v2_中英对照.md`
- Modify: `docs/README.md`
- Modify: `docs/superpowers/specs/2026-10-29-classlint-entity-mentions-design.md`
- Modify: `docs/superpowers/plans/2026-10-29-classlint-entity-mentions.md`

**Interfaces:**
- Consumes: Task 1 的真实 `mentions` 输出和匹配语义。
- Produces: 与实现一致的现行说明，以及已实施规格和已执行计划。

- [x] **Step 1: 更新 classlint 使用与协议说明**

`classlint/README.md` 的 entries 字段补充 `mentions`，并加入：

```markdown
`mentions` 是正文别名报告：`{entity, alias, count}`。别名来自 `codex/entities.yaml`；缺文件或没有匹配时为 `[]`。匹配区分大小写、最长别名优先且不重叠，英文/数字别名要求词边界。它是只读报告，不改变 findings、CL/PE 判定、文本输出或 graph；坏注册表返回退出码 2。
```

`classlint/PROTOCOL.md` §3.4 增加“正文提及报告”条目，明确相同语义和永不进退出码。

- [x] **Step 2: 修复三处独立文档漂移**

- 作品层草案 `docs/superpowers/specs/2026-10-24-works-layer-design.md` 的剩余“契约 0.7”改“契约 0.8”，其他文字不动。
- 汇报材料的中文“协议 1.8”和英文“protocol 1.8”全部改 1.9；设计理念仍标待作者补充，不代写。
- `classlint/README.md` 的别名说明与初始化模板保持“已实现，见 mentions”，不得再写待实现。

- [x] **Step 3: 收口规格、计划和索引状态**

- 本规格状态改“已确认并实施，2026-10-29”。
- 本计划只勾选实际完成步骤。
- `docs/README.md` 登记本计划；规格状态改“现行”，计划状态改“历史”。

Run: `python3 tests/test_docs.py && python3 classlint/tests/run_tests.py`

Expected: 文档 15/15、classlint 18 个世界与全部意图断言通过。

### Task 3: 全量验收与独立评审

**Files:**
- Review: 全部 Task 1–2 变更
- Verify: `docs/superpowers/plans/2026-10-29-classlint-entity-mentions.md`

**Interfaces:**
- Consumes: Task 1–2 的实现和文档。
- Produces: 六套绿色证据、真实 CLI 验证和独立评审结论。

- [x] **Step 1: 跑六套标准回归**

```bash
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 tests/test_serve.py
python3 tests/test_docs.py
python3 classlint/tests/run_tests.py
```

Expected: `63 + 12 + 26 + 31 + 15` 全通过，classlint 18 个世界与全部意图断言通过。

- [x] **Step 2: 真实 CLI 验证**

不得修改仓库夹具；在临时世界运行：

```bash
set -e
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 classlint/classlint.py init "$tmp/world"
cat > "$tmp/world/codex/gray-harbor.md" <<'EOF'
---
id: gray-harbor
title: 灰港
type: faction
---
灰港城与灰港。
EOF
python3 classlint/classlint.py check "$tmp/world" --json > "$tmp/before.json"
cat > "$tmp/world/codex/entities.yaml" <<'EOF'
entities:
  gray-harbor:
    aliases: [灰港, 灰港城]
EOF
python3 classlint/classlint.py check "$tmp/world" --json > "$tmp/after.json"
python3 - "$tmp/before.json" "$tmp/after.json" <<'PY'
import json, sys
before = json.load(open(sys.argv[1], encoding="utf-8"))
after = json.load(open(sys.argv[2], encoding="utf-8"))
assert all(e["mentions"] == [] for e in before["entries"])
assert after["entries"][0]["mentions"] == [
    {"entity": "gray-harbor", "alias": "灰港城", "count": 1},
    {"entity": "gray-harbor", "alias": "灰港", "count": 1},
]
print("CLI mentions 与缺文件兼容：PASS")
PY
printf 'entities: [\n' > "$tmp/world/codex/entities.yaml"
set +e
python3 classlint/classlint.py check "$tmp/world" --json > /dev/null 2> "$tmp/error.txt"
status=$?
set -e
test "$status" -eq 2
python3 - "$tmp/error.txt" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8").read()
assert "entities.yaml" in text, text
print("坏注册表 exit 2：PASS")
PY
```

- [x] **Step 3: 核对 diff 并独立评审**

核对 diff 只含本计划文件、实现、测试和文档；没有既有夹具变化。让独立评审检查完整变更，Critical/Important 必须先写复现红测试再修复并重新跑六套；Minor 记录后在最终回复说明。

- [x] **Step 4: 无提交交付**

不执行 commit、merge 或 push。最终回复列出六套结果、真实 CLI 结果、评审结论和任何延后 Minor。
