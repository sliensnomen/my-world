# 参与贡献

这份文件有**两个读者**：人，和人的 AI 助手。目标只有一个——
任何人（或任何 AI）都能在 30 分钟内弄清「**改哪里、怎么证明没弄坏别的**」。

---

## 0. 给 AI 助手的一段话（可整段粘贴）

> 你在给 `my-world` 仓库（世界存储 + 确定性判定的工具集）改代码。先按顺序读这几份：
>
> 1. `README.md` —— 30 秒知道这是什么、命令有哪些
> 2. `world.schema.json` —— 条目格式的唯一契约（自定义字段一律 `x-` 前缀，不要另开 `extensions` 键）
> 3. `store/README.md` —— 存储层边界、常见改动菜谱
> 4. 你要改的那一层（见 §1 的表）
>
> **铁律（越线会被测试抓住）**
>
> - **存储不认识理论**：`store/` 里不许出现层级、`kind` 语义、承重墙、PE 规则等理论词汇。
>   判定只读存储暴露的接口（`Entry.meta` / `Entry.deps` / `Entry.relations`），不许自己去读文件。
> - **不许为了让改动通过而修改测试期望值**：`tests/snapshots/` 是逐字节回归网。如果你认为期望值本身错了，
>   在 PR 里单独说明，并把「改期望值」做成一个独立提交。
> - **自定义字段必须 `x-` 前缀；引用只认 id，不认文件路径。**
> - **不要改 CI 里的检查名**（`canonlint (3.12)` 等四个名字被分支保护依赖）。
> - **提交前必须跑完 §4 的四条命令**，并把输出摘要写进 PR 描述。

---

## 1. 这个仓库是什么

| 层 | 代码在哪 | 改它需要懂什么 | 谁守着它 |
|---|---|---|---|
| **存储** | `store/`（model / layout / write） | 只要懂文件格式 | `tests/test_store.py`（AST 检查，越线即红） |
| **格式契约** | `world.schema.json` | 只要懂 JSON Schema | `tests/test_schema.py` |
| **结构判定** | `canonlint.py` 的 `check_*` 与规则常量 | 要懂规则语义（`PROTOCOL.md` §6.3） | `tests/run_tests.py`（快照）+ `tests/test_docs.py` |
| **政治经济学判定** | `classlint/classlint.py`（CL1xx + PE001–PE005） | 要读 `classlint/PROTOCOL.md` | `classlint/tests/run_tests.py`（15 个夹具） |
| **回归网** | `tests/`、`classlint/tests/` | —— | CI（四个检查） |
| **文档** | `README.md`、`CONTRIBUTING.md`、`PROTOCOL.md`、`docs/` | —— | `tests/test_docs.py`（数字必须与代码一致） |

一句话总结这个项目的赌注：同类工具（SillyTavern 的世界书、World Anvil）能**存**能**展示**，
但都不能**判定**。我们做的只有判定这一件事。

---

## 2. 30 分钟做完第一处改动

```bash
pip install pyyaml
git clone https://github.com/sliensnomen/my-world && cd my-world
git switch -c fix/your-topic

# ① 建立基线：四条命令都该绿
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 classlint/tests/run_tests.py
```

② 挑改动（菜谱见下）→ ③ 改 → ④ 重跑那四条 → ⑤ 提交 → ⑥ 开 PR（见 §5）。

### 菜谱 A：加一个字段

见 `store/README.md` 的「常见改动 · 加一个字段」。要点：**存储层加字段表 + 契约加属性 +
需要严格检查时才动规则**，三处都要动，`tests/test_schema.py` 会在两张表不一致时报红。

### 菜谱 B：加一个关系别名（把 `owns` 这类具名字段接上）

同样的位置：`store/model.py` 的 `LEGACY_RELATION_FIELDS` + `FIELD_TABLE` + `Entry.relations` 归一化。
注意**这一步是行为变更**（CA106 不再报这个词），要在 PR 里解释。
六个别名今天正是被刻意留着的收口点，见 `store/README.md` 末尾的「已知漂移」。

### 菜谱 C：改一条规则（加规则 / 改判定 / 改文案）

1. `canonlint.py` 的 `check_structure` / `check_content` / `check_refs` / `check_chain` / `check_duplicates`
   里改判定；
2. **同步 `PROTOCOL.md` §6.3 的规则表**（那是 23 条规则的清单，`tests/test_docs.py` 要求两边条数与编号一致）；
3. **加一个夹具**：在 `tests/world-*` 里造出会/不会触发它的条目，跑 `python3 tests/run_tests.py --update`
   更新快照，然后 **`git diff tests/snapshots/` 逐行看**——快照的 diff 就是这次行为变更的说明书；
4. 如果是新规则编号，记得在 `PROTOCOL.md` §6.1 的编号段里给它一个位置。

> `--update` 是给**有意的**行为变更用的。快照里出现你没解释的 diff，就是 bug。

---

## 3. 会被测试抓住的几条线

1. `store/` 里出现理论词汇 → `tests/test_store.py` 红；
2. 契约（`world.schema.json`）与代码字段表/词表不一致 → `tests/test_schema.py` 红；
3. 改了行为却没更新快照 → `tests/run_tests.py` 红（逐字节比对）；
4. 解析层遇到坏输入抛异常（而不是报 CA100/CL100）→ `tests/run_tests.py` 红（stderr 非空即失败）；
5. 文档里的数字（规则条数 / 层数 / 测试世界数量 / PE 编号）与代码不符 → `tests/test_docs.py` 红；
6. classlint 的期望值三元组变化 → `classlint/tests/run_tests.py` 红。

---

## 4. 验证命令（改完必须跑）

```bash
python3 tests/run_tests.py            # 9 个世界夹具 + 17 项检查，逐字节比对快照
python3 tests/test_schema.py          # 契约 ↔ 代码常量
python3 tests/test_store.py           # 存储层边界与写入路径
python3 tests/test_docs.py            # 文档里的数字 ↔ 代码
python3 classlint/tests/run_tests.py  # 15 个 classlint 夹具
```

两个 Python 版本都要过（CI 跑 3.12 与 3.14；本机可用
`~/.pyenv/versions/3.12.10/bin/python3` 交叉验证）。

---

## 5. CI 会跑什么

`.github/workflows/canonlint.yml`：`pull_request` 与 `push: main` 触发，两个 job × 两个 Python 版本：

| 检查名（分支保护依赖） | 跑什么 |
|---|---|
| `canonlint (3.12)` / `canonlint (3.14)` | `tests/run_tests.py` → `tests/test_schema.py` → `tests/test_store.py` → `tests/test_docs.py` |
| `classlint (3.12)` / `classlint (3.14)` | `classlint/tests/run_tests.py` |

**CI 不审计这个仓库本身**（为什么：本仓库没有 `entries/` 之类的入口目录，`canonlint . --strict`
会退化成扫描全仓库、把测试夹具当成世界——744 个假错误。审计对象是「世界数据」，不是「工具源码」）。

## 6. PR 流程

- **main 受保护**：只能走 PR；四个检查必须绿；分支必须先同步到最新 main。
- **合并方式**：`Merge`（不用 squash/rebase——保留每个提交作为可整体回滚的单元）。
- **CODEOWNERS** 目前只有仓库所有者 `@sliensnomen`。**「Require review from Code Owners」是刻意关着的**：
  GitHub 不允许自己 approve 自己的 PR，开了等于把自己的 PR 锁死。等有第二位 code owner 再开。
- 细节（状态机 ↔ git 操作的映射、世界数据仓库该保护什么）见 [docs/协作流程.md](docs/协作流程.md)。

## 7. 硬规矩

1. **引用只认 id**，不认文件路径（理由：文件能改名，id 不能）。
2. **自定义字段一律 `x-` 前缀**；不带前缀的未知字段会被 CA106 拒绝。
3. **AI 产出永不进 canon 状态**：用 AI 写了条目或正文，`ai_assisted: true` 必须标，且永久保留。
4. **AI 判定永不进退出码**：机器判定必须可复现；AI 只递建议条子（`report` 级别不进退出码）。
5. **判定一致性**：同一份数据，任何实现跑出来的确定性判定必须逐条一致。不一致时要么是实现有 bug，
   要么是契约有歧义——两者都得修，不许绕。
6. **不要删既有文件**：要改就就地改，要废弃就写清楚「已废弃，见 X」。git log 是唯一的历史。

## 8. 提 issue 时

说清楚：跑了什么命令、期望什么、实际什么、用的哪个测试世界（`tests/world-*` 里挑一个最接近的）。
有 `--json` 输出就贴上。误报/漏报是目前最有价值的贡献。

## 授权

代码 MIT，协议文本 CC BY 4.0。提交即表示你同意你的贡献按此授权发布。
