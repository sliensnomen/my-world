# WGP-econ 扩展包 · 草案 v0.3

**状态：草案，未冻结 ｜ 依赖：WGP-core v1.0 ｜ 日期：2026-11-27**

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
| `value` | 必须 | 有限非负数字（int/float；nan/inf/负数拒绝） |
| `unit` | 必须 | 非空字符串，自由文本单位 |
| `justification` | 条件必填 | 越界时必须（CA602），其余随意 |

## 2.1 世界参数 `econ.yaml`（v0.3）

食物链需要一组世界级比例，放在世界根目录的 `econ.yaml`，不塞进任何一张卡：

```yaml
params:
  food_per_person_day:
    value: 0.6
    unit: kg_grain/person/day
```

- `params` 必须是映射；`food_per_person_day` 必须有有限正数 `value` 与非空字符串 `unit`。
- 没有 `econ.yaml` 时 CA603 整体沉默：缺数据不是违规。
- 参数只参与报告，工具不把它写回卡面。

## 3. 规则族 CA6xx

| 编号 | 级别 | 定义 |
|---|---|---|
| CA601 | error | figure 缺 `value`/`unit`、`unit` 非非空字符串，或 `value` 非有限非负数字 |
| CA602 | warning | figure 越参数表硬边界且无 `justification`；或分母为 0 但分子 >0（零人口不可能供养军队） |
| CA603 | warning / error | 食物缺口：`population × food_per_person_day > grain_supply + grain_import` 且无 `justification` 时 warning；`econ.yaml` 缺参数或参数形状坏时 error |

**缺数据不报错原则：** 参数表规则需要的一对 figure 缺其一时，该规则跳过——世界永远是大部未量化的，缺失不是违规。

## 4. 参数表 v0（每条注明出处，升 minor 版本维护）

| id | 关系 | 上界 | 出处 |
|---|---|---|---|
| standing-army-ratio | `military_size / population` | 0.02 | 前现代常备军供养上限启发式（中世纪欧洲估算 1–2%） |
| wartime-garrison-ratio | `garrison / population` | 0.10 | 围城战总动员极限启发式 |

边界值故意宽松——它抓的是"贫穷农业国养十万常备军"级的结构裂缝，不抓细节误差。
精细估算属 CA9xx AI 建议层。

## 5. 修订记录

- **v0.3（2026-11-27）**：新增 CA603 食物链——世界根 `econ.yaml` 的 `food_per_person_day` × `population` 对 `grain_supply`/`grain_import`；缺口 warning，配置坏 error，补 `justification` 放行；推导只报告、不写回卡。对应 1.4 事件优先 P1.5。
- **v0.2（2026-11-24）**：数值收紧——`value` 必须是有限非负数字（nan/inf/负数报 CA601），`unit` 必须非空字符串；CA602 增加「分母为 0 而分子 >0」的 warning（此前静默跳过）。对应 issue #38 的 econ 数值类。
