# classlint ROADMAP

详细任务与验收标准见 [开发计划.md](开发计划.md)；此处仅里程碑。

| 阶段 | Sprint | 交付 | 状态 |
| :-: | :-: | :-: | :-: |
| 基础层 | 0 | 目录结构 + Markdown 解析器 + `init`/`check` | ✅ 完成（2026-09-24） |
| 生产关系层 | 1–3 | 七种关系（owns/controls/extracts/coerces/legitimizes/owes/depends_on）+ PE001–PE005（定性）+ 关系图 + 影响报告 | Sprint 1–2 ✅（2026-09-24）；Sprint 3 ⬜ |
| 流量层 | 4–6 | 四种线（物流/暴力/信息/人员）+ 守恒律 + PE004/005 定量回填 + PE006–PE008 | ⬜ |
| 个人关系层 | 7 | kin/allegiance/bond/affinity/history + PE 规则修正项 | ⬜ |
| 时间线 + 视图 | 8–10 | 点事件/结构变迁 + 关系图/时间线/地图三视图 | ⬜ |
| AI 辅助 | 11–12 | 实体关系提取、提问式补全（用户自带 API key） | ⬜ |

**总量：** 约 12–16 周，按每周 10–15 小时估算。

## 当前：Sprint 3 准备

- PE004/PE005 定性版
- 关系图生成（DOT 或 JSON）
- 影响报告（下游依赖闭包，参考 canonlint CA504）
