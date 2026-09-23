# WGP-econ 扩展包 · 草案 v0.1

**状态：草案，未冻结 ｜ 依赖：WGP-core v1.0 ｜ 日期：2026-09-23**

数值系统扩展。核心哲学与 core 同源：**偏差合法化**——机器算期望值，作者有权偏离，但偏离必须留原因；原因入库成为设定资产。

## 1. 启用

世界仓库声明启用本包后，lint 才运行 CA6xx 规则并接受 `figures` 字段（未启用时 `figures` 按 CA106 报未定义字段）。

## 2. `figures` 字段（可选，映射）

```yaml
figures:
  population:    {value: 500000, unit: persons}
  garrison:      {value: 5000, unit: personnel}
  annual_revenue: {value: 120000, unit: gold_mark, justification: "含走私罚金，账面外收入"}
```

每个 figure 对象：

| 字段 | 必填 | 约束 |
|---|---|---|
| `value` | 必须 | 数字（int/float） |
| `unit` | 必须 | 字符串，自由文本单位 |
| `justification` | 条件必填 | 越界时必须（CA602），其余随意 |

## 3. 规则族 CA6xx

| 编号 | 级别 | 定义 |
|---|---|---|
| CA601 | error | figure 缺 `value`/`unit`，或 `value` 非数字 |
| CA602 | warning | figure 越参数表硬边界且无 `justification` |

**缺数据不报错原则：** 参数表规则需要的一对 figure 缺其一时，该规则跳过——世界永远是大部未量化的，缺失不是违规。

## 4. 参数表 v0（每条注明出处，升 minor 版本维护）

| id | 关系 | 上界 | 出处 |
|---|---|---|---|
| standing-army-ratio | `military_size / population` | 0.02 | 前现代常备军供养上限启发式（中世纪欧洲估算 1–2%） |
| wartime-garrison-ratio | `garrison / population` | 0.10 | 围城战总动员极限启发式 |

边界值故意宽松——它抓的是"贫穷农业国养十万常备军"级的结构裂缝，不抓细节误差。
精细估算属 CA9xx AI 建议层。
