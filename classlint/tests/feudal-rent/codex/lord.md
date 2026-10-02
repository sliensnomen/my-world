---
id: lord
title: 领主
type: character
owns: [manor]
controls: [peasants]
extracts:
  - id: peasants
    what: 劳役地租
depends_on:
  - id: peasants
    critical: true
    kind: manpower
---
领主占有庄园、控制农民、抽取劳役地租。
