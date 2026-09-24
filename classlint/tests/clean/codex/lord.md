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
owes:
  - id: bank
    what: 借款
---
领主占有庄园、控制农民、抽取地租、靠农民供养、欠银行钱。
