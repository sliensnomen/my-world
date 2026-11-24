# my-world · 世界的存储与检测

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sliensnomen/my-world)

> [DeepWiki](https://deepwiki.com/sliensnomen/my-world) 那份英文导读是**建站时刻的快照**，不会随提交自动更新；
> 与代码不一致时一律以本仓库为准，信的顺序见下文「这个仓库里什么说了算」。

> **项目正在转型**：本仓库正从「卡面世界 lint」（1.x）转向**文字世界模型**——以事件为唯一
> 事实源的叙事世界模型（协议 2.0 长分支，宪章见 [CHARTER.md](CHARTER.md)，L0 契约见
> `spine/event.schema.json`）。以下文档描述 1.x 卡面工具：已进入维护态（收 bug 修复与
> 协议小版本，不再长新规则），全文继续有效；转型方向、里程碑与迁移纪律以宪章为准。

给写小说、剧本、跑团设定的人用的本地优先工具：**把世界存成 Git 里的 Markdown，再用确定性规则检测它在结构上讲不讲得通。**

同类工具里，SillyTavern 的世界书能**存**、World Anvil 能**展示**，但都不能**判定**——没有哪件工具会告诉你
「这个承重链条在政治经济学上不成立」。这个项目只赌这一件事。

## 两个工具，两层职责

| | 负责 | 现在有什么 |
|---|---|---|
| **存** | 条目格式、id、目录布局、关系、写入命令 | `store/` · `world.schema.json`（格式契约） |
| **判** | 结构规则 + 政治经济学规则 | 47 条 CA 规则（`judges/` 的 `core-ca` 包，`canonlint.py` 驱动）· 11 条 CL + 16 条 PE 规则（`judges/` 的 `core-cl`/`pe` 包，`classlint/` 驱动；CL100–CL110，PE001–PE016） |

**两者之间有一条线**：`store/` 里不许出现政治经济学词汇。改存储的人不该被迫先学会八层链和 PE003——
政治经济学只住在规则、`classlint/` 和文档里。这条线由 `tests/test_store.py` 用 AST 检查守着（越线即红）。

## 命令

```bash
pip install pyyaml

# ── 结构层：canonlint（条目住 entries/）
python3 canonlint.py init ~/worlds/grey-harbor
python3 canonlint.py new  --root ~/worlds/grey-harbor location 灰港 --id grey-harbor
python3 canonlint.py new  --root ~/worlds/grey-harbor faction 王都 --id crown-capital
python3 canonlint.py link --root ~/worlds/grey-harbor grey-harbor crown-capital --kind fiscal --critical

python3 canonlint.py ~/worlds/grey-harbor                  # 审计：报告 + 退出码
python3 canonlint.py ~/worlds/grey-harbor --strict          # warning 也当失败
python3 canonlint.py ~/worlds/grey-harbor --json            # 机器可读
python3 canonlint.py ~/worlds/grey-harbor --impact crown-capital  # CA504：改它会波及谁（只读）
python3 canonlint.py ledger ~/worlds/grey-harbor            # 事件流水：派生状态（只读，不进退出码）
python3 canonlint.py event transfer --by anna --to bob --object sword-x --when "元年" --when-sort 1  # 一行记一笔流水
python3 canonlint.py ~/worlds/grey-harbor --pack econ        # 启用 econ 扩展包（CA601/CA602）

# ── 政治经济学层：classlint（条目住 codex/，目前是另一个仓库根）
python3 classlint/classlint.py init ~/worlds/grey-harbor-econ
python3 classlint/classlint.py check ~/worlds/grey-harbor-econ      # CL1xx + PE001–PE016
python3 classlint/classlint.py check ~/worlds/grey-harbor-econ --json
python3 classlint/classlint.py check ~/worlds/grey-harbor-econ --impact some-id   # 只读
python3 classlint/classlint.py graph ~/worlds/grey-harbor-econ --format dot       # 只读
python3 classlint/classlint.py view ~/worlds/grey-harbor-econ                       # 关系图 + 时间线（自包含 HTML）
python3 classlint/classlint.py fork ~/worlds/grey-harbor-econ alt-history           # 反事实推演（Git 分支）
```

```bash
# ── 出口：把世界数据交给前端（只读，不判定）
python3 canonlint.py export ~/worlds/grey-harbor --out world.json   # 导出数据集（合同见 docs/使用参考/接口说明.md）
python3 serve.py ~/worlds/grey-harbor --port 8000                   # 起接口：/api/world、/api/entry/<id> …
python3 serve.py ~/worlds/grey-harbor --port 8000 --writable        # 默认只读；加 --writable 才开三条写路由
# 前端读 /api/world 或 world.json；wgp-client.js 负责补默认值、给出思维导图要的形状
```

`serve.py` 默认只读，另有 `--writable`（开三条写路由）、`--token`（Bearer 凭据）、`--write-log`（JSONL 审计日志）、`--quiet`（不打每行请求日志）与 `--pack econ`（让 CA6xx 一起进 JSON，与 canonlint 侧同一面旗）。

判定器由 Registry 统一执行：`judges/` 提供统一的 Rule/Pack 元数据与加载入口，`core-ca`、`core-cl`、`pe` 负责核心规则，`econ` 仍由 `--pack econ` 显式启用。CLI 与 serve 共用同一 Pack 加载入口。旧判定后端（legacy）已按判定器注册表计划 Task 7 签核删除（2026-11-22）：Registry 自 2026-10-31 起默认运行一个发布周期、无应急回退、验收报告签核完毕，判定语义与本表相同。

退出码：canonlint `0` 通过 · `1` 有 error（`--strict` 时 warning 也算）· `2` 用法/环境错误（例如没装 pyyaml，或 `--dup-threshold` 不在 `(0, 1]` 内）。classlint 另有 `3`：PE 规则被 `rules: off` 关掉时，判定不是「全规则通过」，退出码 3；确认是有意关闭的，加 `--accept-disabled-rules` 才回到 0（见 `classlint/PROTOCOL.md` §4）。
三个开关的边界都钉在 `tests/run_tests.py` 里：`--strict` **只改退出码不改判定**（同一份数据两种模式的 findings 逐字相同）；`--dup-threshold` 越界是用法错误、且它真的是旋钮（放宽到 0.99 会消音 CA201）；`--impact` 给悬空主体出空下游、主体不进自己的下游、报告不影响退出码。
`report` 级别的发现（CA504 影响报告、`graph`）**永不进退出码**。

> 两层现在读的目录不同：canonlint 读 `entries/`，classlint 读 `codex/`。
> 判定器注册表统一了规则加载与后端选择，但「一个世界、两种判定器」的合并管线还没做。

全部项目文档的分类、时效状态和更新触发见 **[文档总索引](docs/README.md)**。

## 这个仓库里什么说了算

文档会过时，代码不会。按这个顺序信：

1. **`world.schema.json`** —— 条目格式的唯一契约。自定义与外来字段一律住 `x-` 前缀（例 `x-st-entry`）；
   不许另开 `extensions` 键——它不在字段表里，会被 CA106 当成未定义字段。
2. **代码 + 测试** —— 行为由 `tests/snapshots/` 与 `classlint/tests/` 钉死；测试绿就是真相。
3. **`PROTOCOL.md`** —— 2026-09 冻结时写下的规范散文：规则表（§6.3，47 条）与代码逐条互证，
   其余叙述是当时的意图。与代码不一致时**以代码为准**。
4. **`项目文书.md` / `classlint/项目文书.md`** —— 定位与路线图，属于「想法」，不是契约。

`tests/test_docs.py` 把**一部分**文档数字钉在代码上：`README.md` / `CONTRIBUTING.md` 里的规则条数与检查项数（47 条 CA、11 条 CL、16 条 PE、五套检查的 106 + 12 + 33 + 33 + 15），`README.md` / `CONTRIBUTING.md` / `classlint/README.md` 里的 31 个 classlint 夹具，以及 `PROTOCOL.md` §6.3 规则表的编号与条数。
它**不**是全文校验：层数、字段数、示例世界的条目数、退出码说明这些没被钉住，改代码时请顺手 `grep` 一遍文档。

## 现状（不吹）

- ✅ **能存**：init / new / link、frontmatter 格式、id 规则、`x-` 扩展、econ 扩展包
- ✅ **能判**：47 条 CA 规则（结构 / 引用 / 承重链条 / 事件流水 / 重复 / 影响报告）+ CL1xx + PE001–PE016
- ✅ **有回归网**：`tests/` 五套（106 + 12 + 33 + 33 + 15 项检查）+ `classlint/tests/` 一套（31 个夹具世界），

  四个受保护检查在 Python 3.12 与 3.14 上跑（见 `.github/workflows/canonlint.yml`）
- ✅ **判定器注册表**：`judges/` 用统一 Rule/Pack 元数据装载 CA/CL/PE/econ，Registry 是唯一判定后端（legacy 已于 2026-11-22 签核删除）；CLI 与 serve 共用同一 Pack 加载入口
- ✅ **界面 v0.2**：`web/index.html`（台账 / 审计 / 流水三视图 + 记账表单 + 升格/降级工单，零依赖零构建，`serve.py` 同源伺候）；默认只读，`--writable` 时界面才显示写入口
- ✅ **可写 HTTP 入口（Phase 2/3）**：`POST /api/entry`（写卡）、`POST /api/event`（记账）、`POST /api/status`（升格/降级）；写完即审、红则回滚，写请求串行化，只收同源 `application/json`；可选 `--token`  bearer 凭据与 `--write-log` 审计日志（见 `docs/使用参考/接口说明.md`）
- ⬜ **~~酒馆互操作~~** —— SillyTavern 世界书导入导出的旧规划，随转型冻结：「第一条真实入口」
  已改定为事件抽取基准（见 [CHARTER.md](CHARTER.md) §5），酒馆适配器是否以新形态复活由宪章修订记录决定
- ✅ **classlint 的判定包已拆出** —— `core-cl` 与 `pe` 经 Registry 执行，扫描/建索引与逐规则判定分离。读卡也只有 `store/parse.py` 一份（`tests/test_store.py` 的结构锁 + 行为锁守着）。classlint 仍是仓库内独立可执行文件，**必须和仓库一起用、从仓库根调用**，不能单独拷走 `classlint/classlint.py`；它自己的字段政策与 canonlint 有一处真实分歧（`depends_on` 收裸字符串，canonlint 要求 `{id, kind, critical}`）
- ⚠️ 三个真实世界（魔戒 / 冰火 / 沙丘）是**演示**不是证据：它们的 warning 几乎全是 CA104（正文不到
  200 字）这类篇幅噪声，不是工具 bug，也不是世界观有毛病；拿它们当「全绿基准」是误会
- ✅ **全绿基准是 `tests/world-clean`（结构）与 `tests/world-ledger`（流水）**：默认与 `--strict`
  两种模式下都是 `0 错误 | 0 警告`、`exit 0`，退出码逐字节钉在 `tests/snapshots/` 里
  （`world-clean`、`world-clean+strict`、`world-ledger`、`world-ledger+strict`）

## 下一步

1.x 进入维护态后，以下旧规划（链与判定 `chain --judge`、作品层、酒馆适配器、事件流水
后续 backlog）**不再展开**——它们曾是「卡面模型的下一步」，而项目的下一步已经换了：
向**文字世界模型**转型，路线与里程碑以 [CHARTER.md](CHARTER.md) 为准（当前第一个里程碑
是「抽取基准跑通」，见宪章 §5；这些旧规划里会以新形态复活的，由宪章的修订记录说了算）。
legacy 退役已完成（2026-11-22，见「现状」）。

## 参与贡献

从 **[CONTRIBUTING.md](CONTRIBUTING.md)** 开始：里面有给 AI 助手的上下文段、30 分钟做完第一处改动的路径，
以及会被测试抓住的几条线。协作机制（PR / 分支保护 / CI）见 [docs/使用参考/协作流程.md](docs/使用参考/协作流程.md)。

授权：代码 [MIT](LICENSE)；协议文本 [CC BY 4.0](LICENSE-PROTOCOL.md)（实现不受限，引用需署名）。
