# 项目文档总索引

这份索引回答四个问题：每份项目文档是什么、能否当作当前事实、跟谁同步、什么时候必须更新。

## 先读什么

1. `world.schema.json` 是条目格式的唯一契约；代码与测试是行为真相。
2. `PROTOCOL.md` 与 `classlint/PROTOCOL.md` 的规则表和代码互证；散文与代码不一致时以代码为准。
3. 新读者从 `README.md`、`CONTRIBUTING.md` 和 `store/README.md` 进入实现。
4. “草案”尚未落地，“历史”只保留当时证据，“模板”是可复用流程，“案例”是特定场景材料。不要把它们当成现行契约。

新增、删除或改变项目文档状态时，必须同步本页。`tests/test_docs.py` 会发现漏登记、重复登记、失效链接和非法分类。

## 全量文档表

| 文档 | 分类 | 状态 | 摘要 | 权威与更新触发 |
|---|---|---|---|---|
| [AGENTS.md](../AGENTS.md) | 授权与治理 | 现行 | 仓库工程纪律与代理工作规矩 | 工程流程变化时同步 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 使用参考 | 现行 | 新贡献者的改动路径与验证要求 | 测试、CI、协作流程变化时同步 |
| [LICENSE](../LICENSE) | 授权与治理 | 授权 | 代码 MIT 授权 | 授权政策变化时才改 |
| [LICENSE-PROTOCOL.md](../LICENSE-PROTOCOL.md) | 授权与治理 | 授权 | 协议文本 CC BY 4.0 授权 | 授权政策变化时才改 |
| [PROTOCOL-ECON.md](../PROTOCOL-ECON.md) | 权威契约 | 草案 | econ 数值扩展的字段与两条规则草案 | 以 `econ.py` 实测为限，不夸大为完整数值系统 |
| [PROTOCOL.md](../PROTOCOL.md) | 权威契约 | 现行 | core 规则表、治理语义与协议演进史 | CA 规则变化按仓库协议流程同步 |
| [README.md](../README.md) | 使用参考 | 现行 | 项目总入口、命令、现状与下一步 | 命令、规则数、测试数和实现状态变化时同步 |
| [项目文书.md](../项目文书.md) | 设计路线 | 历史 | 2026-09 的原始定位与架构设想 | 历史留档，以现行 README 为准 |
| [叙境社汇报_演讲提纲_v2_中英对照.md](../叙境社汇报_演讲提纲_v2_中英对照.md) | 案例与对外 | 案例 | 叙境社汇报的中英演示工作稿 | 对外使用前按实测数字核对，不作协议依据 |
| [store/README.md](../store/README.md) | 使用参考 | 现行 | 存储层边界与改动菜谱 | 存储接口、字段和写入纪律变化时同步 |
| [classlint/README.md](../classlint/README.md) | 使用参考 | 现行 | classlint 用法、结构与当前能力 | CL/PE、命令和夹具数变化时同步 |
| [classlint/PROTOCOL.md](../classlint/PROTOCOL.md) | 权威契约 | 现行 | 生产关系层协议与 CL/PE 规则表 | CL/PE 规则变化时同步 |
| [classlint/ROADMAP.md](../classlint/ROADMAP.md) | 设计路线 | 现行 | classlint 分阶段里程碑 | 阶段完成状态变化时同步 |
| [classlint/开发计划.md](../classlint/开发计划.md) | 设计路线 | 现行 | Sprint 历史、交付标准与当前行动项 | 当前 Sprint 与验收状态变化时同步 |
| [classlint/项目文书.md](../classlint/项目文书.md) | 设计路线 | 历史 | classlint 的三层本体论与长期设想 | 历史定位，以现行协议和 ROADMAP 为准 |
| [classlint/tests/world-arrakis/README.md](../classlint/tests/world-arrakis/README.md) | 案例与对外 | 案例 | 沙丘 PE003 真阳性的 dogfood 证据 | 保留当时转写与判定，夹具预期变化时补注 |
| [classlint/tests/world-westeros/README.md](../classlint/tests/world-westeros/README.md) | 案例与对外 | 案例 | 冰火真阴性与建模判断记录 | 保留当时 16 条转写背景，不套用主世界新条数 |
| [docs/README.md](README.md) | 使用参考 | 现行 | 全部项目文档的分类索引与更新入口 | 新增、删除或改变文档状态时同步 |
| [docs/接口说明.md](接口说明.md) | 使用参考 | 现行 | HTTP 路由、写入口、安全与错误合同 | `serve.py` 路由、字段或写策略变化时同步 |
| [docs/给前端的说明.md](给前端的说明.md) | 使用参考 | 现行 | 导出 JSON 字段、样例与前端使用规矩 | 导出字段、真实样例和界面状态变化时同步 |
| [docs/前端开工清单.md](前端开工清单.md) | 使用参考 | 现行 | 前后端分工、已完成界面与剩余工作 | 界面交付状态变化时同步 |
| [docs/协作流程.md](协作流程.md) | 使用参考 | 现行 | 世界状态机与 Git/CI 协作映射 | 分支保护、门禁和评审流程变化时同步 |
| [docs/判定规则总表.md](判定规则总表.md) | 使用参考 | 现行 | CA/CL/PE 规则与外部标准对照工作表 | 规则、事件词表或退出码变化时同步 |
| [docs/事件流水设计.md](事件流水设计.md) | 设计路线 | 现行 | 账本模型的设计决定、规则边界与 backlog | 事件语义、导出能力和后续裁决变化时同步 |
| [docs/世界模型设计.md](世界模型设计.md) | 设计路线 | 历史 | 账本模型的早期讨论稿 | 后续决定见事件流水设计，不改写历史 |
| [docs/代码评审提示词.md](代码评审提示词.md) | 评审过程 | 模板 | 单份对抗性代码评审任务书 | 方法保留，仓库命令与能力描述变化时同步 |
| [docs/代码评审提示词-分段.md](代码评审提示词-分段.md) | 评审过程 | 模板 | 按语义、存储、接口、测试、对账分段的评审任务书 | 方法保留，范围与当前接口描述变化时同步 |
| [docs/代码评审报告-守卫审计.md](代码评审报告-守卫审计.md) | 评审过程 | 历史 | 首轮全量守卫变异与缺口证据 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-全量守卫审计.md](代码评审报告-全量守卫审计.md) | 评审过程 | 历史 | 93 个变异点的第二轮守卫审计 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-边层合并.md](代码评审报告-边层合并.md) | 评审过程 | 历史 | 两引擎统一边层的差分与变异证据 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-语义.md](代码评审报告-语义.md) | 评审过程 | 历史 | 规则语义与误报漏报评审 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-往返与变形.md](代码评审报告-往返与变形.md) | 评审过程 | 历史 | 存储读写往返和输入变形评审 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-接口.md](代码评审报告-接口.md) | 评审过程 | 历史 | HTTP 与前端外部视角评审 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-测试.md](代码评审报告-测试.md) | 评审过程 | 历史 | 测试名实一致性与 CI 评审 | 以评审锚点为准，不改写 verdict |
| [docs/代码评审报告-对账.md](代码评审报告-对账.md) | 评审过程 | 历史 | 契约、代码、测试、文档四方对账 | 以评审锚点为准，修复记录保留原貌 |
| [docs/代码评审报告-事件流水与可写接口.md](代码评审报告-事件流水与可写接口.md) | 评审过程 | 历史 | 协议 1.7 时期事件与写接口评审 | 后续修复见提交史，不改写 verdict |
| [docs/代码评审报告-判定器注册表.md](代码评审报告-判定器注册表.md) | 评审过程 | 草案 | CA/CL/PE/econ 双跑验收、Registry 原子切换与独立评审准备 | 独立评审、用户签核与发布周期状态变化时同步；未完成前不得删除 legacy |
| [docs/superpowers/plans/2026-10-19-event-ledger.md](superpowers/plans/2026-10-19-event-ledger.md) | 设计路线 | 历史 | 协议 1.2 事件流水的已执行计划 | 历史留档，不批量补勾或改成 1.8 |
| [docs/superpowers/specs/2026-10-24-works-layer-design.md](superpowers/specs/2026-10-24-works-layer-design.md) | 设计路线 | 草案 | 作品层视图、时间窗与分支设计 | 未实现，待作者拍板后再更新 |
| [docs/superpowers/specs/2026-10-28-modify-event-design.md](superpowers/specs/2026-10-28-modify-event-design.md) | 设计路线 | 现行 | modify 同身份变化的事件语义与规则复用设计 | 已实施，后续 modify 语义变化时同步 |
| [docs/superpowers/plans/2026-10-28-modify-event.md](superpowers/plans/2026-10-28-modify-event.md) | 设计路线 | 历史 | modify 事件的红绿实施与全量验收计划 | 已执行，保留红绿验证与验收记录 |
| [docs/superpowers/specs/2026-10-29-classlint-entity-mentions-design.md](superpowers/specs/2026-10-29-classlint-entity-mentions-design.md) | 设计路线 | 现行 | classlint 正文别名识别、注册表校验与 JSON mentions 设计 | 已实施，后续 mentions 语义变化时同步 |
| [docs/superpowers/plans/2026-10-29-classlint-entity-mentions.md](superpowers/plans/2026-10-29-classlint-entity-mentions.md) | 设计路线 | 历史 | classlint 正文别名识别的红绿实施与验收计划 | 已执行，保留红绿验证与验收记录 |
| [docs/superpowers/specs/2026-10-30-judge-registry-design.md](superpowers/specs/2026-10-30-judge-registry-design.md) | 设计路线 | 现行 | CA/CL/PE/econ 判定器注册表、双跑迁移与回退设计 | 设计已确认，实施与验收状态变化时同步 |
| [docs/superpowers/plans/2026-10-30-judge-registry.md](superpowers/plans/2026-10-30-judge-registry.md) | 设计路线 | 草案 | 判定器注册表的分期迁移、双跑与原子切换计划 | 执行时逐项勾选，完成后转为历史 |
| [docs/superpowers/specs/2026-10-28-documentation-governance-design.md](superpowers/specs/2026-10-28-documentation-governance-design.md) | 设计路线 | 现行 | 本轮文档治理的已确认设计规格 | 已实施，后续文档政策变化时同步 |
| [docs/superpowers/plans/2026-10-28-documentation-governance.md](superpowers/plans/2026-10-28-documentation-governance.md) | 设计路线 | 历史 | 本轮文档治理的逐步实施计划 | 已执行，保留红绿验证与验收记录 |
