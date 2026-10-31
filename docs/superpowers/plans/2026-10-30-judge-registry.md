# 判定器注册表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分期把 CA/CL/PE/econ 迁移到统一 Rule/Pack 注册表，保持现有行为完全等价，并在全量验收后一次性切换默认后端。

**Architecture:** `judges/` 负责元数据、加载校验、查询与 Finding 适配；各引擎驱动继续拥有执行日程。阶段 0–3 始终默认 legacy，Registry 只用于显式 opt-in 和双跑；阶段 4 原子切换，阶段 5 在一个发布周期后由用户签核删除 legacy。

**Tech Stack:** Python 3 标准库、PyYAML、现有脚本式断言测试、JSON/HTTP、GitHub Actions；不引 pytest 或新依赖。

**Spec:** `docs/superpowers/specs/2026-10-30-judge-registry-design.md`

## Global Constraints

- 不改变协议版本、规则编号、判据、消息、级别、Finding 顺序、stdout/stderr、退出码、JSON、graph 或 mentions。
- Registry 统一加载与适配，引擎保留执行日程；econ 只遍历 `index_parseable`，不得扩大到被遮蔽条目。
- CL100–CL107 必须逐规则注册，禁止把 collect 整体包装成复合 Rule。
- `requires_annotations` / `rule_coverage` 本期不实现；AI、chain、热重载、entry_points 不在本期。
- 阶段 0–3 默认 legacy；阶段 4 才原子切换；legacy 默认运行一个发布周期且无应急回退后才可删除。
- 新测试先红后绿；每批必须双跑并通过六套回归，不能只验证“注册成功”。
- 不修改 `.gitignore` 与 `.review-scratch/`；提交与推送需用户执行时再次确认。

## Review Focus

1. **CA 逐条目交错与 econ 遍历域**：结构/内容 Finding 顺序及被遮蔽条目不得变化；Task 3、4 的双跑序列锁。
2. **CL 扫描与判定拆分**：CL100–CL107 各自加载，collect→CL105→PE 拼接不变；Task 5 的逐规则与顺序测试。
3. **字段、级别与重复选择**：CA102/108 的 info、重复 `--pack econ`、字段冲突和 YAML off→False；Task 2 的加载矩阵。
4. **serve 动态量与后端失败时点**：Date/端口/ts 不制造假差异，非法后端在绑定端口前 exit 2；Task 1、6 的 HTTP 包络。
5. **真实 Finding 与回退**：每条迁移规则必须有正反例和变异证据；阶段 4 原子切换、legacy 回退和阶段 5 删除门槛由 Task 6、7 锁住。

---

### Task 1: 表征基线与双跑比较工具

**Files:**
- Create: `judges/__init__.py`
- Create: `judges/compare.py`
- Modify: `tests/run_tests.py`
- Modify: `tests/test_serve.py`
- Modify: `classlint/tests/run_tests.py`

**Interfaces:**
- Produces: `finding_tuple(f) -> tuple[str, str, str, str]`、`assert_cli_equal(old, new)`、`assert_http_equal(old, new)`、`assert_log_equal(old, new, clock)`。

- [ ] **Step 1: 固化六套绿色基线**

```bash
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 tests/test_serve.py
python3 tests/test_docs.py
python3 classlint/tests/run_tests.py
```

Expected: `63 + 12 + 26 + 31 + 15` 与 18 个 classlint 世界全部通过。

- [ ] **Step 2: 先写比较器红测试**

在现有测试脚本增加意图断言：两条 Finding 仅交换原始顺序必须 FAIL；临时根路径规范化后相同才 PASS；HTTP `Date` 不同可接受，但 status/body/语义头部任一不同必须 FAIL；日志仅 `ts` 不同可由固定时钟处理，其他字段不同必须 FAIL。

Run: `python3 tests/run_tests.py && python3 tests/test_serve.py`

Expected: 新断言因 `judges.compare` 不存在而失败。

- [ ] **Step 3: 实现最小比较工具**

```python
def finding_tuple(f):
    return (f.rule, f.level, f.entry, f.message)


def normalized_cli_result(code, stdout, stderr, root):
    return (code, stdout.replace(str(root), "<WORLD>"),
            stderr.replace(str(root), "<WORLD>"))


def normalized_http_result(status, body, headers):
    semantic = {k: v for k, v in headers.items() if k.lower() != "date"}
    return status, body, semantic
```

保留驱动原始序列和出口排序后序列两份比较；不得只比较最终排序。日志使用注入的固定时钟，除 `ts` 外逐字段比较。

- [ ] **Step 4: 验证比较器与基线均可重复**

Run: 上述两个测试脚本。

Expected: 全部通过；交换 Finding 顺序和改变 body 的负面对照仍会被抓住。

### Task 2: Rule/Pack/Registry 骨架与 econ 参照

**Files:**
- Create: `judges/model.py`
- Create: `judges/registry.py`
- Create: `judges/econ_pack.py`
- Modify: `canonlint.py`
- Modify: `tests/run_tests.py`

**Interfaces:**
- Produces: `Rule`、`Pack`、`Registry`、`RegistryError`、`load_backend(env=None)`、`select_packs(engine, names)`。

- [ ] **Step 1: 写加载失败矩阵红测试**

覆盖：重复规则 id、重复包内 order、当前选择集重复 `ca106_fields`、未知 Pack、非法 scope/level/default_level、非法 `WGP_JUDGE_BACKEND`、重复显式 `--pack econ`、econ 被遮蔽条目、CA102/108 的 `{error, info}`。

断言非法输入在审计前抛 `RegistryError`；重复 econ 选择只加载模块一次但执行两次；econ 不对被遮蔽条目发 CA601/602。

Run: `python3 tests/run_tests.py`

Expected: 新测试因 Registry 类型不存在而失败。

- [ ] **Step 2: 实现不可变元数据与加载器**

```python
@dataclass(frozen=True)
class Rule:
    id: str
    pack: str
    scope: str
    entry_domain: str
    check: object
    default_level: str
    levels: frozenset[str]
    order: int


@dataclass(frozen=True)
class Pack:
    name: str
    version: str
    engine: str
    ca106_fields: frozenset[str]
    rules: tuple[Rule, ...]
```

`Registry` 保存 Pack 映射和选中列表，校验唯一性、scope、级别和字段冲突。`load_backend()` 只接受 `legacy|registry`，本任务默认 `legacy`。加载模块缓存与选择列表分离，允许同一 Pack 重复执行。

- [ ] **Step 3: 迁移 econ 并接入显式 opt-in**

保留 econ 的 `check_entry(meta, rel, add)`，在 `econ_pack` 注册 CA601/602 与 `index_parseable`。canonlint 在 `WGP_JUDGE_BACKEND=registry` 时走新 Pack，否则走旧 `_apply_packs`；本任务不得改变默认后端。

- [ ] **Step 4: 双跑 econ 与全量回归**

对 world-econ（默认与 `--pack econ`）比较原始 Finding、出口 Finding、stdout/stderr/exit；随后运行六套回归。

Expected: 两后端完全一致，六套全绿。

### Task 3: CA 结构与内容迁移（legacy 默认）

**Files:**
- Create: `judges/ca/structure.py`
- Create: `judges/ca/content.py`
- Create: `judges/ca/pack.py`
- Modify: `canonlint.py`
- Modify: `tests/run_tests.py`

**Interfaces:**
- Consumes: Task 2 的 Rule/Registry 和双跑工具。
- Produces: `core-ca` 的 CA100–CA114 与 CA104/CA301/CA302 注册实现。

- [ ] **Step 1: 写逐规则与交错顺序红测试**

逐规则覆盖 CA100、101、102、103、105、106、107、108、109、110、111、112、114、104、301、302。构造同一张卡同时命中结构/内容多个规则，双跑必须保持每张卡 structure→content 交错，而不是先跑完全部结构再跑内容。

Run: `python3 tests/run_tests.py`

Expected: 新实现尚未接入时双跑差异明确显示缺失规则或顺序差异。

- [ ] **Step 2: 拆出逐规则实现并保留日程**

把判定移入 `judges/ca/structure.py` 与 `content.py`，每条 Rule 独立注册；`core-ca` 驱动先保留 store 的 CA114，再对 `all_entries` 逐条目执行结构→内容。不得把多个规则合并成不可查询的黑盒。

- [ ] **Step 3: 双跑并跑六套**

比较所有世界的原始/排序 Finding 和完整输出；重点覆盖重复 id、YAML 原生日期、重复键、实验类型和近失关系名。确认后仍保持 legacy 默认。

Expected: 双跑为零差异，六套全绿。

### Task 4: CA 引用、链、事件、流水与查重迁移（legacy 默认）

**Files:**
- Create: `judges/ca/refs.py`
- Create: `judges/ca/chain.py`
- Create: `judges/ca/events.py`
- Create: `judges/ca/ledger.py`
- Create: `judges/ca/duplicates.py`
- Modify: `judges/ca/pack.py`
- Modify: `canonlint.py`
- Modify: `tests/run_tests.py`

**Interfaces:**
- Consumes: Task 3 的 core-ca 驱动。
- Produces: CA401–CA405、CA501–CA505、CA701–CA712、CA201 的完整注册实现。

- [ ] **Step 1: 写每族正反例与原始顺序红测试**

覆盖所有关系悬空、 archived/draft/trial 状态、层级方向/环/关键来源、事件腿形状/时序/同刻/存在窗口/成员关系、降级承接对豁免。每族分别比较旧新驱动序列，禁止只比较最终排序。

Run: `python3 tests/run_tests.py`

Expected: 未迁移族在 Registry 后端缺失，双跑失败。

- [ ] **Step 2: 逐族迁移并接回现有日程**

迁移 refs→chain→events→ledger→duplicates，CA504 仍只走 report 路径。CA701–CA712 的单条目与跨条目部分可以拆函数，但每条 Rule 独立注册，消息和不双报原则不变。

- [ ] **Step 3: 与 econ 联合双跑**

验证结构/内容/引用/链/事件/流水/查重/econ 的完整日程，含 `--pack econ` 重复选择、CA114 初始发现和 serve 写后审计同口径。随后跑六套。

Expected: 双跑为零差异，legacy 默认未变，六套全绿。

### Task 5: classlint 的 CL 逐规则与 PE 独立包（legacy 默认）

**Files:**
- Create: `judges/cl/structure.py`
- Create: `judges/cl/pack.py`
- Create: `judges/pe/rules.py`
- Create: `judges/pe/pack.py`
- Modify: `classlint/classlint.py`
- Modify: `classlint/tests/run_tests.py`

**Interfaces:**
- Consumes: Task 2 的 Registry 与引擎私有 world 上下文。
- Produces: `core-cl` 的 CL100–CL107、`pe` 的 PE001–PE005/PE009，以及现有开关/拼接行为。

- [ ] **Step 1: 写 CL 逐规则与 PE 实际 Finding 红测试**

每条 CL/PE 至少一个真阳性和一个真阴性。另测：collect→CL105→PE 原始拼接、被遮蔽条目的边、名分两种写法、rules: off 的 `off` 与 `False`、退出码 3、judgement_complete、mentions 与 graph 不变。

Run: `python3 classlint/tests/run_tests.py`

Expected: Registry 后端缺少实际 Finding 或拼接顺序不同，测试失败。

- [ ] **Step 2: 拆分扫描/索引与逐规则判定**

先建立不含判定的扫描/索引步骤，再把 CL100–CL107 各自注册。适配器只转换签名与 Finding，禁止整体包装 collect。保留 CL103 的 classlint 私有字段政策，不写入 `ca106_fields`。

- [ ] **Step 3: 迁移 PE 并保留开关**

把 PE 函数移入 `judges/pe/rules.py`，按原编号顺序注册。`rules: off` 继续仅 PE，未知 id 在执行前配置失败，不级联关闭依赖规则。

- [ ] **Step 4: 双跑 classlint 与六套回归**

比较 18 个世界及所有意图断言的原始/排序 Finding、文本、JSON、graph 和 mentions；随后跑六套。

Expected: 双跑为零差异，legacy 默认未变，六套全绿。

### Task 6: 全量验收、原子切换与独立评审

**Files:**
- Modify: `canonlint.py`
- Modify: `classlint/classlint.py`
- Modify: `serve.py`
- Modify: `.github/workflows/canonlint.yml`
- Modify: `README.md`、`CONTRIBUTING.md`、`docs/判定规则总表.md`、`classlint/README.md`
- Modify: `docs/README.md`
- Create: `docs/代码评审报告-判定器注册表.md`

**Interfaces:**
- Consumes: Task 1–5 的全部双跑证据。
- Produces: 默认 `registry`、显式 legacy 回退、双后端 CI 和验收报告。

- [ ] **Step 1: 先证明全部 Pack 已完成**

逐项检查 Task 1–5 的双跑记录、规则正反例和六套结果；任何缺失都停止，不得切换。

- [ ] **Step 2: 一次性切换默认后端**

把 `WGP_JUDGE_BACKEND` 默认值从 legacy 改为 registry。serve 在绑定端口前确定后端并处理非法值；CLI/serve 继续共用加载函数。CI 为 registry/legacy 两种后端运行全部六套。

- [ ] **Step 3: 验证回退与 serve 比较包络**

显式 `WGP_JUDGE_BACKEND=legacy` 跑六套；registry 再跑六套。HTTP 比较 status/body/语义头部，Date/端口不比较；写请求使用独立世界副本，ts 固定或单列检查。

Expected: 两后端均全绿，非法后端在审计/绑定前 exit 2，无部分结果。

- [ ] **Step 4: 独立评审并写验收报告**

让独立评审检查完整变更、执行日程、遍历域和真实 Finding。Critical/Important 必须先写红测试再修复并跑双后端六套；Minor 记录。报告列出规则覆盖、双跑证据、已知限制和回退方式，请用户明确批准默认 registry，并在 `docs/README.md` 的“评审过程”分类登记该报告。

### Task 7: 一个发布周期后的 legacy 删除门槛

**Files:**
- Modify: `canonlint.py`、`classlint/classlint.py`、`serve.py`、`.github/workflows/canonlint.yml`
- Modify: `docs/代码评审报告-判定器注册表.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: 默认 registry 一个发布周期的运行记录和应急回退记录。
- Produces: 用户签核后的独立 legacy 删除提交；本任务不得提前执行。

- [ ] **Step 1: 核对删除资格**

必须同时满足：一个发布周期已结束、无应急回退、验收报告已签核、独立评审无未解决 Critical/Important。缺任一项停止。

- [ ] **Step 2: 独立提交删除并验证回滚方案**

只删除 legacy 实现和双后端 CI，保留验收报告。提交信息明确“删除已签核的 legacy 后端”，并将 `docs/README.md` 中本计划状态改为“历史”。若后续发现问题，用 `git revert` 恢复该独立删除提交，禁止 reset 或强推。
