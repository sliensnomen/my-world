# my-world · 世界的存储与检测

给写小说、剧本、跑团设定的人用的本地优先工具：**把世界存成 Git 里的 Markdown，再用确定性规则检测它在结构上讲不讲得通。**

同类工具里，SillyTavern 的世界书能**存**、World Anvil 能**展示**，但都不能**判定**——没有哪件工具会告诉你
「这个承重链条在政治经济学上不成立」。这个项目只赌这一件事。

## 两个工具，两层职责

| | 负责 | 现在有什么 |
|---|---|---|
| **存** | 条目格式、id、目录布局、关系、写入命令 | `store/` · `world.schema.json`（格式契约） |
| **判** | 结构规则 + 政治经济学规则 | 23 条 CA 规则（`canonlint.py`）· 6 条 CL + 5 条 PE 规则（`classlint/`） |

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
python3 canonlint.py ~/worlds/grey-harbor --pack econ        # 启用 econ 扩展包（CA601/CA602）

# ── 政治经济学层：classlint（条目住 codex/，目前是另一个仓库根）
python3 classlint/classlint.py init ~/worlds/grey-harbor-econ
python3 classlint/classlint.py check ~/worlds/grey-harbor-econ      # CL1xx + PE001–PE005
python3 classlint/classlint.py check ~/worlds/grey-harbor-econ --json
python3 classlint/classlint.py check ~/worlds/grey-harbor-econ --impact some-id   # 只读
python3 classlint/classlint.py graph ~/worlds/grey-harbor-econ --format dot       # 只读
```

退出码：`0` 通过 · `1` 有 error（`--strict` 时 warning 也算）· `2` 用法/环境错误（例如没装 pyyaml）。
`report` 级别的发现（CA504 影响报告、`graph`）**永不进退出码**。

> 两层现在读的目录不同：canonlint 读 `entries/`，classlint 读 `codex/`。
> 把两层合成一条管线（一个世界、两种判定器）还没做。

## 这个仓库里什么说了算

文档会过时，代码不会。按这个顺序信：

1. **`world.schema.json`** —— 条目格式的唯一契约。自定义与外来字段一律住 `x-` 前缀（例 `x-st-entry`）；
   不许另开 `extensions` 键——它不在字段表里，会被 CA106 当成未定义字段。
2. **代码 + 测试** —— 行为由 `tests/snapshots/` 与 `classlint/tests/` 钉死；测试绿就是真相。
3. **`PROTOCOL.md`** —— 2026-09 冻结时写下的规范散文：规则表（§6.3，23 条）与代码逐条互证，
   其余叙述是当时的意图。与代码不一致时**以代码为准**。
4. **`项目文书.md` / `classlint/项目文书.md`** —— 定位与路线图，属于「想法」，不是契约。

`tests/test_docs.py` 把文档里的数字（规则条数、层数、测试世界数量、PE 编号）钉在代码上：
改了代码不改文档，CI 会红。

## 现状（不吹）

- ✅ **能存**：init / new / link、frontmatter 格式、id 规则、`x-` 扩展、econ 扩展包
- ✅ **能判**：23 条 CA 规则（结构 / 引用 / 承重链条 / 重复 / 影响报告）+ CL1xx + PE001–PE005
- ✅ **有回归网**：`tests/` 三套（17 + 10 + 12 项检查）+ `classlint/tests/` 一套（15 个夹具世界），
  四个受保护检查在 Python 3.12 与 3.14 上跑（见 `.github/workflows/canonlint.yml`）
- ⬜ **没有界面** —— 前端最后做：没有判定，就没有值得渲染的东西；渲染器是别人能写的东西
- ⬜ **酒馆互操作没做** —— SillyTavern 世界书 / 角色卡的导入导出，是设计好的第一条真实入口（不用先写界面就有用户）
- ⬜ **classlint 还没按「存 / 判」拆** —— 它仍是 canonlint 的整份拷贝（`ENTRY_ROOT = "codex"`）
- ⚠️ 三个真实世界（魔戒 / 冰火 / 沙丘）是**演示**不是证据：它们的 warning 大多是真实世界的真实问题，
  不是工具 bug；拿它们当「全绿基准」是误会（唯一的全绿基准是 `tests/world-clean`）

## 下一步（方向已定，未实现）

1. **判定器注册表**：把 CA / PE 规则变成可插拔的包，缺注解就记 info 跳过，沿用 `econ.py` 的
   `KNOWN_FIELDS + check_entry(meta, rel, add)` 契约
2. **链与判定**：`chain --from <id> --to <id>` 选头选尾取一条链，`--judge ca|pe|ai` 选判定器
   （AI 判定器**永不进退出码、永不自动写入**）
3. **作品层**：世界 = 事实（只存一次），作品（小说 / 剧本 / 跑团）= 视图（带时间段与视角）
4. **酒馆适配器**：`adapters/st/` 读写世界书与角色卡 V2/V3，我们的关系图住 `x-` 命名空间

## 参与贡献

从 **[CONTRIBUTING.md](CONTRIBUTING.md)** 开始：里面有给 AI 助手的上下文段、30 分钟做完第一处改动的路径，
以及会被测试抓住的几条线。协作机制（PR / 分支保护 / CI）见 [docs/协作流程.md](docs/协作流程.md)。

授权：代码 [MIT](LICENSE)；协议文本 [CC BY 4.0](LICENSE-PROTOCOL.md)（实现不受限，引用需署名）。
