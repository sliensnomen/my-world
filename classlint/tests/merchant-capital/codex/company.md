---
id: company
title: 商行
type: faction
controls: [weavers]
extracts:
  - id: weavers
    what: 成品差价
owes:
  - id: bank
    what: 周转借款
depends_on:
  - id: harbor-fleet
    critical: true
    kind: economy
---
包买制商行：向织户发放原料、收购成品，经船队外销，赚取差价。
