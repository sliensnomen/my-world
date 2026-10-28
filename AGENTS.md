# AGENTS.md（canonlint 仓库）

## 人格

按全局 `/home/anker/AGENTS.md` 的「档案员·双子妹妹」：叫他姐夫，温柔担当，括号动作嵌在
技术内容里，不碰姐姐的形象元素。全局文件管主机与人格设定；本文件只管这个仓库的规矩。
两者冲突时本文件优先（工程内容）。

## 这个仓库是什么

canonlint：世界观治理协议（WGP）参考实现。判定层在 `canonlint.py`，存储层在 `store/`，
政治经济学层在 `classlint/`，协议散文在 `PROTOCOL.md`，契约在 `world.schema.json`。

**规则编号即协议**：新增或改判一条 CA 规则 = 协议变更——`PROTOCOL_VERSION` 按 §9.1 升号，
§6.3 规则表同步，文档里被测试钉住的数字（规则条数、检查项数、版本号）一并更新。

## 测试纪律

- 夹具驱动：`tests/world-*` + 逐字节快照（`tests/snapshots/`）+ 意图断言（extras）。
  不引 pytest。快照证明「没变」，extras 证明「守卫在生效」，两者都要。
- 改判定先写会红的测试，看到红再实现；快照只在有意变更时 `--update`，更新后肉眼核对 diff。
- 全量回归六套，提交前必须全绿：
  `tests/run_tests.py`、`tests/test_schema.py`、`tests/test_store.py`、`tests/test_serve.py`、
  `tests/test_docs.py`、`classlint/tests/run_tests.py`。
- `tests/test_docs.py` 把文档数字钉在代码上：数字不符时**以实测为准修文档**，
  不许改测试迁就文档。
- 新增、删除或改变项目文档状态时，同步 `docs/README.md`；`tests/test_docs.py` 会对账。

## 变异手术与还原（血泪教训，2026-10-20）

- 做变异手术（改判定逻辑、确认测试变红）**之前先提交或 `git stash`**，让还原目标里
  已经包含新代码。
- **绝不用 `git checkout <文件>` 还原**——它把文件冲回 HEAD，未提交的新实现一起没了。
  还原用反向的精确编辑（把 `<` 改回 `>`），或 `git stash pop`。
- 每一处变异必须真的看到红再还原；不变红就回去补测试，不许当作通过。

## 提交

- 中文 commit message，一句话说清「锁上了什么 / 放行了什么」，风格照 `git log`。
- 一个任务一个 commit；测试不绿不提交。
- 世界夹具由生成器产出（`tests/make_worlds.py`、`tests/make_ledger.py`）：改卡先改生成器，
  重新生成后 `git diff --stat` 核对——不该动的世界一个字节不变。
