---
id: lord
title: 领主
type: character
owns: [estate]
controls: [peasants]
extracts:
  - id: peasants
    what: 地租
depends_on:
  - id: peasants
    critical: true
  - id: bank
    kind: economy
    critical: true
owes:
  - id: bank
    what: 借款
---
领主占有庄园、控制农民、抽取地租、靠农民供养、欠银行钱，周转上靠银行续借
（PE009：这笔债之所以收得回来，是因为领主自己依赖银行的信贷通道）。
