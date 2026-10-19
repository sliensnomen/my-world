# 存储层（store）

**一句话**：这里决定「世界在磁盘上长什么样」，不决定「这样写对不对」。

| 文件 | 管什么 |
|---|---|
| `store/parse.py` | **读卡代码的唯一一份**：id 语法、frontmatter 切分、契约词表、关系名归一化、`Relation`/`RawEntry` |
| `store/model.py` | 条目模型（`Entry`）、字段表、从 `RawEntry` 长成 `Entry`（挂上 `edges` 视图） |
| `store/layout.py` | 目录布局（`ENTRY_DIRS`/`SKIP_DIRS`/`TYPE_DIRS`）、扫描与 id 索引 |
| `store/write.py` | 写入命令：`init` / `new` / `link`（结构级最小改动 + 写完自检，见下） |

**读卡代码只有一份**（`store/parse.py`）。`canonlint.py` 与 `classlint/classlint.py` 都只
转发，谁都不许自己 `compile` 正则、自己切 frontmatter、或自己抄一份契约词表——
`tests/test_store.py` 里那条「两个引擎共用同一份读卡代码」用结构锁（AST 查抄写）
加行为锁（同一段字节喂给两个引擎，读出来必须一模一样）钉着它。
新增关系别名、改 id 语法、改 frontmatter 规则，都只改这一个文件。

**边层也只有一份**：`Entry.relations` / `relation_shape_errors` 在 `store/model.py`，
`classlint` 只把形状问题映射成自己的编号。唯一的差异开关是
`Entry.depends_on_requires_annotations`（契约 `x-stricter-than-contract` 第一条登记的口径：
canonlint 要求 `depends_on` 对象式且 `kind`/`critical` 给全，classlint 按自己的协议降为可选），
由 `tests/test_store.py` 的「两个引擎建同一张边图」钉着——例外只许是这一处。

规则不在这里。层级方向、承重墙、盲区、合法性闭环、关系讲不讲得通——那些在
`canonlint.py`（未来拆到 `rules/`）。**存储层不认识理论**：它不知道 `fiscal` 与
`manpower` 有什么区别，也不知道哪一层该养哪一层。

---

## 30 分钟上手

### 改完必须跑的命令

```sh
python3 tests/run_tests.py        # 10 个世界夹具 + 36 项检查，输出与快照逐字节比对
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

判定器**只读 `Entry.edges_of("关系名")`**（归一化视图），不再自己翻旧具名字段——
所以旧写法与规范形 `relations` 走同一条路，新增的别名只要归一化进 `Entry.relations`，
现有规则（CA401/402/403/404/405/501/502/503/504、CA108 kind）立刻就能看见它。

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

## 写卡的三条规矩（`store/write.py`）

1. **先看清结构再动**：`link` 不再用正则往 frontmatter 里塞三行——那会在「零缩进的块
   序列」「`depends_on:` 写成 null」「多行标量里出现 `depends_on:` 字样」这三种**合法**
   写法上写坏卡或写丢边，还照旧打印「已连线」。现在用 YAML 解析器给出键的位置，只插
   这一条边，其它字节（含注释、围栏、正文、行尾、BOM）不动。
2. **写完自检，不一致就退**：插入后重新解析、比对「旧结构 + 这一条边」。不一致 → 退回
   整块重排再验一次；还不一致 → **拒绝写盘**（退出码 2，磁盘上零改动）。重排会丢
   frontmatter 里的注释与键序，所以它是退路，输出里会说明走了哪条路。
3. **不动不属于自己的东西**：保留文件模式（临时文件是 0600，不能顶掉原来的 0644）、
   保留 CRLF/CR、顺着符号链接写真正的文件、只读文件直说拒绝、写前拒绝有重复键的文件
   （重复键会让前面的边静默消失，见 CA112）。

## 已知漂移

已收口：契约列的十一个关系字段全都读得进来、也都查悬空引用（CA401）；两个引擎的建边
与形状校验共用一份代码。**今天没有「读不进来」的别名了**，剩下的唯一分歧是上面那个
`depends_on` 口径开关（契约登记过）。再发现新漂移，写在这里并配一把锁。

契约的 `x-relation-source.aliases` 列的**十一个具名关系字段**（`canon_refs` / `conflicts_with` /
`depends_on` / `exchanges_with` / `derives_legitimacy_from` / `owns` / `controls` / `extracts` /
`coerces` / `legitimizes` / `owes`）今天**全部接线**：都能读进来，也都查悬空引用（CA401）。
只有**契约里没定义的扩展字段**才报 CA106——写一个不带 `x-` 前缀、契约也没登记的字段名，
那才是真错误；上面这十一个名字不会。
`tests/test_store.py::check_relation_alias_drift` 逐个真的解析每个别名，钉住这条接线：
以后谁把某个名字从字段表里摘掉，这个测试会变红。
