---
id: corrino-imperium
title: 柯瑞诺帝国
type: faction
owns: [arrakis]
controls: [sardaukar]
coerces:
  - id: salusa-secundus
    note: 帝国维持监狱行星的炼狱环境——暴力恰恰在生产供养能力，留档讨论 PE002 语义
legitimizes:
  - id: harkonnen-fief
    note: 厄拉科斯八十年采香权是皇帝御封
  - id: choam
    note: 帝国特许状
depends_on:
  - id: sardaukar
    critical: true
    kind: manpower
  - id: choam
    critical: true
    kind: fiscal
---
沙达姆四世的权力两条腿：萨多卡军团的军事霸权，与 CHOAM 分红构成的财政血脉。
PE003 预期触发：corrino legitimizes choam 而 choam legitimizes corrino——帝位与特许公司的
合法性闭环，外部无锚。小说实证了它的崩塌：保罗抓住香料这个物质锚点打破循环。
