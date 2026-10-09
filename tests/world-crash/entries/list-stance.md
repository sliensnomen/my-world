---
id: list-stance
title: stance 写成列表的条目
type: event
author: tester
date: 2026-09-23
status: canon
load_bearing: false
canon_refs: []
conflicts_with:
  - id: ok-node
    stance: [official]
ai_assisted: false
---
这个条目的 conflicts_with 目标存在，但 stance 故意写成 YAML 列表，用来触发取值守卫。修复前 list 不可哈希，会让成员检查抛 TypeError 并让整个审计崩掉。它应当只产生一条取值非法的错误，不应当产生内容类提示；它与 ok-node 的标注是对称的，所以不该出现不对称提示。名册、码头、钟楼、石屋、钥匙、会首、抄录、留白，这些词都与承重墙关键词无关。石屋地窖里堆着二十几个空木箱，箱盖内侧刻着历任会首的名字，最早的一批字迹已经被潮气糊掉了。
