# world-arrakis · classlint 真实作品 dogfood（2026-09-26）

自 canonlint `tests/world-arrakis`（22 条真实设定条目）转写为 classlint 七关系模型。
**结果：1 错误——PE003 真阳性，classlint 的第一个真实世界结构裂缝发现。**

```
[PE003] error codex/choam.md: legitimizes 闭环无外部锚点: choam ↔ corrino-imperium——合法性不能凭空互证
```

## 判定：真阳性 ✅

**帝位 ↔ CHOAM 的合法性闭环**：皇帝给 CHOAM 特许状（legitimizes），CHOAM 的分红体制把各大家族绑在帝位上（legitimizes 回流）——两者互证，分量外没有任何 legitimizes 锚点。

小说自己验证了这个判定：保罗不动一刀一枪，只抓住**香料**这个物质锚点（"谁有能力毁掉香料，谁就控制了宇宙"），帝位-CHOAM 循环即刻崩塌，皇帝被迫让位。一个合法性闭环在叙事里的真实死法，和 PE003 的报警一一对应——**这正是 classlint 存在理由的第一次实证**。

## 协议讨论（留档，本轮不改定义）

1. **"锚"该不该包括物质锚？** 马克思主义视角下合法性的锚本来就该是物质关系（香料、土地、暴力机器）。但 PE003 目前只认 legitimizes 边作锚。反方：若 owns/controls 也算锚，几乎所有闭环都有锚，规则形同虚设。本轮证据不足以裁决——PE003 的严格语义（只认规范层锚）恰好抓住了"帝国合法性纯靠意识形态内循环"这个真问题，**维持现定义，继续收集案例**。
2. **生产性暴力 vs 破坏性暴力**：corrino coerces salusa-secundus（维持炼狱环境）但 sardaukar depends_on salusa——暴力恰恰在**生产**供养能力而非破坏它。PE002 未触发（边归属不同实体，无传递违规原则正确生效），但语义边界已标记：将来若 PE002 扩展，需要区分两种暴力。
3. **贿赂不是抽取**：弗雷曼人贿赂公会是自愿的交换（买卫星真空），公会没有强制基础——七种关系有意不覆盖市场交易，标注留档。
4. **依赖实体，不依赖记录**：WGP 的 guild depends_on fremen-bribes、imperium depends_on choam-dividends 两条指向事件记录的边，转写时分别丢弃和改为 depends_on choam——与 westeros 同一纪律。

## 逐规则评审

- **PE001**：harkonnen extracts spice-harvest 有 controls 基础，正确放行。✅
- **PE002**：coerces（corrino→salusa）与 depends_on（corrino→sardaukar/choam）无同对重叠，正确沉默——见上"生产性暴力"。✅
- **PE003**：真阳性（见上）。✅

## 回归锁

已登记 `run_tests.py` EXPECTED：`[("PE003", "error", "codex/choam.md")]`——
既防 PE003 漏报，也防它在 westeros 上误报（两个真实世界一阴一阳互为对照）。
