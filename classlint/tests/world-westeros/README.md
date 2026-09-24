# world-westeros · classlint 真实作品 dogfood（2026-09-24）

自 canonlint `tests/world-westeros`（16 条真实设定条目）转写为 classlint 七关系模型。
**结果：0 错误 0 警告——结构自洽的世界，三条 PE 规则全部正确沉默（真阴性）。**

## 转写的建模判断

| WGP 原边 | classlint 边 | 理由 |
|---|---|---|
| iron-throne depends_on crown-debt-agot | iron-throne **owes** iron-bank | 债务记录不是供养者；depends_on 只表达"谁靠谁养"，债权关系归 owes |
| the-north depends_on robb-host-ledger（manpower） | （丢弃） | 兵力账本不是供养来源——WGP v0.5"depends_on 不表达主题相关"的纪律在 classlint 同样成立 |
| （新增） | iron-throne **controls + extracts** kings-landing | 王领直辖与税赋：抽取以控制为基础，PE001 正确放行 |
| （新增） | iron-bank **extracts + coerces** iron-throne | 利息抽取以**信用强制**为基础（"不偿还就资助你的对手"）。建模结论：coerces 涵盖经济强制，不限物理暴力——PE001 的三选一基础无需改协议 |
| stannis depends_on iron-bank (critical) | 保留 + 补 **owes** iron-bank | 供养与债务是两条边 |
| conflicts_with（王冠债务/兵力两口径） | （不转写） | 口径矛盾治理是 WGP 的职责，classlint 不管——分工正确 |

## 逐规则评审

- **PE001**：两条 extracts 边均有基础，正确沉默。✅
- **PE002**：无 coerces×depends_on 重叠，正确沉默。注意：瑟曦违约→金库转投史坦尼斯是"供养者反噬"叙事，但走 owes/depends_on 表达，本就不属 PE002（那不是镇压）。✅
- **PE003**：本世界未标注 legitimizes 边，未被检验。下一个 dogfood 应用 world-arrakis（保罗权力三支柱：预言合法性/弗雷曼武力/皇位法理——legitimizes 的富矿）。⚠️ 待补

## 工具现在还看不见的（按设计）

1. **王冠财政黑洞**——六百万→数千万的膨胀 + 全部军事存在悬于债务：PE006 素材，需流量层数值（Sprint 4–6）。
2. **守夜人缺口**——不足千人守三百英里：人员线守恒问题（Sprint 4–6）。
3. **君临粮道单点**——depends_on critical 已表达，但"断供后多久崩"是流量层补给律的事。

## 协议结论

PE001–PE003 定义本轮**不改**（无误报、无该报未报）。PE006–008 的真实检验必须等流量层。
