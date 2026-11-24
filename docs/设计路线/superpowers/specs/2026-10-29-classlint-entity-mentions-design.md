# classlint 正文别名识别设计

> 状态：已确认并实施。2026-10-29。
> 一句话：把 `codex/entities.yaml` 中的别名确定性映射到稳定 id，并在 `check --json` 的每个条目里报告正文提及。

## 1. 背景与目标

`classlint init` 已生成 `codex/entities.yaml`，`classlint/README.md` 也称别名解析已实现，
但当前代码没有任何读取方。与此同时，CL/PE 判定只读 frontmatter 关系，不需要、也不应因
正文识别而改变。

本轮目标是兑现“正文中的别名注册到稳定 ID”的承诺，并顺手修复三处已确认的文档漂移：
作品层草案契约号、汇报材料协议号，以及别名实现状态。成功标准是：作者可以通过现有 JSON
输出确定每篇正文提到了哪些注册实体、用了哪个别名、出现几次；坏注册表得到明确配置错误；
六套标准回归全绿。

## 2. 已确认的范围

- 只扫描 Markdown 正文，不扫描 frontmatter，不改写原文；
- 不让别名进入关系目标，不改变 CL/PE 规则、退出码中的 error/warning 数量或关系图；
- 识别结果只加入 `classlint check <世界> --json`，文本输出保持不变；
- 使用确定性字面匹配，不引入 NLP、AI、依赖或模糊猜测；
- 缺少 `codex/entities.yaml`、注册表为空或正文没有匹配时，输出空 `mentions` 列表，旧世界兼容。

本轮不实现别名在 frontmatter 中的归一，不新增 `mentions` 命令，不把提及加入 `graph`，
不为正文提及新增 CL 规则。

## 3. 注册表形状与配置错误

沿用初始化模板：

```yaml
entities:
  gray-harbor:
    aliases: [灰港, 灰港城]
```

每个稳定 id 必须满足现有 id 语法，并且存在于 `run_checks()` 返回的条目索引中。
`aliases` 必须是列表，每项必须是非空字符串。识别只针对这些别名；稳定 id 自身和条目标题
不会被隐式当成别名。

以下情况走现有 `ConfigError` 路径，`cmd_check` 返回 2：

- YAML 无法解析，顶层不是映射，或 `entities` 不是映射；
- 某个实体记录不是映射，或 `aliases` 不是列表；
- 别名为空、不是字符串，或同一别名重复注册（包括重复在同一稳定 id 下）；
- 稳定 id 语法非法，或没有对应的实际条目卡。

错误信息指出 `codex/entities.yaml` 和具体实体或别名。实体记录中的其他键不读、不限制，
避免给未来扩展制造无谓障碍。

## 4. 匹配语义

- 匹配区分大小写，扫描正文全部文本，包括代码块；这是字面报告，不尝试理解 Markdown 语义；
- 所有别名按长度从长到短竞争同一位置，匹配后不重叠继续扫描；
- 中文及其他非 ASCII 别名按字面匹配；
- 以 ASCII 字母、数字或下划线开头/结尾的别名，在相应边界要求两侧不是 ASCII 字母、数字、
  下划线或连字符，避免 `harbor` 命中 `harbor-master`；
- 同一 `(entity, alias)` 多次出现合并计数；列表按首次出现位置、再按 entity/alias 排序，
  输出确定。

例如正文“灰港城先征税，灰港随后跟进，灰港城再次争议”产生：

```json
[
  {"entity": "gray-harbor", "alias": "灰港城", "count": 2},
  {"entity": "gray-harbor", "alias": "灰港", "count": 1}
]
```

## 5. 数据流与接口

新增两个纯判定辅助接口，放在现有 `classlint/classlint.py` 中，沿用单文件结构：

```python
def load_entity_aliases(root: Path, index: dict[str, Entry]) -> dict[str, str]:
    """返回 alias → stable id；坏注册表抛 ConfigError。"""

def body_mentions(body: str, aliases: dict[str, str]) -> list[dict]:
    """返回按首次出现排序的 {entity, alias, count}。"""
```

`run_checks()` 的签名、返回值和判定路径完全不变。`cmd_check` 在现有 `try` 块内取得
`(entries, index, findings, disabled)` 后调用 `load_entity_aliases()`，再在 JSON 序列化阶段
为每个可解析条目添加：

```json
{
  "id": "entry-id",
  "path": "codex/entry.md",
  "meta": {},
  "body_chars": 123,
  "mentions": [{"entity": "gray-harbor", "alias": "灰港", "count": 2}]
}
```

这是 JSON 的向后兼容增量字段；`classlint_version`、CL/PE 协议版本和 `graph` 输出不变。

## 6. 测试设计

在 `classlint/tests/run_tests.py` 增加意图检查，先看到红再实现：

1. 真实 `cmd_check(as_json=True)` 输出包含 `mentions`，重复别名计数正确；
2. 长短别名不重叠，英文词边界和连字符边界正确，中文别名可识别；
3. 缺少注册表、空注册表和无匹配正文都输出 `mentions: []`；
4. 有/无别名时，frontmatter 关系、findings 和 PE/CL 判定不变；
5. 未知稳定 id、重复别名、空别名、非列表 aliases、非映射实体记录和坏 YAML 都返回 2；
6. 文本输出不因提及增加内容，`graph --format json` 形状不变。

测试使用临时世界和真实函数/命令，不用 mock，不修改既有夹具世界。

## 7. 文档同步

- `classlint/classlint.py` 初始化模板删除“别名解析待实现”，改为说明 JSON `mentions`；
- `classlint/README.md` 保留别名实现承诺，并在 JSON 字段表写明 `mentions` 的形状与匹配口径；
- `classlint/PROTOCOL.md` §3.4 增加正文提及报告，明确它永不进退出码、不影响 CL/PE；
- `docs/superpowers/specs/2026-10-24-works-layer-design.md` 剩余契约 0.7 改 0.8，其他作品层
  语义不动；
- `叙境社汇报_演讲提纲_v2_中英对照.md` 的协议 1.8 改 1.9；设计理念仍标待作者补充，不代写；
- `docs/README.md` 登记本规格与实施计划，并在完成后更新状态。

## 8. 明确不做与验收

不做关系目标别名归一、自动正文改写、AI 实体识别、字符偏移输出、图视图或注册器架构。
不修改 B3 携带推导、作品层语义或判定器注册表。

完成后运行：

```bash
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 tests/test_serve.py
python3 tests/test_docs.py
python3 classlint/tests/run_tests.py
```

另用临时世界执行真实 `classlint check --json`，确认别名计数、空注册表兼容和配置错误退出码。
