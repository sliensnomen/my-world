# 参与贡献

感谢你愿意看这个仓库。这份文件告诉你怎么参与，尽量不废话。

## 这个仓库有什么

- **canonlint**：世界观治理协议（WGP）的参考实现，用确定性规则给虚构世界「查设定 bug」
- **classlint/**：马克思主义政治经济学审计工具（从 canonlint 抽出架构，详见下文「是什么关系」）
- **tests/**：测试世界（world-bad 是故意写错的全规则夹具；world-clean 是全绿基准；魔戒/冰火/沙丘是真实 dogfood 数据）

## canonlint 和 classlint 是什么关系

精确的区分只有一个轴：**canonlint 是治理平台，classlint 是审计工具。** classlint 的协议原文写得很清楚：它继承 WGP 的条目格式和 lint 架构，但**不引入 WGP 的治理层**（canon 状态机、矛盾标注、评审程序）。

| | canonlint（WGP） | classlint |
|---|---|---|
| 回答的问题 | 「这个世界里什么算数？」——什么算正式设定、谁能改、降级了下游怎么办 | 「这个世界讲得通吗？」——谁在抽取谁、合法性怎么闭环、有没有隐形剥削 |
| 核心机制 | canon 状态机（draft→trial→canon→archived）+ 评审程序 + CA 规则 | 七种生产关系（owns/controls/extracts/coerces/legitimizes/owes/depends_on）+ PE 规则 |
| 七层链的角色 | 只是「结构完整性」检查的一条边（CA501–CA505） | 被放大成整个主体：PE001–PE008 全是政治经济学规则 |
| 规则谁说了算 | 协议冻结（v1.0.1），CA 规则不可关，判定权在评审组 | 作者自己的工具：PE 规则在 `classlint.yaml` 里**可以关，不能改定义** |
| `depends_on` 的 kind | 六值封版（治理需要统一口径） | 降为自由词汇（审计只关心边的存在和方向） |

所以血缘关系是：**classlint 是 canonlint 的一个切面放大**——把 WGP 里只当结构约束用的政治经济学部分抽出来做成主体，同时把治理层整个扔掉。共用的东西很具体：frontmatter 条目格式、id 引用规范（不认路径）、「Git + Markdown 是唯一事实来源」、`--impact` 影响报告（直接参考 CA504）。

改代码时注意：**改 `canonlint.py` 不影响 classlint，但反过来要小心**——classlint 里留着从 canonlint 复制来的解析代码（`parse_entry` / `Entry`），修解析 bug 时想想两边要不要同步修。

## 快速上手

```bash
pip install pyyaml
python3 canonlint.py tests/world-bad      # 故意写错的世界，应该报一堆 error
python3 canonlint.py tests/world-clean    # 全绿，应该一条 error 都没有
python3 canonlint.py . --strict           # CI 同款门禁模式
```

改完代码后，这两个测试世界的输出必须和原来一致（除非你的改动本身就是修 bug）。

## 怎么贡献

**不用写代码的：**

- 拿一个你熟悉的世界（小说、游戏、自己的 OC 都行）写成测试世界条目，跑一遍 canonlint，把误报/漏报截图提 issue——这是目前最有价值的贡献
- 报告协议看不懂的地方：PROTOCOL.md 是给人读的，读不懂就是文档的 bug
- 发现 canonlint 报的错和 PROTOCOL.md 规则表对不上，直接提 issue（两者必须逐条互证）

**写代码的：**

- 改 `canonlint.py` 或 `classlint/classlint.py`：开分支 → PR，CI 会跑 `canonlint --strict`
- 新增确定性规则：必须先改 `PROTOCOL.md` 的规则表（规则是协议的一部分，代码只是实现）
- 改了协议条款：PR 里必须有动机、对现有仓库的迁移成本、参考实现的对应 diff——三者缺一不收

## 几条硬规矩

1. **协议已冻结（v1.0.1）**：结构性变更走 major 版本流程，不是想改就改
2. **AI 产出永不进 canon 状态**：如果你用 AI 写了条目或正文，`ai_assisted: true` 必须标，且永久保留。AI 辅助 + 你自己实质性重写并署名，可以正常参与
3. **判定一致性**：同一仓库快照，任何实现跑出来的确定性判定必须逐条一致。你的实现和参考实现判定不一样时，要么是你有 bug，要么是协议有歧义——两者都得修，不许绕
4. **加字段必须用 `x-` 前缀**：不带前缀的自定义字段会被 CA106 拒绝
5. **引用只认 id**：永远用 id 不用文件路径（理由见 PROTOCOL.md §2.3）

## 提 issue 时

说清楚：跑了什么命令、期望什么、实际什么、用的哪个测试世界。有 `--json` 输出就贴上。

## 授权

代码 MIT，协议文本 CC BY 4.0。提交即表示你同意你的贡献按此授权发布。
