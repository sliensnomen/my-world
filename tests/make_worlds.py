#!/usr/bin/env python3
"""把魔戒/冰火测试数据转成 WGP v0.4 条目仓库（中土 + 维斯特洛）。"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


def fm(id, title, type_, status, layer=None, load_bearing=False,
       canon_refs="[]", conflicts="[]", depends="[]", superseded="null"):
    lb = "true" if load_bearing else "false"
    layer_line = f"layer: {layer}\n" if layer else ""
    return f"""---
id: {id}
title: {title}
type: {type_}
author: dataset-v1
date: 2026-09-23
status: {status}
load_bearing: {lb}
{layer_line}canon_refs: {canon_refs}
conflicts_with: {conflicts}
depends_on: {depends}
superseded_by: {superseded}
ai_assisted: false
---
"""


def dep(id, kind, critical=True):
    return (id, kind, critical)


def dep_list(deps):
    if not deps:
        return "[]"
    lines = [""]
    for id, kind, critical in deps:
        c = "true" if critical else "false"
        lines.append(f"  - id: {id}\n    kind: {kind}\n    critical: {c}")
    return "\n".join(lines)


def conflict_list(refs):
    """refs: [(id, stance|None), ...]"""
    if not refs:
        return "[]"
    simple = [r for r in refs if isinstance(r, str)]
    if len(simple) == len(refs):
        return "[" + ", ".join(simple) + "]"
    lines = [""]
    for r in refs:
        if isinstance(r, str):
            lines.append(f"  - {r}")
        else:
            id, stance = r
            lines.append(f"  - id: {id}\n    stance: {stance}")
    return "\n".join(lines)


ME = {}  # 中土
WE = {}  # 维斯特洛

# ============ 中土 ============

ME["gondor-realm"] = ("faction", "canon", "political", True, """\
刚铎王国，第三纪元末的南方人类王国。王位空悬近千年，由执政宰相世家代管。
值得注意的是：全书对刚铎的税收、王室财政、货币发行没有任何记载——
这个王国养着常备军和七环城，却没有任何条目能说明钱从哪来。
lint 应当在此处报告空中楼阁：一个 political 层承重墙，下面没有 fiscal 支点。""",
"[]", "[]", [("fief-muster-system", "manpower", True)])

ME["fief-muster-system"] = ("faction", "canon", "military", True, """\
刚铎的封邑征召制：南方各封邑按定额出兵。佩兰诺战前的援军清单逐项可数：
洛斯阿尔那赫斧手二百（书中明言这是该地的什一征额）、林罗谷三百、
莫松德弓手五百、伊西尔渔民一百、品那斯格林三百、多阿姆洛斯步兵七百加骑士一营。
原文收束：'不足三千，再无来者。' 制度有效，但总量天花板清晰可见。""",
"[gondor-realm]", "[]", [("rohan-oath-2510", "legitimacy", True)])

ME["rohan-oath-2510"] = ("event", "canon", "political", True, """\
第三纪元2510年，执政宰相奇瑞安以卡伦那松全域赠予伊奥希奥德人，
换取永世军事同盟。伊奥梅尔誓言原文：'汝之敌即我之敌，汝之急即我之急'。
五百年后佩兰诺之战，希奥顿仍视其为神圣义务。触发机制：烽火台与红箭。
一条封建契约跨五个世纪仍是军事动员的法律基础——制度承重墙的标准样本。""",
"[]", "[]", [])

ME["mordor-host"] = ("faction", "canon", "military", True, """\
魔多的围城大军。粮食来自纳恩奴隶农庄（山姆与弗罗多亲眼所见的南方大田），
兵员纪律不依赖粮饷而依赖索伦的中央意志支配。战后纳恩奴隶被埃莱萨释放，
纳恩成为独立土地——这条供应链在战后整体失效。""",
"[]", "[]", [("nurn-slave-fields", "production", True),
           ("sauron-dominion", "x-will-binding", True)])

ME["nurn-slave-fields"] = ("location", "canon", "production", True, """\
纳恩低地的奴隶劳作大田，四河注入努尔能内陆海，土壤远比戈埚洛斯高原肥沃。
'辽阔国土南方的大片奴隶耕作之田'（《魔影之地》）。
农庄到前线军营的运量与损耗率：无记载。""",
"[]", "[]", [])

ME["sauron-dominion"] = ("faction", "canon", "ideology", True, """\
索伦的支配体系。对兽人是中央意志的蚁群式支配（'使兽人几成蚁群之生，
其控制远胜魔苟斯'，《魔苟斯之戒》p.417），对努门诺尔人与东方人类则是
利诱与许愿：延寿、秩序、复仇。恐惧是底色但非唯一手段——
同一专制者对不同对象用不同的供养关系，这正是 kind 分辨率的试金石。""",
"[]", "[]", [("the-one-ring", "legitimacy", False)])

ME["the-one-ring"] = ("item", "canon", "ideology", True, """\
至尊魔戒：统治权证书与力量电池的复合体。功能有三：储存索伦力量本源、
作为支配其余诸戒及其持有者的意志总线、以及对'诸戒之王'地位的合法性宣称。
它不是产能工具；索伦对兽人的控制不靠它（见 sauron-dominion），
它支配的是持戒者网络。一个物件同时承载 resource 与 legitimacy 两种 kind。""",
"[]", "[]", [("sauron-dominion", "resource", False)])

ME["minas-tirith"] = ("location", "canon", "economy", True, """\
米那斯提力斯，白城，七环之城。人口书内无数值（外部考据估一万五至三万，
置信度低；'半空'的描写暗示容量远大于现人口）。粮食来自佩兰诺田园
（'townlands were rich'）与安都因河运，咽喉在奥斯吉利亚斯渡桥——
渡桥失守即粮道被掐。佩兰诺围城期间的粮价与配给：无记载（stylistic missing，
托尔金根本不写后勤）。""",
"[]", "[]", [("pelennor-fields", "resource", True)])

ME["pelennor-fields"] = ("location", "canon", "resource", True, """\
佩兰诺平野：环绕白城的牧农田园，拉马斯外墙圈出的近郊产粮区。
围城前被主动弃守收缩，田野付诸敌蹄。""",
"[]", "[]", [])

# 奥克起源：三个正典版本互斥，全部保留
ME["orc-origin-silmarillion"] = ("event", "canon", None, False, """\
1951 年《精灵宝钻》选定版：奥克源于被魔苟斯俘获并扭曲的精灵。
克里斯托弗·托尔金的编辑定本，流传最广的正典。""",
"[]", conflict_list([("orc-origin-corruption", "official"),
                     ("orc-origin-myths-transformed", None)]), [])
ME["orc-origin-corruption"] = ("event", "canon", None, False, """\
正文版（奇立斯乌苟之塔，弗罗多对山姆）：'暗影只能嘲弄，不能创造……
它只是毁坏了他们，扭曲了他们。' 明确否定泥土/石头造物的旧版，
但未指明被腐化者究竟是精灵、人类还是兽类。""",
"[]", conflict_list([("orc-origin-silmarillion", "heretic"),
                     ("orc-origin-myths-transformed", None)]), [])
ME["orc-origin-myths-transformed"] = ("event", "canon", None, False, """\
1950 年代后期 Myths Transformed 文本群（VII-X）：起源在精灵、人类、
兽类与混合说之间反复，托尔金至死未定。1963 年拍卖流出信件孤证：
'想必存在女兽人……只是无人知晓。' 繁殖方式一栏：全谱系 missing。""",
"[]", conflict_list([("orc-origin-silmarillion", None),
                     ("orc-origin-corruption", None)]), [])

# 蓝袍巫师：双正典互斥
ME["blue-wizards-ut"] = ("character", "canon", None, False, """\
UT《伊斯塔利》版：阿拉塔尔与帕蓝多，第二纪元约1600年赴东方，
下落不明，'有人认为他们堕入邪恶成了索伦的仆从'。""",
"[]", conflict_list([("blue-wizards-pome", "official")]), [])
ME["blue-wizards-pome"] = ("character", "canon", None, False, """\
PoME《晚期著作》版：改名莫林赫塔与罗梅斯塔莫（'灭暗者'与'助东者'），
同约第二纪元1600年赴东方，使命是削弱索伦在东方的势力，
且'似乎成功了'——从失败翻案为成功，名字与命运全部冲突。""",
"[]", conflict_list([("blue-wizards-ut", "heretic")]), [])

# ============ 维斯特洛 ============

WE["iron-throne"] = ("faction", "canon", "political", True, """\
七国铁王座。劳勃时代财政已空：国库靠举债维持，实际财技操盘手自小指头始。
王座的军事存在（王领兵力、守夜人拨款、海政）全部悬于财政收入一线，
而收入一线早已变成债务黑洞。""",
"[]", "[]", [("crown-debt-agot", "fiscal", True)])

WE["crown-debt-agot"] = ("event", "canon", "fiscal", False, """\
AGOT《Lord Snow》口径：王冠负债六百万金龙，其中三百万欠兰尼斯特。
小指头对奈德交底。距劳勃登基仅约十五年。""",
"[]", "[crown-debt-affc]", [])
WE["crown-debt-affc"] = ("event", "canon", "fiscal", False, """\
AFFC 提利昂口径：'我们欠他们数千万'。从六百万到数千万，
约十倍级差，书中无任何过程交代。两口径并存，不加裁决——
可注记'修辞夸张/通胀'的翻译方向，但数字本身互斥。""",
"[]", "[crown-debt-agot]", [])

WE["iron-bank"] = ("faction", "canon", "economy", True, """\
布拉佛斯铁金库。放贷逻辑原文：'王侯若不能偿还铁金库，
就会有新的王侯凭空坐上他们的王位。' 瑟曦停付即转投史坦尼斯
（条件：登基后承认铁王座债务）；同时向守夜人放款购粮——
机构对国家与组织一视同仁，只问偿还能力。""",
"[]", "[]", [("braavos-free-port", "economy", True)])

WE["stannis-north-campaign"] = ("event", "canon", "military", True, """\
史坦尼斯的北境军事行动。资金完全依赖铁金库贷款，
而贷款的触发器是瑟曦的违约决定——一条政治决定撬动两个战场的资金流。""",
"[cersei-default]", "[]", [("iron-bank", "fiscal", True)])

WE["cersei-default"] = ("event", "canon", None, False, """\
瑟曦单方面停付铁金库债务的政治决定。直接后果：铁金库转投史坦尼斯，
铁王座再融资通道关闭。建模注记：本条与债务的关系是"作用于"而非"被供养"，
故用 canon_refs 而非 depends_on。""",
"[crown-debt-affc]", "[]", [])

WE["kings-landing"] = ("location", "canon", "economy", True, """\
君临，人口约五十万（提利昂口径，ASOS；马丁自定标：大于中世纪伦敦巴黎，
小于君士坦丁堡）。粮食全靠输入：玫瑰大道陆路加海运，无战略存粮——
黑水河战前海路被掐，面包暴乱直接冲击红堡，一句话证明输入线即生命线。""",
"[]", "[]", [("roseroad-grain", "resource", True)])

WE["roseroad-grain"] = ("location", "canon", "resource", True, """\
玫瑰大道：河湾地到君临的陆路粮道。河湾地是七国粮仓，
谁控制玫瑰大道，谁就捏着君临的饭碗。""",
"[]", "[]", [])

WE["braavos-free-port"] = ("location", "canon", "economy", True, """\
布拉佛斯自由港：银行业（铁金库）、保险业（钥匙持有者）、造船（兵工厂）、
渔业与海运贸易多支柱。政治底座是逃亡奴隶建城与永久禁奴法理——
这使它对奴隶湾政权有结构性敌意，也构成吸引自由贸易的身份资本。""",
"[]", "[]", [])

WE["night-watch-order"] = ("faction", "canon", "military", True, """\
当代守夜人：全团不足千人，十九座城堡常驻者仅三座
（黑城堡、影子塔、东海望）。守卫对象是三百英里长、七百尺高的长城。""",
"[]", conflict_list([("the-wall-scale", None)]),
[])

WE["the-wall-scale"] = ("location", "canon", None, False, """\
长城本体设定：七百尺高、三百英里长、十九座城堡。
筑城者时代的组织能力 vs 当代守夜人不足千人的规模落差无解——
可读作叙事性退化（degradation），亦可读作解释缺失（missing），两解并存。""",
"[]", conflict_list([("night-watch-order", None)]), [])

WE["robb-host-theon"] = ("event", "canon", "military", False, """\
萝卜南下兵力·席恩口径：两万。""",
"[]", "[robb-host-ledger]", [])
WE["robb-host-ledger"] = ("event", "canon", "military", False, """\
萝卜南下兵力·分项加总口径：封邑逐项合计约一万七千，
绿叉河后回流计算约一万八千。与席恩口径差幅超一成，三方均无解释。""",
"[]", "[robb-host-theon]", [])

WE["wight-army"] = ("faction", "canon", "military", True, """\
尸鬼军团：复活尸体组成的不死者大军。无粮食需求、无睡眠、士气恒定，
且随身携冬（'寒冷随他们而来'）——魔法替代后勤的双向豁免。
一切活人大军都受粮食与债务链条约束，唯独它的成本函数里没有 food 项。""",
"[]", "[]", [("the-others-magic", "x-magic-logistics", True)])

WE["the-others-magic"] = ("faction", "canon", "ideology", True, """\
异鬼的寒冰魔法：复活死者、改变环境补给条件的超自然力量源头。
注意其位于 ideology 层——它是信仰之外的另一类'非物质的支配力'，
kind 实验值 x-magic-logistics 的供给方。""",
"[]", "[]", [])

WE["the-north"] = ("faction", "canon", "political", True, """\
北境。地广人稀，封臣征召制，动员总量天花板低（萝卜只能拉出一两万）。
长冬存粮制度：口头焦虑无数，具体制度几乎无记载——
冬市镇入冬迁出、曼德勒丰收宴、卡林湾沼泽存粮，皆零星线索不成体系。
与刚铎财政并列为'大师共同的盲区'：political 承重墙下缺 fiscal 支点。""",
"[]", "[]", [("robb-host-ledger", "manpower", False)])


def write_world(path: Path, entries: dict) -> None:
    if path.exists():
        shutil.rmtree(path)
    (path / "entries").mkdir(parents=True)
    for id, (type_, status, layer, lb, body, refs, conflicts, deps) in entries.items():
        title = id
        text = fm(id, title, type_, status, layer=layer, load_bearing=lb,
                  canon_refs=refs,
                  conflicts=conflicts if conflicts.startswith("[") or conflicts == "[]"
                  else conflict_list([]),
                  depends=dep_list(deps))
        (path / "entries" / f"{id}.md").write_text(text + body, encoding="utf-8")


write_world(ROOT / "world-middle-earth", ME)
write_world(ROOT / "world-westeros", WE)
print(f"middle-earth: {len(ME)} entries, westeros: {len(WE)} entries")
