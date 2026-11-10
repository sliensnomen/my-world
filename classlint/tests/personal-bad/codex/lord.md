---
id: lord
title: 领主
type: faction
demand:
  tax:
    amount: 100
    unit: 石
coerces:
  - town
depends_on:
  - id: town
    critical: true
kin:
  - id: town
    what: 兄弟
allegiance:
  - id: town
    what: 庇护
---
领主。
