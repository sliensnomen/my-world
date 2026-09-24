# classlint · 马克思主义政治经济学审计工具

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
作者写文本，工具建模型，模型展示结构，审计报出作者看不见的矛盾。

[项目文书](项目文书.md)（定位与三层架构） · [开发计划](开发计划.md) · [ROADMAP](ROADMAP.md)
姊妹项目：[WGP 世界观治理协议](../PROTOCOL.md) + [canonlint](../canonlint.py)（本工具的解析器与 lint 架构来源）

**状态：Sprint 0 基础层**——目前只有 `init` / `check`，PE 规则引擎从 Sprint 1 开始。

## 用法

```bash
pip install pyyaml
python3 classlint.py init my-world      # 初始化世界仓库
cd my-world
# ……在 codex/ 下写条目……
python3 ../classlint.py check .         # 读取全部条目，输出结构化数据
python3 ../classlint.py check . --json  # 机器可读输出
```

退出码：`0` 正常；`1` 条目存在错误；`2` 用法/环境错误。

## 审计规则（协议 v0.1，见 [PROTOCOL.md](PROTOCOL.md)）

- **CL1xx 结构规则**（不可关）：解析失败、缺必填字段、id 非法/重复、未定义字段、关系 schema 违规、关系目标不存在。
- **PE001** 抽取必须有基础（`controls`/`coerces`/`owns`）；**PE002** 不能镇压自己的供养者（critical 依赖 = error，否则 warning）；**PE003** 合法性不得无锚闭环（有外部锚点的互锁合法）。

PE 规则可在 `classlint.yaml` 关闭（`rules: {PE003: off}`）——可以关，不能改定义。

测试：`python3 tests/run_tests.py`（8 个夹具世界，正例/反例钉死期望判定）。

## 世界仓库结构

```
world/
├── classlint.yaml        # 项目配置（名称、工具版本、启用的规则包）
├── rules/                # 自定义规则（YAML，Sprint 2 起）
├── lore/                 # 世界背景、规则、声音指南
├── codex/                # 实体注册表——条目唯一位置
│   ├── entities.yaml     # 稳定 ID 与别名注册
│   ├── characters/
│   ├── locations/
│   └── factions/         # 目录纯组织，可自由增删子目录
├── stories/              # 叙事正文
├── timeline/             # 世界内历史
└── records/              # 派生输出
```

**条目 = `codex/` 下一个带 YAML frontmatter 的 Markdown 文件。**
文本是源头，模型是投影：Git + Markdown 是唯一事实来源。

## 实体 ID 规范（Sprint 0）

- 仅允许小写字母、数字、连字符（`^[a-z0-9-]+$`）；
- 全库唯一；一旦发布永不更改、永不复用；
- 正文中的别名通过 `codex/entities.yaml` 注册到稳定 ID（别名解析 Sprint 1 实现）。

## 核心原则

1. **Git + Markdown 是唯一事实来源。** 文本变，模型变。
2. **固定关系，实体开放。** 关系是语法，实体是词汇。
3. **三层咬合：** 流量层（数据）→ 生产关系层（结构）→ 个人关系层（语境修正）。
4. **AI 可选。** AI 是提取器、提问者、连接者，不是裁决者；产出永不自动入库。
