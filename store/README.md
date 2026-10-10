# 存储层（store）

**一句话**：这里决定「世界在磁盘上长什么样」，不决定「这样写对不对」。

| 文件 | 管什么 |
|---|---|
| `store/model.py` | 条目模型、frontmatter 解析、字段表、id 语法、边的形状（`Relation`） |
| `store/layout.py` | 目录布局（`ENTRY_DIRS`/`SKIP_DIRS`/`TYPE_DIRS`）、扫描与 id 索引 |
| `store/write.py` | 写入命令：`init` / `new` / `link`（文本级插入，diff 小到能评审） |

规则不在这里。层级方向、承重墙、盲区、合法性闭环、关系讲不讲得通——那些在
`canonlint.py`（未来拆到 `rules/`）。**存储层不认识理论**：它不知道 `fiscal` 与
`manpower` 有什么区别，也不知道哪一层该养哪一层。

---

## 30 分钟上手

### 改完必须跑的命令

```sh
python3 tests/run_tests.py        # 九个世界夹具 + 17 项检查，输出与快照逐字节比对
python3 tests/test_schema.py      # 契约与代码常量不漂移
python3 tests/test_store.py       # 存储层边界（包括本文件的规矩）
```

`tests/run_tests.py` 里的快照（`tests/snapshots/`）是**逐字节**的：存储层重构不允许
改变任何一个世界的输出。快照要改，只能是因为**有意**改了行为，并且要在 PR 里说清为什么。

### 常见改动

**加一个字段**（比如 `x-wgp-source` 之外的正式字段 `canonical_url`）

1. `store/model.py`：加进 `CORE_REQUIRED_FIELDS`（必填）或 `ANNOTATION_FIELDS`（可选）。
2. `world.schema.json`：加进 `properties`；若属于严格档，同步 `x-strict-required`。
3. `canonlint.py`：若它也要被严格规则检查（比如词表），再把词表加进 `x-strict-vocabulary`
   并在 `check_structure` 里加判定。
4. 跑三个测试。`tests/test_schema.py` 会在两张表不一致时直接报红。

**加一个条目目录**（比如 `drafts/`）

`store/layout.py` 的 `ENTRY_DIRS` 加一项；若它不该被扫描，加进 `SKIP_DIRS`。
注意 `ENTRY_DIRS` 全都不存在时 `collect` 会退化成扫描**整棵树**（这是本仓库自己踩过的坑：
工具仓库里没有 `entries/`，于是 CI 把自己的测试夹具当成待审计的世界，报了 744 个不存在的错误）。

**加一个关系别名**（把 `owns` 之类变成可读的边）

1. `store/model.py`：加进 `LEGACY_RELATION_FIELDS` 与 `FIELD_TABLE`，并在
   `Entry.relations` 里归一化成 `Relation`。
2. 决定它是否进 `from store import ...` 的字段表——**这一步会让 CA106 不再报它**，
   属于行为变更，必须解释。
3. 判定器那边（`rules/`）决定它参不参与检查；存储层不判断关系名是否有意义，
   未知关系名**原样保留**。

**改 id 语法**

只改 `store/model.py` 的 `ID_RE`。它会同时影响解析（`depends_on[].id`）、
规则（CA105）和写入（`new --id`）——这是有意为之：id 语法是格式的一部分。

---

## 边界自检

一个改动该不该放这里，只问一句：**「不知道政治经济学的人，能不能独立判断它对不对？」**

- 能 → 放 `store/`。
- 不能 → 它属于判定器。

`tests/test_store.py` 把这条规矩变成了机器可查的东西：`store/` 的源码里不允许出现
理论词表（八层名、六种 `kind`、PE 规则号、政治经济学术语）。这条检查会失败，
说明有理论漏进了存储层。

唯一的例外是四条**已经发出去的老提示语**（`ALLOWED_SNIPPETS`，写在
`tests/test_store.py` 里）：`cmd_new` 的交互提示与错误提示、打印的连线示例
（`--kind fiscal`），以及 `cmd_link` 结尾那句「记得跑 canonlint 检查这条边是否合法
（层级方向/环/状态）」。改动它们等于改工具输出，所以留在原地；**新的理论措辞一律
不许住进 `store/`**——要表达理论，去判定层。

## 已知漂移（PR#3 收口）

契约的 `x-relation-source.aliases` 列了九个别名，本工具目前能读三种。其余六种
（`owns` / `controls` / `extracts` / `coerces` / `legitimizes` / `owes`）今天会被
CA106 报成「未定义字段」——它们在世界格式里合法，只是还没接上判定器。
`tests/test_store.py::check_relation_alias_drift` 把这个状态钉住了：收口那天，
那个测试会失败，提醒你把它一起改掉。
