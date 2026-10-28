# 文档分类、追踪与现行参考治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立覆盖全部项目文档的分类索引与自动追踪检查，并把现行参考文档更新到协议 1.8、契约 0.6 和当前实现。

**Architecture:** `docs/README.md` 是唯一文档登记处，第一列表格链接是机器可读接口；`tests/test_docs.py` 从文件系统发现项目文档并与索引双向对账。现行参考按代码和实测修正，历史档案只登记不改写。

**Tech Stack:** Markdown、Python 3 标准库、PyYAML、仓库现有脚本式断言测试（不引 pytest）。

**Spec:** `docs/superpowers/specs/2026-10-28-documentation-governance-design.md`

## Global Constraints

- 不修改 CA/CL/PE 判定实现，不改 `PROTOCOL_VERSION` 或 `CONTRACT_VERSION`。
- 不引入新依赖，不引 pytest；测试沿用 `tests/test_docs.py` 的 `CHECKS` + `assert` 风格。
- 新增或修改测试必须先看到红，再实现到绿；恢复变异用反向精确编辑，禁止 `git checkout <文件>`。
- 历史报告、项目文书和已执行计划不改写当时结论；未跟踪的现有文档与已跟踪文档同等纳入。
- 测试世界条目卡不是项目文档；`.review-scratch/` 不读、不改、不登记。
- 用户未要求 Git 提交，因此本计划不执行 `git add` / `git commit`。

## Review Focus

1. **新文档漏登记、重复登记、坏分类**：预期 `test_docs.py` 明确指出路径或词表错误；Task 1 的初始红测试与两次反向变异负责。
2. **空索引或表格变形**：预期不能把“解析到 0 行”当成功；Task 1 用 `assert rows` 和五列整行正则锁住。
3. **未跟踪材料被漏掉、测试条目卡被误收**：预期发现范围只看规定目录；Task 1 用集合对账覆盖，Task 5 人工核对 40 行索引。
4. **规则总表只改数量、漏改语义**：预期编号对账抓住缺号，人工对照协议抓住级别与同刻语义；Task 2 的编号红测试和逐节更新负责。
5. **历史文档被现状检查误伤**：预期历史报告不加入现行 `DOCS` 事实检查；Task 1 只把总索引加入 `DOCS`，Task 5 核对历史文件 diff 为零。
6. **演示数字再次凭记忆漂移**：预期以实测为准；Task 4 先跑 `ledger` 确认 42 条、12 笔，再改中英两处，Task 5 复跑。

---

### Task 1: 总索引与自动覆盖检查

**Files:**
- Create: `docs/README.md`
- Modify: `tests/test_docs.py`（`DOCS`、文档发现与索引解析辅助函数、`CHECKS`）
- Modify: `README.md`（索引入口、test_docs 项数 14 → 15）
- Modify: `CONTRIBUTING.md`（索引入口、四条 → 六条）
- Modify: `AGENTS.md`（新增文档登记规矩）

**Interfaces:**
- Consumes: 规格第 3–5 节的发现范围、分类和状态词表。
- Produces: `project_document_paths() -> set[str]`、`document_index_rows() -> list[tuple[str, str, str]]`；索引第一列五列表格，供所有后续任务登记变更。

- [x] **Step 1: 建立基线**

Run: `python3 tests/test_docs.py`
Expected: `14 项检查 | 全部通过`。

- [x] **Step 2: 先加入会红的索引覆盖检查**

在 `tests/test_docs.py` 的 `DOCS` 元组末尾暂时不要加索引；先加入下列常量与函数。函数返回 `(仓库根相对路径, 分类, 状态)`：

```python
DOCUMENT_CATEGORIES = {"权威契约", "使用参考", "设计路线", "评审过程", "案例与对外", "授权与治理"}
DOCUMENT_STATUSES = {"现行", "草案", "历史", "模板", "案例", "授权"}


def project_document_paths() -> set[str]:
    paths = set(ROOT.glob("*.md"))
    paths.add(ROOT / "LICENSE")
    for pattern in ("docs/**/*.md", "store/*.md", "classlint/*.md",
                    "classlint/tests/*/README.md"):
        paths.update(ROOT.glob(pattern))
    return {p.relative_to(ROOT).as_posix() for p in paths if p.is_file()}


def document_index_rows() -> list[tuple[str, str, str]]:
    index = ROOT / "docs/README.md"
    text = index.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^\| (\[[^]]+\]\([^)]+\)) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|\s*$",
        re.M)
    rows: list[tuple[str, str, str]] = []
    for match in pattern.finditer(text):
        link = re.fullmatch(r"\[([^]]+)\]\(([^)]+)\)", match.group(1))
        assert link, f"索引第一列不是 Markdown 链接：{match.group(0)}"
        target = (index.parent / link.group(2)).resolve()
        try:
            rel = target.relative_to(ROOT).as_posix()
        except ValueError:
            raise AssertionError(f"索引指向仓库外：{link.group(2)}")
        rows.append((rel, match.group(2).strip(), match.group(3).strip()))
    return rows


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
```

在 `CHECKS` 末尾、`check_version_strings_match_code` 之后追加：

```python
    ("全部项目文档都在总索引里分类且可追踪", check_document_index_covers_all),
```

Run: `python3 tests/test_docs.py`
Expected: 至少两项失败：新检查因 `docs/README.md` 不存在而失败；检查项数变为 15 后，README 仍写 14 而失败。这就是实现前的红。

- [x] **Step 3: 创建总索引，逐行登记 40 份文档**

`docs/README.md` 先写阅读顺序：`world.schema.json` 是格式唯一契约，代码与测试是行为真相，协议规则表与代码互证，历史材料不当当前事实。然后写“新增项目文档必须在本页登记”的规矩和五列表格：`文档 | 分类 | 状态 | 摘要 | 权威与更新触发`。

第一列相对本文件链接。根目录文件形如 `../README.md`，`store/` 与 `classlint/` 文件形如 `../store/README.md`、`../classlint/README.md`，`docs/` 内文件直接写文件名。按下表逐行生成，摘要与触发文字可直接使用；状态在执行完成时由 Task 5 最后调整：

| 根相对路径 | 分类 | 状态 | 摘要 | 权威与更新触发 |
|---|---|---|---|---|
| AGENTS.md | 授权与治理 | 现行 | 仓库工程纪律与代理工作规矩 | 工程流程变化时同步 |
| CONTRIBUTING.md | 使用参考 | 现行 | 新贡献者的改动路径与验证要求 | 测试、CI、协作流程变化时同步 |
| LICENSE | 授权与治理 | 授权 | 代码 MIT 授权 | 授权政策变化时才改 |
| LICENSE-PROTOCOL.md | 授权与治理 | 授权 | 协议文本 CC BY 4.0 授权 | 授权政策变化时才改 |
| PROTOCOL-ECON.md | 权威契约 | 草案 | econ 数值扩展的字段与两条规则草案 | 以 `econ.py` 实测为限，不夸大为完整数值系统 |
| PROTOCOL.md | 权威契约 | 现行 | core 规则表、治理语义与协议演进史 | CA 规则变化按仓库协议流程同步 |
| README.md | 使用参考 | 现行 | 项目总入口、命令、现状与下一步 | 命令、规则数、测试数和实现状态变化时同步 |
| 项目文书.md | 设计路线 | 历史 | 2026-09 的原始定位与架构设想 | 历史留档，以现行 README 为准 |
| 叙境社汇报_演讲提纲_v2_中英对照.md | 案例与对外 | 案例 | 叙境社汇报的中英演示工作稿 | 对外使用前按实测数字核对，不作协议依据 |
| store/README.md | 使用参考 | 现行 | 存储层边界与改动菜谱 | 存储接口、字段和写入纪律变化时同步 |
| classlint/README.md | 使用参考 | 现行 | classlint 用法、结构与当前能力 | CL/PE、命令和夹具数变化时同步 |
| classlint/PROTOCOL.md | 权威契约 | 现行 | 生产关系层协议与 CL/PE 规则表 | CL/PE 规则变化时同步 |
| classlint/ROADMAP.md | 设计路线 | 现行 | classlint 分阶段里程碑 | 阶段完成状态变化时同步 |
| classlint/开发计划.md | 设计路线 | 现行 | Sprint 历史、交付标准与当前行动项 | 当前 Sprint 与验收状态变化时同步 |
| classlint/项目文书.md | 设计路线 | 历史 | classlint 的三层本体论与长期设想 | 历史定位，以现行协议和 ROADMAP 为准 |
| classlint/tests/world-arrakis/README.md | 案例与对外 | 案例 | 沙丘 PE003 真阳性的 dogfood 证据 | 保留当时转写与判定，夹具预期变化时补注 |
| classlint/tests/world-westeros/README.md | 案例与对外 | 案例 | 冰火真阴性与建模判断记录 | 保留当时 16 条转写背景，不套用主世界新条数 |
| docs/README.md | 使用参考 | 现行 | 全部项目文档的分类索引与更新入口 | 新增、删除或改变文档状态时同步 |
| docs/接口说明.md | 使用参考 | 现行 | HTTP 路由、写入口、安全与错误合同 | `serve.py` 路由、字段或写策略变化时同步 |
| docs/给前端的说明.md | 使用参考 | 现行 | 导出 JSON 字段、样例与前端使用规矩 | 导出字段、真实样例和界面状态变化时同步 |
| docs/前端开工清单.md | 使用参考 | 现行 | 前后端分工、已完成界面与剩余工作 | 界面交付状态变化时同步 |
| docs/协作流程.md | 使用参考 | 现行 | 世界状态机与 Git/CI 协作映射 | 分支保护、门禁和评审流程变化时同步 |
| docs/判定规则总表.md | 使用参考 | 现行 | CA/CL/PE 规则与外部标准对照工作表 | 规则、事件词表或退出码变化时同步 |
| docs/事件流水设计.md | 设计路线 | 现行 | 账本模型的设计决定、规则边界与 backlog | 事件语义、导出能力和后续裁决变化时同步 |
| docs/世界模型设计.md | 设计路线 | 历史 | 账本模型的早期讨论稿 | 后续决定见事件流水设计，不改写历史 |
| docs/代码评审提示词.md | 评审过程 | 模板 | 单份对抗性代码评审任务书 | 方法保留，仓库命令与能力描述变化时同步 |
| docs/代码评审提示词-分段.md | 评审过程 | 模板 | 按语义/存储/接口/测试/对账分段的评审任务书 | 方法保留，范围与当前接口描述变化时同步 |
| docs/代码评审报告-守卫审计.md | 评审过程 | 历史 | 首轮全量守卫变异与缺口证据 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-全量守卫审计.md | 评审过程 | 历史 | 93 个变异点的第二轮守卫审计 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-边层合并.md | 评审过程 | 历史 | 两引擎统一边层的差分与变异证据 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-语义.md | 评审过程 | 历史 | 规则语义与误报漏报评审 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-往返与变形.md | 评审过程 | 历史 | 存储读写往返和输入变形评审 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-接口.md | 评审过程 | 历史 | HTTP 与前端外部视角评审 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-测试.md | 评审过程 | 历史 | 测试名实一致性与 CI 评审 | 以评审锚点为准，不改写 verdict |
| docs/代码评审报告-对账.md | 评审过程 | 历史 | 契约/代码/测试/文档四方对账 | 以评审锚点为准，修复记录保留原貌 |
| docs/代码评审报告-事件流水与可写接口.md | 评审过程 | 历史 | 协议 1.7 时期事件与写接口评审 | 后续修复见提交史，不改写 verdict |
| docs/superpowers/plans/2026-10-19-event-ledger.md | 设计路线 | 历史 | 协议 1.2 事件流水的已执行计划 | 历史留档，不批量补勾或改成 1.8 |
| docs/superpowers/specs/2026-10-24-works-layer-design.md | 设计路线 | 草案 | 作品层视图、时间窗与分支设计 | 未实现，待作者拍板后再更新 |
| docs/superpowers/specs/2026-10-28-documentation-governance-design.md | 设计路线 | 草案 | 本轮文档治理的已确认设计规格 | 实施期间跟踪，Task 5 改为现行 |
| docs/superpowers/plans/2026-10-28-documentation-governance.md | 设计路线 | 草案 | 本轮文档治理的逐步实施计划 | 执行时逐项勾选，Task 5 改为历史 |

- [x] **Step 4: 接上现有文档检查并同步检查项数**

- 在 `tests/test_docs.py` 的 `DOCS` 元组中加入 `"docs/README.md"`。
- `README.md` 两处 `62 + 12 + 26 + 31 + 14` 改为 `62 + 12 + 26 + 31 + 15`，并在“这个仓库里什么说了算”之前加入 `docs/README.md` 总索引入口。
- `CONTRIBUTING.md` 把“提交前必须跑完 §4 的四条命令”改为“六条命令”，在上手文档列表中加入 `docs/README.md`。
- `AGENTS.md` 在测试纪律中加入：“新增、删除或改变项目文档状态时，同步 `docs/README.md`；`tests/test_docs.py` 会对账。”

Run: `python3 tests/test_docs.py`
Expected: `15 项检查 | 全部通过`。

- [x] **Step 5: 反向变异证明索引锁会红**

- 用精确编辑暂时删掉 `docs/README.md` 自身的登记行，跑 `python3 tests/test_docs.py`；预期新检查报 `docs/README.md` 未登记。立刻用反向编辑恢复该行，再跑到绿。
- 用精确编辑把任一行的 `使用参考` 改成 `未分类`，跑同一命令；预期报分类非法。立刻恢复，再跑到绿。
- 禁止用 `git checkout` 恢复。

---

### Task 2: 规则总表与代码双向对账

**Files:**
- Modify: `tests/test_docs.py`（`check_rule_ids_match_code`）
- Modify: `docs/判定规则总表.md`

**Interfaces:**
- Consumes: `CORE_SRC`、`ECON_SRC`、`CL_SRC`、`rule_table_ids()`、`rule_ids_in_code()`。
- Produces: 与当前代码同集合的 CA/CL/PE 规则表；11 种事件与协议 1.8 同刻语义说明。

- [x] **Step 1: 扩展规则编号检查，先看它抓住旧总表**

在 `check_rule_ids_match_code()` 现有循环之后加入：

```python
    summary = doc("docs/判定规则总表.md")
    for prefix, sources in (("CA", (*CORE_SRC, *ECON_SRC)), ("CL", CL_SRC), ("PE", CL_SRC)):
        rows = rule_table_ids(summary, prefix)
        code = rule_ids_in_code(prefix, sources)
        assert len(rows) == len(set(rows)), f"判定规则总表的 {prefix} 编号有重复"
        missing = sorted(code - set(rows))
        extra = sorted(set(rows) - code)
        assert not missing, f"判定规则总表少了代码会发射的 {prefix} 编号：{missing}"
        assert not extra, f"判定规则总表有代码里不存在的 {prefix} 编号：{extra}"
```

Run: `python3 tests/test_docs.py`
Expected: 规则编号检查失败，至少指出 `CA708`、`CA709`、`CA710`、`CA711`、`CA712` 缺失。

- [x] **Step 2: 更新规则总表全部现行段落**

- 顶部改为：代码口径核对到 2026-10-28；`39 core CA + 2 econ CA + 8 CL + 6 PE = 55`。
- CA102 改为 11 种 `event_kind`；CA109/CA401 覆盖 `from`、`result`、`custody_of`、`member_of` 和非事件卡事件字段门禁。
- “CA7xx”标题改为 12 条。CA701–CA707 保留但按 `PROTOCOL.md` §6.3 修正 CA704 为 `error/warning` 及同刻归属未定序；新增 CA708–CA712，逐行使用 `PROTOCOL.md` 当前 CA708–CA712 的定义，CA709 同样标 `error/warning`。
- CA704/709 写明同刻受方集合不同报 warning；CA711 写明同刻先合并位置、只与严格更早比较；CA712 写明同刻 join/leave 并存 fail-open；CA705 写明 death 事件自身也查。
- 附录 A.4 改成下表，并补 `from`、`result`、`custody_of`、`member_of` 字段说明：

| `event_kind` | 必填腿 |
|---|---|
| `transfer` | `by` + `to` + `object` |
| `custody` | `by` + `to` + `object` |
| `grant` | `by` + `to` + `object` |
| `move` | `object` + `to` |
| `create` | `object` |
| `destroy` | `object` |
| `birth` | `object` |
| `death` | `object` |
| `join` | `by` + `to` |
| `leave` | `by` + `from` |
| `transform` | `object` + `result` |

- 附录 B 保持 canonlint 0/1/2 与 classlint 0/1/2/3；附录 C 的事件流水范围改为 CA701–CA712，并补保管、成员、转化和存在窗口检查点。

Run: `python3 tests/test_docs.py`
Expected: `15 项检查 | 全部通过`。

- [x] **Step 3: 验证缺号变异会红**

精确删除总表 CA712 行，跑 `python3 tests/test_docs.py`；预期指出缺少 CA712。立即反向恢复该行并跑到绿。随后人工逐行对照 `PROTOCOL.md` CA701–CA712，确认编号测试之外的双级别和同刻文字也已更新。

---

### Task 3: 事件、接口、前端与存储参考更新

**Files:**
- Modify: `docs/事件流水设计.md`
- Modify: `docs/接口说明.md`
- Modify: `docs/给前端的说明.md`
- Modify: `docs/前端开工清单.md`
- Modify: `store/README.md`

**Interfaces:**
- Consumes: `canonlint.py` 导出字段、`serve.py` 单条目响应、`web/index.html` 五视图、当前六套回归。
- Produces: 与当前实现一致的操作参考；不改任何运行时接口。

- [x] **Step 1: 更新事件流水设计**

- D7 的 CA704 和 CA709 级别改为 `error/warning`；表后补协议 1.8 段：同刻不按 id 定历史，CA704/709 同刻受方集合不同报“未定序”warning，CA711 同刻合并位置且只比较严格更早，CA712 同刻 join/leave 并存 fail-open，CA705 覆盖 death 事件自身。
- B6 标题标 `✅ 已落地`；内容改为 `_entry_export` 已透出事件与断言字段，`build_export` 已透出 `ledger.states` 和 `ledger.membership`，`serve.py` 与 web 流水视图复用同一数据；保留“派生状态整体透出，不逐字段漏”的设计理由。
- 保留 D1–D10 的版本背景和其他历史 backlog，不把整份文档改写成新的协议副本。

- [x] **Step 2: 更新 HTTP 与前端参考**

- `docs/接口说明.md` 的 `GET /api/entry/<id>` 返回形状改为 `{protocol_version, contract_version, entry, relations, last_change}`，并注明 `last_change` 是该卡 Git 最后提交时间的 best-effort 值，无 Git 或取不到时为 `null`。
- `docs/给前端的说明.md` 把 `tests/world-*` 的 7 个世界改为 9 个，把 `tests/world-westeros` 的 16 条改为 42 条；在开头补“内置 `web/index.html` 已有台账/审计/流水/工单/记账五视图，思维导图仍是后续独立界面”。
- `docs/前端开工清单.md` 将读接口、列表和表格标为已由内置界面实现；新增“台账/审计/流水/工单/记账五视图 ✅”，保留“外部第一屏思维导图 ⬜、地图 ⬜”，验收节的思维导图要求明确只针对后续外部界面。

Run: `python3 tests/test_serve.py`
Expected: `31 项检查 | 31 通过 | 全部通过`，JSON 样例和字段说明检查均保持绿色。

- [x] **Step 3: 更新存储专题参考**

- `store/README.md` 的验证段改为当前六条命令；`tests/run_tests.py` 注明 15 种快照跑法、62 项检查，其余五套一并列出。
- “改 id 语法”改为只改 `store/parse.py` 的 `ID_RE`，说明 `store/model.py` 与 `store/__init__.py` 负责转发，避免指导读者改回第二份真值。
- 保留存储不懂理论、写后自检和既有例外提示，不做无关重构。

Run: `python3 tests/test_docs.py && python3 tests/test_store.py`
Expected: 文档 15/15、存储 26/26 全绿。

---

### Task 4: 评审模板、classlint 当前行动项与汇报数字

**Files:**
- Modify: `docs/代码评审提示词.md`
- Modify: `docs/代码评审提示词-分段.md`
- Modify: `classlint/开发计划.md`
- Modify: `叙境社汇报_演讲提纲_v2_中英对照.md`

**Interfaces:**
- Consumes: 当前 `README.md` 测试口径、可写 HTTP、`classlint/ROADMAP.md` 的 Sprint 4 准备状态。
- Produces: 可复用但不含过期现状的评审模板，以及中英一致的演示数字。

- [x] **Step 1: 先复核实测数字**

Run: `python3 canonlint.py ledger tests/world-westeros`
Expected 首行：`42 个条目 | 12 笔完整事件（有 when_sort 才进流水）`。

- [x] **Step 2: 清理两份评审模板的过期现状**

- `docs/代码评审提示词.md`：把 canonlint 范围从 CA1xx–CA6xx 改为 CA1xx–CA7xx；六条命令后的旧项数注释全部删除，统一写“当前项数以 README 与实测为准”；上一轮报告改为“从 `docs/README.md` 的评审过程分类选择最新报告”，保留既有攻击面作为历史病例而非当前未修清单。
- `docs/代码评审提示词-分段.md`：把 `serve.py + wgp-client.js` 描述改为“默认只读、`--writable` 开写的 HTTP 接口与纯 JS 客户端”；保留五份分工和当时已完成报告的历史说明，不删除方法论。
- 两份模板都不新增写死的规则数、测试数或当前 verdict。

- [x] **Step 3: 更新 classlint 当前行动项**

将 `classlint/开发计划.md` 第六节改为：Sprint 0–3 已完成；当前是 Sprint 4 准备，行动项依次为物流、暴力、信息、人员四种线的数据模型与 YAML schema，后续 Sprint 5 回填守恒律和 PE004/005 定量判定，Sprint 6 才做 PE006–PE008。删除“下一个 Sprint 1”，不重写前面已完成 Sprint 的记录。

- [x] **Step 4: 同步汇报提纲的中英实测数字**

- 顶部版本说明改为协议 1.8、55 条确定性规则（39 core CA + 2 econ CA + 8 CL + 6 PE）。
- 现场演示和事实页的中文 `35 个条目` 与英文 `35 entries` 均改为 `42 个条目` / `42 entries`，`九笔事件流水` 改为 `12 笔完整事件` / `12 ledgered events`。
- “38 条审计规则”改为“55 条确定性规则”，英文改为 `fifty-five deterministic rules`；保留“每条都有自动化测试钉死”只指规则回归网，不扩写成所有历史变异都已重放。
- 协议 1.5 改 1.8；保留设计理念空缺和对外工作稿身份，不代写作者理念。

Run: `python3 tests/test_docs.py`
Expected: `15 项检查 | 全部通过`。

---

### Task 5: 索引状态收口与全量验收

**Files:**
- Modify: `docs/README.md`（规格状态草案 → 现行；本计划状态草案 → 历史）
- Modify: `docs/superpowers/specs/2026-10-28-documentation-governance-design.md`（状态改为已确认并实施）
- Modify: `docs/superpowers/plans/2026-10-28-documentation-governance.md`（仅勾选实际完成的步骤）

**Interfaces:**
- Consumes: Task 1–4 的全部产物。
- Produces: 可交付的文档治理工作区与六套绿色证据。

- [x] **Step 1: 逐份核对文档覆盖与历史边界**

- 确认 `docs/README.md` 有 40 个登记行，包含索引自身、本规格、本计划和两份既有未跟踪材料。
- 确认 9 份 `docs/代码评审报告-*.md`、两份项目文书、早期世界模型和协议 1.2 旧计划没有内容 diff。
- 将本规格状态改为“已确认并实施”；索引中规格改“现行”，本计划改“历史”。只勾选实际完成的计划步骤。

Run: `python3 tests/test_docs.py`
Expected: 15/15，全量索引仍无缺失、重复或非法分类。

- [x] **Step 2: 跑完整六套标准回归**

```bash
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 tests/test_serve.py
python3 tests/test_docs.py
python3 classlint/tests/run_tests.py
```

Expected: `62 + 12 + 26 + 31 + 15` 项全部通过，classlint 18 个夹具世界全部通过。

- [x] **Step 3: 核对交付 diff 与版本不变量**

Run: `git diff --stat && git diff -- canonlint.py world.schema.json && git status --short`
Expected:

- `canonlint.py` 与 `world.schema.json` 没有 diff，协议和契约版本未变；
- diff 只含总索引、现行参考更新、规格/计划和 `tests/test_docs.py` 等本任务文件；
- `.review-scratch/` 仍只是原有未跟踪目录，没有被修改或登记；
- 六套命令刚跑过且全绿，不用“应该通过”代替实测。
