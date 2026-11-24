# `modify` 事件设计：同一身份内的变化

> 状态：已确认并实施。2026-10-28。
> 一句话：`modify` 记录「东西变了，但还是同一个 id」；它是事件标记，不是属性补丁系统。

## 1. 背景与目标

`docs/事件流水设计.md` 的 Backlog B1 中，`transform` 已在协议 1.7 转正，剩下
`modify` 未进词表。两者必须分开：`transform` 关闭旧身份的存在窗口并为一个或多个
新身份开窗；`modify` 不改变身份，也不改变存在窗口。

本轮目标是完成 B1 的 `modify` 转正，同时保持事件流水 v0 的克制：不新增属性模型、
不新增派生状态、不新增 CA 规则。B3 携带推导和 B5 CA301 的既有决定不变。

成功标准是：作者可以用正式 `event_kind: modify` 记账；现有通用校验照常工作；
正反意图测试证明身份、窗口和持有/保管/位置语义没有被暗改；六套标准回归全绿。

## 2. 已确认的事件语义

`modify` 是第 12 种正式 `event_kind`：

- `object` 必填：发生变化的客体，可沿用现有多值 id 列表形状；
- `by` 可选：施动者，语义与其他事件的 `by` 一致；
- `when` / `when_sort` 沿用现有完整事件和 fail-open 规则；
- 变化的具体内容写在事件正文，不新增属性名、旧值或新值字段；
- `result` 不属于 `modify` 的语义，产物身份变化应使用 `transform`。

示例：

```yaml
type: event
event_kind: modify
when: 城堡扩建后
when_sort: 305
by:
  - castle-stewards
object:
  - winter-town
```

这张卡只声明 `winter-town` 在同一身份下发生了变化。它不隐式改变该客体的持有者、
保管人或位置，也不关闭、重开其存在窗口。

本轮不新增「某种事件禁止哪些额外腿」的判定。现有通用腿形状检查保持不变；
`result` 对 `modify` 没有定义语义，不应被解释为产物或自动派生任何状态。

## 3. 规则复用与错误处理

不新增 CA 编号，确定性规则总数保持 55。

| 规则 | 对 `modify` 的行为 |
|---|---|
| CA102 | `modify` 是正式词表值，不再报非法枚举或实验值 info |
| CA109 | 事件字段和腿的通用形状检查不变；坏形状不与 CA702 双报 |
| CA401 | `object` / `by` 中的悬空 id 照常报错 |
| CA702 | 缺失或为空的 `object` 报 error；`by` 不是必填腿 |
| CA705 | `by` 中的人物若严格更早已 death，照常报 warning |
| CA708 | `modify` 是普通客体事件；落在存在窗口外报 warning，自身不是窗口边界 |

CA701 的事件依赖时序检查和其他通用检查保持原样。`modify` 不参与 CA703/CA704 的
所有权对账、CA709 的保管对账、CA711 的轨迹链或 CA712 的成员对账。

缺 `when_sort` 时不进有序流水，沿用现有 fail-open。没有已知存在边界的客体也不因
`modify` 获得一个虚构边界。

## 4. 实现边界与数据流

- `ledger.py`：在 `EVENT_KINDS` 加入 `modify`，在 `REQUIRED_LEGS` 登记
  `("object",)`。`existence_windows` 不为它增加分支；`derive_state` 不修改任何
  已有状态字段。
- `canonlint.py`：协议版本升为 1.9、契约版本升为 0.7；更新受词表和规则语义钉住的
  说明。CLI `event modify` 与 `--event-kind modify` 通过共享词表自动接受新值。
- `world.schema.json`：契约版本升为 0.7，`event_kind` 词表加入 `modify`；不增加
  properties。
- `store/`、HTTP 写接口和 web 不需要新字段或新分支，继续复用现有事件字段导出。
- 不修改既有世界夹具来虚构小说案例；测试使用独立合成世界。

## 5. 测试设计与红绿证据

在 `tests/run_tests.py` 新增并注册 `modify` 意图检查，先运行到红，再实现到绿。
同一组检查覆盖：

1. 窗口内、腿完整的 `modify` 不报 CA102/CA702/CA708；
2. 缺失 `object` 报 CA702，坏形状只报 CA109，悬空 id 报 CA401；
3. create 之前和 destroy 之后的 `modify` 报 CA708，窗口内和缺排序键的边界情形
   仍按原规则豁免；
4. 可选 `by` 能触发既有 CA705，不把它误设为必填；
5. `modify` 前后，既有持有者、保管人和位置的派生结果不变；
6. CLI `event modify` 真实建卡后能被审计器接受，证明共享词表入口端到端可用。

测试项总数以实测为准并同步文档；按当前基线预计主套件从 62 项变为 63 项。
不主动更新既有世界快照；若版本透出导致快照变化，必须肉眼核对后有意更新。

## 6. 协议与文档同步

- `PROTOCOL.md`：§2.2 改为十二种事件，CA702/CA708 写明 `modify`，§9 增加
  协议 1.9 修订记录；规则编号与总数不变。
- `world.schema.json`、`README.md`、`CONTRIBUTING.md`、`store/README.md`：同步版本、
  词表或测试数字，以代码和实测为准。
- `docs/判定规则总表.md`：更新事件词表、必填腿表和 CA702/CA708 的现行语义。
- `docs/事件流水设计.md`：B1 标记 `modify` 已转正，记录「同 id、不动窗口、正文记变化」
  的裁决；保留 transform 的历史案例和 B3/B5 原决定。
- `docs/给前端的说明.md` 及其他提到事件词表的现行参考：同步到十二种事件。
- `docs/superpowers/specs/2026-10-24-works-layer-design.md`：仅把未实施作品层预留的
  契约 0.7 机械调整为 0.8，避免与本轮已占用的 0.7 冲突，不改作品层设计语义。
- `docs/README.md`：登记本规格和后续实施计划，并按实施状态更新。

## 7. 明确不做

- 不设计属性前后值、补丁合并、属性冲突或属性派生状态；
- 不让 `modify` 继承、清除或改写持有者、保管人、位置和成员关系；
- 不实现携带推导，不新增 `carrying` / `contains`；
- 不改变 CA301 的级别、关键词表或白名单机制；
- 不实现 README 中判定器注册表、chain、作品层或酒馆适配器等其他方向。

## 8. 验收

实施完成后运行并全部通过：

```bash
python3 tests/run_tests.py
python3 tests/test_schema.py
python3 tests/test_store.py
python3 tests/test_serve.py
python3 tests/test_docs.py
python3 classlint/tests/run_tests.py
```

最后核对版本号、55 条规则不变、既有世界夹具无无意变化、文档索引无漏登记，
并用 CLI 的真实 `modify` 建卡与审计结果验证用户场景。
