#!/usr/bin/env bash
# 重建测试夹具：world-bad（全规则触发）与 world-clean（应全绿）
set -euo pipefail
cd "$(dirname "$0")"
rm -rf world-bad world-clean
mkdir -p world-bad/entries world-clean/entries

B=world-bad/entries

# --- 合法链条 geo→fiscal→military ---
cat > $B/grain-belt.md <<'EOF'
---
id: grain-belt
title: 谷带平原
type: location
author: tester
date: 2026-09-23
status: canon
load_bearing: true
layer: geo
canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---
灰港以北的冲积平原，河网密布，是整个地区唯一的大规模产粮区。
每年两季收获，养活了灰港城邦八成的人口，也是所有贸易路线的根基。
EOF

cat > $B/gh-customs.md <<'EOF'
---
id: gh-customs
title: 灰港关税
type: event
author: tester
date: 2026-09-23
status: canon
load_bearing: true
layer: fiscal
canon_refs: [grain-belt]
conflicts_with: []
depends_on:
  - id: grain-belt
    kind: economy
    critical: true
superseded_by: null
ai_assisted: false
---
灰港议会向一切进出港货物征收的关税，税率按货值十二取一。
关税是城邦财政的命脉，舰队军饷、港口维护和议会开销全部由此支出。
EOF

cat > $B/gh-fleet.md <<'EOF'
---
id: gh-fleet
title: 灰港舰队
type: faction
author: tester
date: 2026-09-23
status: canon
load_bearing: true
layer: military
canon_refs: [gh-customs]
conflicts_with:
  - id: gh-memo
    stance: official
depends_on:
  - id: gh-customs
    kind: fiscal
    critical: true
superseded_by: null
ai_assisted: false
---
灰港的常备舰队，三十艘桨帆船，兵员两千，军饷由关税全额供养。
舰队司令由议会任命，但水手的忠诚只属于发饷的人。
EOF

# CA402 目标为 trial（gh-fleet 引用 canon，无 CA402；此处无）——gh-memo 为 trial 被 conflicts 对象式引用（豁免 CA403）
cat > $B/gh-memo.md <<'EOF'
---
id: gh-memo
title: 自由市备忘录
type: event
author: tester
date: 2026-09-23
status: trial
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---
一份流传的匿名文件，声称关税实为海寇与议会的分赃协议。
EOF

# CA404: canon 条目 depends_on 指向 trial
cat > $B/harbor-watch.md <<'EOF'
---
id: harbor-watch
title: 港口卫队
type: faction
author: tester
date: 2026-09-23
status: canon
load_bearing: true
layer: military
canon_refs: []
conflicts_with: []
depends_on:
  - id: gh-memo
    kind: fiscal
    critical: true
superseded_by: null
ai_assisted: false
---
港口的陆上卫队，负责码头治安与缉私，编制五百人。
EOF

# CA108 info: kind 实验值
cat > $B/pirates.md <<'EOF'
---
id: pirates
title: 黑帆海寇
type: faction
author: tester
date: 2026-09-23
status: trial
load_bearing: true
layer: military
canon_refs: []
conflicts_with: []
depends_on:
  - id: gh-customs
    kind: x-faith
    critical: false
superseded_by: null
ai_assisted: false
---
游荡在灰港外海的海寇团伙，据说与城内某些议员暗通款曲。
EOF

# CA502: 环 ring-a → ring-b → ring-a
cat > $B/ring-a.md <<'EOF'
---
id: ring-a
title: 环甲
type: faction
author: tester
date: 2026-09-23
status: trial
load_bearing: true
layer: economy
canon_refs: []
conflicts_with: []
depends_on:
  - id: ring-b
    kind: economy
    critical: true
superseded_by: null
ai_assisted: false
---
环甲靠环乙供养。
EOF
cat > $B/ring-b.md <<'EOF'
---
id: ring-b
title: 环乙
type: faction
author: tester
date: 2026-09-23
status: trial
load_bearing: true
layer: economy
canon_refs: []
conflicts_with: []
depends_on:
  - id: ring-a
    kind: economy
    critical: true
superseded_by: null
ai_assisted: false
---
环乙靠环甲供养。
EOF

# CA401: 不存在的 id + world:id 形式
cat > $B/bad-refs.md <<'EOF'
---
id: bad-refs
title: 坏引用
type: character
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: [ghost-entry, otherworld:shared-lore]
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---
一个引用了不存在条目的角色。
EOF

# CA405: archived 被引用且无 superseded_by（CA402 不应双报）
cat > $B/old-tax.md <<'EOF'
---
id: old-tax
title: 旧税率法案
type: event
author: tester
date: 2026-09-23
status: archived
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: []
ai_assisted: false
---
已废止的十取一税率法案。
EOF
cat > $B/tax-hist.md <<'EOF'
---
id: tax-hist
title: 税制沿革
type: event
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: [old-tax]
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---
梳理灰港税制变迁的条目。
EOF

# CA402: archived 但已填 superseded_by → 报在引用方
cat > $B/old-law.md <<'EOF'
---
id: old-law
title: 旧市政条例
type: event
author: tester
date: 2026-09-23
status: archived
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: gh-customs
ai_assisted: false
---
已被新关税条例取代的旧市政条例。
EOF
cat > $B/law-hist.md <<'EOF'
---
id: law-hist
title: 法制沿革
type: event
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: [old-law]
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---
梳理灰港法制变迁的条目。
EOF

# CA105: 重复 id 独立对
cat > $B/dup-id.md <<'EOF'
---
id: dup-entry
title: 重复甲
type: item
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: []
conflicts_with: []
superseded_by: null
ai_assisted: false
---
重复 id 甲。
EOF
cat > $B/dup-id-2.md <<'EOF'
---
id: dup-entry
title: 重复乙
type: item
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: []
conflicts_with: []
superseded_by: null
ai_assisted: false
---
重复 id 乙。
EOF

# CA102(stance)/CA103/CA106
cat > $B/bad-fields.md <<'EOF'
---
id: bad-fields
title: 坏字段
type: character
author: tester
date: 昨天
status: draft
load_bearing: false
canon_refs: []
conflicts_with:
  - id: gh-memo
    stance: rebellious
depends_on: []
superseded_by: null
ai_assisted: false
secret_level: 3
---
字段实验条目。
EOF

# CA501: 向上依赖（military 依赖 political，物质族 fiscal 边）
cat > $B/coup-ledger.md <<'EOF'
---
id: coup-ledger
title: 政变账本
type: faction
author: tester
date: 2026-09-23
status: trial
load_bearing: true
layer: military
canon_refs: []
conflicts_with: []
depends_on:
  - id: council
    kind: fiscal
    critical: true
superseded_by: null
ai_assisted: false
---
一支军饷直接由议会金库拨付的佣兵团——军事层向上依赖政治层，方向反了。
EOF
cat > $B/council.md <<'EOF'
---
id: council
title: 灰港议会
type: faction
author: tester
date: 2026-09-23
status: canon
load_bearing: true
layer: political
canon_refs: [gh-customs]
conflicts_with: []
depends_on:
  - id: gh-customs
    kind: fiscal
    critical: true
superseded_by: null
ai_assisted: false
---
灰港的统治机构，由纳税额前四十的商人家族组成。
EOF

# CA503: ideology 承重墙无 critical 依赖
cat > $B/temple.md <<'EOF'
---
id: temple
title: 潮汐神庙
type: faction
author: tester
date: 2026-09-23
status: trial
load_bearing: true
layer: ideology
canon_refs: []
conflicts_with: []
depends_on:
  - id: grain-belt
    kind: economy
    critical: false
superseded_by: null
ai_assisted: false
---
灰港的信仰中心，主持出航祝福与葬礼。
EOF

# CA201: 两篇正文几乎一样（>100 字）
python3 - <<'PY'
body = "灰港南面的悬崖上立着灯塔，灯火由守灯人世代相传。每当风暴之夜，灯塔的油火彻夜不灭，为归港的船只指明方向。守灯人家族因此免缴关税，这是城邦最古老的特许之一，记载于建市石碑的背面。第三代守灯人曾在灯塔地下室藏过走私的盐，此事无人再提，但码头老人都知道地窖的锁从来没有换过。"
fm = """---
id: %s
title: %s
type: location
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: []
conflicts_with: []
superseded_by: null
ai_assisted: false
---
"""
open("world-bad/entries/lighthouse-a.md", "w").write(fm % ("lighthouse-a", "灯塔甲") + body)
open("world-bad/entries/lighthouse-b.md", "w").write(fm % ("lighthouse-b", "灯塔乙") + body)
PY

# CA403: 简式矛盾，对方不回指
cat > $B/rumor-a.md <<'EOF'
---
id: rumor-a
title: 传闻甲
type: event
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs: []
conflicts_with: [gh-customs]
superseded_by: null
ai_assisted: false
---
传闻关税实际税率是十取二而非十二取一。
EOF

# CA109: canon_refs 写成字符串 + bool 字段写成字符串
cat > $B/type-errors.md <<'EOF'
---
id: type-errors
title: 类型错误条目
type: item
author: tester
date: 2026-09-23
status: draft
load_bearing: "true"
canon_refs: grain-belt
conflicts_with: []
ai_assisted: "no"
superseded_by: null
---
类型测试。
EOF

# CA109: canon_refs 元素是 dict
cat > $B/bad-ref-elem.md <<'EOF'
---
id: bad-ref-elem
title: 坏引用元素
type: item
author: tester
date: 2026-09-23
status: draft
load_bearing: false
canon_refs:
  - id: grain-belt
conflicts_with: []
ai_assisted: false
superseded_by: null
---
引用元素是对象而非字符串。
EOF

# CA401: superseded_by 指向不存在
cat > $B/old-tax2.md <<'EOF'
---
id: old-tax2
title: 更旧的税法
type: event
author: tester
date: 2026-09-23
status: archived
load_bearing: false
canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: nowhere-entry
ai_assisted: false
---
有承接者但指向虚空。
EOF

# --- world-clean：应 0 错误 exit 0 ---
C=world-clean/entries
python3 - <<'PY'
body1 = "灰港以北的冲积平原，河网密布，是整个地区唯一的大规模产粮区。每年两季收获，养活了灰港城邦八成的人口，也是所有贸易路线的根基。没有了谷带，灰港的舰队、关税和议会都不过是沙滩上画的图案。平原上的灌溉水渠由各村共管，每年春汛前集中修缮，这个传统比灰港建市还要早两百年。渠首的分水石碑上刻着各村的水额分配，争吵了上百年也没有改过一个字。"
body2 = "灰港议会向一切进出港货物征收的关税，税率按货值十二取一。关税是城邦财政的命脉，舰队军饷、港口维护和议会开销全部由此支出。税率每动一分，谷带的粮商和港口的船主就要在议会里吵上三个月。历史上关税曾因粮价暴涨临时加到六取一，直接引发了当年的码头罢市，议会从此学会在动税率之前先囤积三个月的存粮。"
body3 = "灰港的常备舰队，三十艘桨帆船，兵员两千，军饷由关税全额供养。舰队司令由议会任命，但水手的忠诚只属于发饷的人。历史上三次税率危机都伴随舰队哗变，这是灰港政治的第一条铁律。舰队冬季驻扎在南岸船坞，由船匠行会负责维护，行会因此享有议会的一个固定席位，这也是行会历史上唯一一次用服务质量换来的政治权力。"
fm = """---
id: %s
title: %s
type: %s
author: tester
date: 2026-09-23
status: canon
load_bearing: true
layer: %s
canon_refs: %s
conflicts_with: []
depends_on: %s
superseded_by: null
ai_assisted: false
---
"""
open("world-clean/entries/grain-belt.md", "w").write(
    fm % ("grain-belt", "谷带平原", "location", "geo", "[]", "[]") + body1)
open("world-clean/entries/gh-customs.md", "w").write(
    fm % ("gh-customs", "灰港关税", "event", "fiscal", "[grain-belt]",
          "\n  - id: grain-belt\n    kind: economy\n    critical: true") + body2)
open("world-clean/entries/gh-fleet.md", "w").write(
    fm % ("gh-fleet", "灰港舰队", "faction", "military", "[gh-customs]",
          "\n  - id: gh-customs\n    kind: fiscal\n    critical: true") + body3)
PY

echo "fixtures rebuilt: $(ls world-bad/entries | wc -l) bad, $(ls world-clean/entries | wc -l) clean"
