#!/usr/bin/env python3
"""沙丘（Dune）测试世界生成脚本 —— WGP v0.5 第三个 dogfood 样本。
重点：香料垄断链（七层尽量走通）、生态改造 vs 香料经济的结构性矛盾、
kind 表达力边界（宗教工程、垄断物流、预言合法性）。"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


def fm(id, title, type_, status, layer=None, load_bearing=False,
       canon_refs="[]", conflicts="[]", depends="[]"):
    lb = "true" if load_bearing else "false"
    layer_line = f"layer: {layer}\n" if layer else ""
    return f"""---
id: {id}
title: {title}
type: {type_}
author: dataset-dune
date: 2026-09-23
status: {status}
load_bearing: {lb}
{layer_line}canon_refs: {canon_refs}
conflicts_with: {conflicts}
depends_on: {depends}
superseded_by: null
ai_assisted: false
---
"""


def dep_list(deps):
    if not deps:
        return "[]"
    lines = [""]
    for id, kind, critical in deps:
        c = "true" if critical else "false"
        lines.append(f"  - id: {id}\n    kind: {kind}\n    critical: {c}")
    return "\n".join(lines)


def conflict_list(refs):
    if not refs:
        return "[]"
    if all(isinstance(r, str) for r in refs):
        return "[" + ", ".join(refs) + "]"
    lines = [""]
    for r in refs:
        if isinstance(r, str):
            lines.append(f"  - {r}")
        else:
            lines.append(f"  - id: {r[0]}\n    stance: {r[1]}")
    return "\n".join(lines)


E = {}

E["arrakis"] = ("location", "canon", "geo", True, """\
厄拉科斯，沙丘星。全宇宙唯一的香料产地，同时是全宇宙最缺水的人类居住地。
两件事不是巧合：香料的诞生与沙虫生命周期绑定，而沙虫死于水。
这颗行星本身就是一条铁律：香料与水不可兼得。""", "[]", "[]", [])

E["sandworm-cycle"] = ("event", "canon", "geo", True, """\
沙虫生命周期：沙鳟锁水系、成熟为巨虫、死后化为香料喷发的原料。
香料不是矿产而是生物过程的副产品——采得着，种不出。
凯因斯的生态改造若成功，沙虫灭、香料绝。这条矛盾被写入 conflicts_with。""",
"[arrakis]", conflict_list(["kynes-terraform-plan"]), [])

E["spice-melange"] = ("item", "canon", "resource", True, """\
美琅脂，香料。延缓衰老、开启预知、成瘾后断服即死。
宇航公会导航员无香料则不能导航，贝尼·杰瑟里特无香料则无圣母试炼，
整个帝国经济以它为血液。垄断品级的战略物资，唯一产地厄拉科斯。""",
"[]", "[]", [("sandworm-cycle", "production", True)])

E["spacing-guild"] = ("faction", "canon", "economy", True, """\
宇航公会：星际运输的绝对垄断者。导航员在香料气雾中以预知导航折叠空间。
没有公会就没有星际贸易、没有军队调动、没有帝国。
它对香料的依赖是全身的：断香料=断导航=断文明。
同时它在厄拉科斯上空保持沉默（无气象卫星、无侦察），因为弗雷曼人用香料贿赂它。""",
"[]", "[]", [("spice-melange", "resource", True),
           ("fremen-bribes", "economy", False)])

E["fremen-bribes"] = ("event", "canon", "economy", False, """\
弗雷曼人用私采香料贿赂宇航公会，换厄拉科斯上空的卫星真空。
全银河最贵的公关费，付得心甘情愿——这是弗雷曼生态计划的隐身衣。""",
"[]", "[]", [("spice-melange", "resource", True)])

E["choam"] = ("faction", "canon", "economy", True, """\
CHOAM，宇宙贸易的垄断公司，股份由皇帝与各大家族分持。
它是把香料换成财富的机器：董事席位即权力分红。
依托公会的运输垄断而存在，一荣俱荣。""",
"[]", "[]", [("spacing-guild", "economy", True)])

E["choam-dividends"] = ("event", "canon", "fiscal", False, """\
CHOAM 分红：皇族与大家族的财政主渠道。厄莉娅时代之前的帝国财政，
本质上是一张香料利润的分配表。""",
"[]", "[]", [])

E["corrino-imperium"] = ("faction", "canon", "political", True, """\
柯瑞诺帝国。沙达姆四世的权力两条腿：萨多卡军团的军事霸权，
与 CHOAM 分红构成的财政血脉。兰兹拉德大家族联合可与皇权抗衡——
这个制衡结构是全部阴谋的舞台。""",
"[]", "[]", [("sardaukar", "manpower", True),
           ("choam-dividends", "fiscal", True)])

E["sardaukar"] = ("faction", "canon", "military", True, """\
萨多卡军团：帝国恐怖统治的军事基础，兵员全部来自监狱行星萨鲁萨·塞昆都斯——
以极限环境筛选出宇宙最强士兵。它的供养链短而硬：恶劣星球出人，皇权出钱。""",
"[]", "[]", [("salusa-secundus", "manpower", True),
           ("choam-dividends", "fiscal", False)])

E["salusa-secundus"] = ("location", "canon", "geo", False, """\
萨鲁萨·塞昆都斯：柯瑞诺家族的流放监狱星，死亡率极高的炼狱环境。
萨多卡的兵源筛选器——环境本身即兵役制度。""", "[]", "[]", [])

E["harkonnen-fief"] = ("faction", "canon", "economy", True, """\
哈克南家族：以厄拉科斯八十年采香权积累的巨富。
财富完全系于香料采收，失去厄拉科斯即失去一切——
这正是皇帝借刀杀人的杠杆支点。""",
"[]", "[]", [("spice-harvest", "production", True)])

E["spice-harvest"] = ("event", "canon", "production", True, """\
香料采收：爬行者与运载机在沙虫袭击的倒计时里抢收。
高危、高耗、高利的工业生产，全部依托厄拉科斯沙漠生态。""",
"[]", "[]", [("spice-melange", "resource", True)])

E["fremen"] = ("faction", "canon", "military", True, """\
弗雷曼人：厄拉科斯自由民，沙漠化生存的专家战士。
内部经济以水为本位（水环即货币、水债即信用），
对外用香料贿赂公会换取隐身。人口规模被帝国严重低估——这是全书最大的情报盲区。""",
"[]", "[]", [("water-rings", "fiscal", True)])

E["water-rings"] = ("item", "canon", "fiscal", True, """\
水环：弗雷曼社会的水权凭证。水即货币、即信用、即遗产。
一个把财政建立在湿度计上的经济体——其存在前提是厄拉科斯的绝对干旱。""",
"[]", "[]", [("arrakis", "resource", True)])

E["kynes-terraform-plan"] = ("event", "canon", "ideology", True, """\
凯因斯的生态改造计划：以数百年尺度把厄拉科斯改造成水润星球。
愿景层（ideology）的多世代工程，执行完全依赖弗雷曼人的世代劳动。
与香料经济存在结构性死锁：改造成功=沙虫灭绝=香料断绝=银河经济崩塌。""",
"[]", conflict_list(["sandworm-cycle"]),
[("fremen", "manpower", True)])

E["bene-gesserit"] = ("faction", "canon", "ideology", True, """\
贝尼·杰瑟里特姐妹会：以育种计划与宗教工程操纵银河政治的千年组织。
不养兵、不征税——它的供养关系全部是非物质的：情报网络、
宗教神话预埋（护教团）、以及嫁入各大家族的生育权安排。""",
"[]", "[]", [("missionaria-protectiva", "x-faith-engineering", True)])

E["missionaria-protectiva"] = ("faction", "canon", "ideology", False, """\
护教团：姐妹会的宗教工程部门，在原始星球预埋神话与预言，
为落难姐妹准备逃生通道。保罗在厄拉科斯的'救世主预言'正是其遗产——
被预埋的神话是现成的合法性基础设施。""", "[]", "[]", [])

E["paul-muaddib"] = ("character", "canon", "political", True, """\
保罗·穆阿迪布。他的权力三根支柱：弗雷曼军事力量、
护教团预埋预言提供的救世主合法性、以及娶伊如兰公主换来的皇位法理。
注意：三者无一是物质——沙丘的政治科学里，合法性可以自己长腿走路。""",
"[]", "[]", [("fremen", "manpower", True),
           ("missionaria-protectiva", "legitimacy", True)])

# 导航员形态：两版描述冲突（《沙丘》vs《沙丘救世主》）
E["navigator-dune"] = ("character", "canon", None, False, """\
《沙丘》本传：公会代表以人形出席宴会，皇帝暗自揣度他们还算不算人。
形态异化未被正面描写，仅暗示。""",
"[]", conflict_list([("navigator-messiah", "official")]), [])
E["navigator-messiah"] = ("character", "canon", "None", False, """\
《沙丘救世主》：导航员埃德里克正式登场——悬浮香料气雾槽中的鳍状异形体，
非人化程度远超本传暗示。两版形态描述冲突，均留档。""",
"[]", conflict_list([("navigator-dune", "heretic")]), [])

# 护盾×激光：设定前后漂移
E["shield-lasgun-dune"] = ("event", "canon", None, False, """\
《沙丘》本传：激光击中霍尔茨曼护盾产生不可预测的爆炸结果，
可能炸射手也可能炸持盾者——因此无人敢用。""",
"[]", conflict_list(["shield-lasgun-later"]), [])
E["shield-lasgun-later"] = ("event", "canon", None, False, """\
后作把护盾-激光互作用当作可计算的伪核爆来战术运用（沙丘世界知名的
设定漂移案例）。两版规则并存，不加裁决。""",
"[]", conflict_list(["shield-lasgun-dune"]), [])


def main():
    path = ROOT / "world-arrakis"
    if path.exists():
        shutil.rmtree(path)
    (path / "entries").mkdir(parents=True)
    for id, (type_, status, layer, lb, body, refs, conflicts, deps) in E.items():
        text = fm(id, id, type_, status,
                  layer=None if layer in (None, "None") else layer,
                  load_bearing=lb, canon_refs=refs,
                  conflicts=conflicts, depends=dep_list(deps))
        (path / "entries" / f"{id}.md").write_text(text + body, encoding="utf-8")
    print(f"arrakis: {len(E)} entries")


if __name__ == "__main__":
    main()
